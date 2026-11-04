"""8 类插件统一契约。

文档 2 节:所有插件遵循统一契约 plugin_id、display_name、config_schema、health()、生命周期管理。
文档 3.2/3.3 给出编排引擎与 LLM 提供商接口,这里逐字保留方法名与返回语义。
文档未定义的插件内部接口(知识库/工具/事件总线/存储)标记【已确认 Q2】。
"""

from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, ClassVar

from ..security import validate_plugin_config

PLUGIN_TYPE_LABELS = {
    "input_source": "输入源插件",
    "agent": "Agent 插件",
    "knowledge_base": "知识库插件",
    "tool": "工具插件",
    "orchestrator": "编排引擎插件",
    "llm_provider": "LLM 提供商插件",
    "event_bus": "事件总线插件",
    "storage": "存储插件",
}


class BasePlugin:
    plugin_id: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    plugin_type: ClassVar[str] = ""
    config_schema: ClassVar[dict[str, dict[str, Any]]] = {}
    # 文档 2.1:插件声明依赖的其他插件类型
    dependencies: ClassVar[dict[str, list[str]]] = {}
    # 【已确认 Q8】插件能力标识,用于区分“已注册”与“可承担执行委托”。
    capabilities: ClassVar[dict[str, Any]] = {}
    enabled_by_default: ClassVar[bool] = True

    def __init__(
        self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None
    ) -> None:
        self.config = validate_plugin_config(self.config_schema, config or {})
        self.dependencies: dict[str, Any] = dependencies or {}
        self.state = "registered"
        self._executor: ThreadPoolExecutor | None = None

    async def health(self) -> tuple[bool, str]:
        return True, "ok"

    def load(self) -> None:
        # 文档 7.1:每个插件运行在独立线程(Phase 2 要求)。
        # 【已确认 Q16】线程 vs 进程由平台规范确认;Demo 采用单线程执行器。
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"plugin-{self.plugin_id or 'unknown'}"
            )
        self.state = "loaded"

    def unload(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self.state = "unloaded"

    async def run_isolated(
        self,
        factory: Callable[[], Awaitable[Any]],
        timeout: float | None = None,
    ) -> Any:
        """在插件专属线程中执行协程,隔离插件故障。

        文档 7.1:插件崩溃不影响其他插件。线程超时后 Python 无法强杀线程,
        因此超时只保证调用方及时失败【已确认 Q16】。
        """

        if self._executor is None:
            self.load()
        assert self._executor is not None
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, lambda: asyncio.run(factory()))
        if timeout is None:
            return await future
        return await asyncio.wait_for(future, timeout=timeout)

    def describe(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "display_name": self.display_name,
            "description": self.description,
            "plugin_type": self.plugin_type,
            "plugin_type_label": PLUGIN_TYPE_LABELS.get(self.plugin_type, self.plugin_type),
            "config_schema": self.config_schema,
            "dependencies": self.dependencies,
            "capabilities": self.capabilities,
            "state": self.state,
        }


class InputSourcePlugin(BasePlugin):
    """输入源插件。文档只定义职责,未定义方法【已确认 Q1/Q2】。

    【待确认 Q24】多输入源/轮询为画布扩展:支持实时监控的插件实现
    collect_alerts();不支持轮询的插件返回空列表,由外部 webhook 推送。
    """

    plugin_type = "input_source"

    async def collect_alerts(
        self, limit: int | None = None, lookback_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        return []


class AgentPlugin(BasePlugin):
    """Agent 插件。文档附录 A 约定 input_event_types/output_event_type/run。"""

    plugin_type = "agent"
    input_event_types: ClassVar[list[str]] = []
    output_event_type: ClassVar[str] = ""

    async def run(self, input_event: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class KnowledgeBasePlugin(BasePlugin):
    """知识库插件。文档未定义接口【已确认 Q2/Q7】。"""

    plugin_type = "knowledge_base"


class ToolPlugin(BasePlugin):
    """工具插件。文档未定义接口【已确认 Q2】。"""

    plugin_type = "tool"


class OrchestratorPlugin(BasePlugin):
    """文档 3.2 编排引擎接口。"""

    plugin_type = "orchestrator"

    async def start_pipeline(self, pipeline_def: dict[str, Any]) -> str:
        raise NotImplementedError

    async def get_pipeline_status(self, run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def stop_pipeline(self, run_id: str) -> None:
        raise NotImplementedError


class LLMProviderPlugin(BasePlugin):
    """文档 3.3 LLM 提供商接口。"""

    plugin_type = "llm_provider"

    async def chat_completion(
        self, messages: list[dict[str, str]], config: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> tuple[bool, str]:
        raise NotImplementedError


class EventBusPlugin(BasePlugin):
    plugin_type = "event_bus"


class StoragePlugin(BasePlugin):
    plugin_type = "storage"


def is_plugin_class(candidate: Any) -> bool:
    return (
        inspect.isclass(candidate)
        and issubclass(candidate, BasePlugin)
        and candidate is not BasePlugin
        and bool(getattr(candidate, "plugin_id", ""))
    )
