"""插件注册中心。

文档 3.4 生命周期:注册 → 配置 → 健康检查 → 加载 → 运行 → 卸载。
文档 2.1:插件声明依赖;文档 7.1:插件隔离与故障不影响其他插件。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import threading
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..config import HEALTH_CHECK_TIMEOUT_SECONDS
from ..errors import ConfigurationError, NotFoundError, PluginUnavailableError
from ..logging_config import get_logger
from ..security import config_defaults, mask_config, validate_plugin_config
from .base import PLUGIN_TYPE_LABELS, AgentPlugin, BasePlugin, is_plugin_class

logger = get_logger("iqe.plugins")

_CATEGORY_ORDER = [
    "input_source",
    "agent",
    "knowledge_base",
    "tool",
    "orchestrator",
    "llm_provider",
    "event_bus",
    "storage",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PluginRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[BasePlugin]] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._instances: dict[str, BasePlugin] = {}
        self._health: dict[str, dict[str, Any]] = {}
        self._runner: Callable[..., Awaitable[Any]] | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------- discovery

    def discover(self) -> None:
        if self._classes:
            return
        import app.plugins as plugins_package

        for module_info in pkgutil.walk_packages(
            plugins_package.__path__, prefix=f"{plugins_package.__name__}."
        ):
            module = importlib.import_module(module_info.name)
            for _, candidate in inspect.getmembers(module, is_plugin_class):
                plugin_id = candidate.plugin_id
                if plugin_id in self._classes:
                    logger.warning(
                        "duplicate plugin id ignored",
                        extra={"plugin_id": plugin_id, "module_name": module_info.name},
                    )
                    continue
                self._classes[plugin_id] = candidate

    def initialize(self) -> None:
        db.init_db()
        self.discover()
        stored = db.list_plugin_states()
        for plugin_id, plugin_class in self._classes.items():
            defaults = config_defaults(plugin_class.config_schema)
            state = stored.get(plugin_id)
            if state is None:
                config = validate_plugin_config(plugin_class.config_schema, defaults)
                enabled = plugin_class.enabled_by_default
                db.upsert_plugin_state(plugin_id, enabled, config)
            else:
                enabled = bool(state["enabled"])
                try:
                    config = validate_plugin_config(
                        plugin_class.config_schema, state.get("config", {})
                    )
                except ConfigurationError:
                    logger.warning(
                        "invalid stored plugin config, falling back to defaults",
                        extra={"plugin_id": plugin_id},
                    )
                    config = validate_plugin_config(plugin_class.config_schema, defaults)
                    db.upsert_plugin_state(plugin_id, enabled, config)
            self._states[plugin_id] = {"enabled": enabled, "config": config}
            if plugin_class.plugin_type != "agent" and enabled:
                self._instantiate(plugin_id)
        logger.info(
            "plugins initialized",
            extra={
                "plugin_count": len(self._classes),
                "agent_count": sum(
                    1 for cls in self._classes.values() if cls.plugin_type == "agent"
                ),
            },
        )

    def set_runner(self, runner: Callable[..., Awaitable[Any]]) -> None:
        self._runner = runner
        instance = self._instances.get("memory_orchestrator")
        if instance is not None:
            instance.resolved_dependencies["runner"] = runner

    # --------------------------------------------------------------- helpers

    def _plugin_class(self, plugin_id: str) -> type[BasePlugin]:
        plugin_class = self._classes.get(plugin_id)
        if plugin_class is None:
            raise NotFoundError(f"插件不存在: {plugin_id}")
        return plugin_class

    def _dependencies(self) -> dict[str, Any]:
        return {"registry": self, "runner": self._runner}

    def _instantiate(self, plugin_id: str) -> BasePlugin:
        plugin_class = self._plugin_class(plugin_id)
        if plugin_class.plugin_type == "agent":
            raise ConfigurationError("Agent 插件按运行实例化,不保存单例")
        existing = self._instances.get(plugin_id)
        if existing is not None:
            return existing
        config = self._states.get(plugin_id, {}).get("config", {})
        instance = plugin_class(config=config, dependencies=self._dependencies())
        instance.load()
        self._instances[plugin_id] = instance
        return instance

    def _drop_instance(self, plugin_id: str) -> None:
        instance = self._instances.pop(plugin_id, None)
        if instance is not None:
            instance.unload()

    def has(self, plugin_id: str) -> bool:
        return plugin_id in self._classes

    def is_enabled(self, plugin_id: str) -> bool:
        self._plugin_class(plugin_id)
        return bool(self._states.get(plugin_id, {}).get("enabled", False))

    def is_agent(self, plugin_id: str) -> bool:
        return self._plugin_class(plugin_id).plugin_type == "agent"

    def is_type(self, plugin_id: str, plugin_type: str) -> bool:
        return self._plugin_class(plugin_id).plugin_type == plugin_type

    def input_source_ids(self) -> list[str]:
        return [
            plugin_id
            for plugin_id, plugin_class in self._classes.items()
            if plugin_class.plugin_type == "input_source"
        ]

    def get_config(self, plugin_id: str) -> dict[str, Any]:
        self._plugin_class(plugin_id)
        return dict(self._states.get(plugin_id, {}).get("config", {}))

    def resolve_agent_prompt(
        self, plugin_id: str, stage_prompt: str | None = None
    ) -> tuple[str, str]:
        """解析 Agent 最终生效的 system prompt 与来源(阶段 > 插件 > 默认)。"""

        stage_value = str(stage_prompt or "").strip()
        if stage_value:
            return stage_value, "stage"
        plugin_class = self._plugin_class(plugin_id)
        default_prompt = str(getattr(plugin_class, "default_system_prompt", "") or "")
        configured = str(self.get_config(plugin_id).get("system_prompt") or "").strip()
        if configured:
            # 插件配置持久化了默认模板时,来源仍应标为“内置默认”。
            return configured, ("default" if configured == default_prompt else "plugin")
        return default_prompt, "default"

    def get(self, plugin_id: str) -> BasePlugin:
        plugin_class = self._plugin_class(plugin_id)
        if plugin_class.plugin_type == "agent":
            raise ConfigurationError("Agent 插件必须通过 create_agent 实例化")
        if not self.is_enabled(plugin_id):
            raise PluginUnavailableError(f"插件已禁用: {plugin_id}")
        return self._instantiate(plugin_id)

    def create_agent(
        self,
        plugin_id: str,
        dependencies: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> AgentPlugin:
        plugin_class = self._plugin_class(plugin_id)
        if plugin_class.plugin_type != "agent":
            raise ConfigurationError(f"插件不是 Agent: {plugin_id}")
        if not issubclass(plugin_class, AgentPlugin):
            raise ConfigurationError(f"Agent 插件未实现 AgentPlugin 契约: {plugin_id}")
        if not self.is_enabled(plugin_id):
            raise PluginUnavailableError(f"Agent 插件已禁用: {plugin_id}")
        config = self.get_config(plugin_id)
        if overrides:
            # 阶段级配置优先于插件配置,仍按 config_schema 严格校验。
            config = validate_plugin_config(
                plugin_class.config_schema, {**config, **overrides}
            )
        instance = plugin_class(config=config, dependencies=dependencies)
        instance.load()
        return instance

    # ------------------------------------------------------------- lifecycle

    async def health(self, plugin_id: str) -> dict[str, Any]:
        plugin_class = self._plugin_class(plugin_id)
        if not self.is_enabled(plugin_id):
            result = {"healthy": False, "message": "插件已禁用", "checked_at": _now_iso()}
            self._health[plugin_id] = result
            return result
        if plugin_class.plugin_type == "agent":
            result = {"healthy": True, "message": "Agent 就绪", "checked_at": _now_iso()}
            self._health[plugin_id] = result
            return result
        try:
            instance = self._instantiate(plugin_id)
            # 外部输入源(如 Airflow)允许声明更长的健康检查预算;默认仍为 2 秒。
            timeout = float(
                getattr(instance, "health_timeout_seconds", HEALTH_CHECK_TIMEOUT_SECONDS)
            )
            healthy, message = await asyncio.wait_for(
                instance.health(), timeout=timeout
            )
            result = {
                "healthy": bool(healthy),
                "message": str(message),
                "checked_at": _now_iso(),
            }
        except TimeoutError:
            result = {
                "healthy": False,
                "message": "健康检查超时",
                "checked_at": _now_iso(),
            }
        except Exception as exc:  # noqa: BLE001 - 健康检查不能拖垮平台
            result = {
                "healthy": False,
                "message": f"健康检查失败: {exc.__class__.__name__}",
                "checked_at": _now_iso(),
            }
        self._health[plugin_id] = result
        return result

    async def health_many(self, plugin_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(plugin_ids)
        results = await asyncio.gather(*(self.health(plugin_id) for plugin_id in ids))
        return dict(zip(ids, results, strict=True))

    def plugin_summary(self, plugin_id: str, health: dict[str, Any] | None = None) -> dict[str, Any]:
        plugin_class = self._plugin_class(plugin_id)
        state = self._states.get(plugin_id, {})
        instance = self._instances.get(plugin_id)
        return {
            "plugin_id": plugin_id,
            "display_name": plugin_class.display_name,
            "description": plugin_class.description,
            "plugin_type": plugin_class.plugin_type,
            "plugin_type_label": PLUGIN_TYPE_LABELS.get(
                plugin_class.plugin_type, plugin_class.plugin_type
            ),
            "config_schema": plugin_class.config_schema,
            "config": mask_config(plugin_class.config_schema, state.get("config", {})),
            "dependencies": plugin_class.dependencies,
            "capabilities": plugin_class.capabilities,
            "enabled": bool(state.get("enabled", False)),
            "state": instance.state if instance else "registered",
            "health": health if health is not None else self._health.get(plugin_id),
        }

    async def list_plugins(self, check_health: bool = False) -> list[dict[str, Any]]:
        ids = list(self._classes)
        health_map: dict[str, dict[str, Any]] = {}
        if check_health:
            health_map = await self.health_many(ids)
        else:
            health_map = {plugin_id: self._health[plugin_id] for plugin_id in ids if plugin_id in self._health}

        categories: list[dict[str, Any]] = []
        for plugin_type in _CATEGORY_ORDER:
            members = [
                self.plugin_summary(plugin_id, health_map.get(plugin_id))
                for plugin_id in ids
                if self._classes[plugin_id].plugin_type == plugin_type
            ]
            if members:
                categories.append(
                    {
                        "type": plugin_type,
                        "label": PLUGIN_TYPE_LABELS.get(plugin_type, plugin_type),
                        "plugins": members,
                    }
                )
        return categories

    def configure(self, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        plugin_class = self._plugin_class(plugin_id)
        current = self._states.get(plugin_id, {"enabled": False, "config": {}})
        incoming = dict(config)
        # 前端回传脱敏值 *** 时保留原密钥,避免误覆盖
        for field, field_schema in plugin_class.config_schema.items():
            if field_schema.get("secret") and incoming.get(field) == "***":
                incoming[field] = current.get("config", {}).get(field, "")
        normalized = validate_plugin_config(plugin_class.config_schema, incoming)
        db.upsert_plugin_state(plugin_id, bool(current.get("enabled", False)), normalized)
        self._states[plugin_id] = {"enabled": bool(current.get("enabled", False)), "config": normalized}
        self._health.pop(plugin_id, None)
        if plugin_class.plugin_type != "agent" and self.is_enabled(plugin_id):
            self._drop_instance(plugin_id)
            self._instantiate(plugin_id)
        return self.plugin_summary(plugin_id)

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        self._plugin_class(plugin_id)
        current = self._states.get(plugin_id, {"enabled": False, "config": {}})
        self._states[plugin_id] = {
            "enabled": bool(enabled),
            "config": dict(current.get("config", {})),
        }
        db.upsert_plugin_state(plugin_id, bool(enabled), self._states[plugin_id]["config"])
        self._health.pop(plugin_id, None)
        if enabled:
            if not self.is_agent(plugin_id):
                self._instantiate(plugin_id)
        else:
            self._drop_instance(plugin_id)
        return self.plugin_summary(plugin_id)

    async def shutdown(self) -> None:
        for plugin_id in list(self._instances):
            self._drop_instance(plugin_id)


registry = PluginRegistry()
