"""Mock 降级策略。

文档 7.4:
- Airflow → 内存编排器(Airflow API 不可用或超时)
- Qoder CN → Mock LLM(Qoder CN API 不可用或超时)

健康检查超时【已确认 Q10】由 config.HEALTH_CHECK_TIMEOUT_SECONDS 统一控制(2 秒)。
"""

from __future__ import annotations

from typing import Any

from ..errors import NotFoundError, PluginUnavailableError
from ..plugins.base import BasePlugin
from ..plugins.capabilities import (
    LLMProviderCapability,
    OrchestratorCapability,
    as_llm_provider,
    as_orchestrator,
)
from ..plugins.registry import PluginRegistry


async def resolve_llm(
    registry: PluginRegistry, preferred_id: str | None
) -> tuple[LLMProviderCapability, LLMProviderCapability | None, str | None]:
    """返回 (主 LLM, Mock LLM, 降级原因)。"""

    mock = (
        as_llm_provider(registry.get("mock_llm"))
        if registry.has("mock_llm") and registry.is_enabled("mock_llm")
        else None
    )
    preferred = preferred_id or "mock_llm"
    if preferred == "mock_llm":
        if mock is None:
            raise PluginUnavailableError("Mock LLM 已禁用")
        return mock, mock, None
    if not registry.has(preferred):
        if mock is None:
            raise PluginUnavailableError(f"LLM 插件不存在且 Mock LLM 已禁用: {preferred}")
        return mock, mock, f"LLM 插件不存在: {preferred},降级到 Mock LLM"
    if not registry.is_enabled(preferred):
        if mock is None:
            raise PluginUnavailableError(f"LLM 插件已禁用且 Mock LLM 已禁用: {preferred}")
        return mock, mock, f"LLM 插件已禁用: {preferred},降级到 Mock LLM"

    health = await registry.health(preferred)
    if not health["healthy"]:
        if mock is None:
            raise PluginUnavailableError(f"LLM 不可用且 Mock LLM 已禁用: {health['message']}")
        return mock, mock, f"LLM 不可用({health['message']}),降级到 Mock LLM"
    primary = as_llm_provider(registry.get(preferred))
    if primary is None:
        raise PluginUnavailableError(f"插件未实现 LLM 提供商能力: {preferred}")
    return primary, mock, None


async def resolve_orchestrator(
    registry: PluginRegistry, preferred_id: str | None
) -> tuple[OrchestratorCapability, str | None]:
    """返回 (实际编排器, 降级原因)。"""

    if not registry.has("memory_orchestrator") or not registry.is_enabled("memory_orchestrator"):
        raise PluginUnavailableError("内置编排器被禁用,平台无法运行")
    memory = as_orchestrator(registry.get("memory_orchestrator"))
    if memory is None:
        raise PluginUnavailableError("内置编排器未实现编排引擎能力,平台无法运行")
    preferred = preferred_id or "memory_orchestrator"
    if preferred == "memory_orchestrator":
        return memory, None
    if not registry.has(preferred):
        return memory, f"编排器不存在: {preferred},降级到内置编排器"
    if not registry.is_enabled(preferred):
        return memory, f"编排器已禁用: {preferred},降级到内置编排器"

    health = await registry.health(preferred)
    if not health["healthy"]:
        return memory, f"编排器不可用({health['message']}),降级到内置编排器"
    airflow = as_orchestrator(registry.get(preferred))
    if airflow is None:
        return memory, f"编排器 {preferred} 未实现编排引擎能力,降级到内置编排器"
    return airflow, None


def resolve_optional_plugin(
    registry: PluginRegistry, plugin_id: str | None
) -> BasePlugin | None:
    """按阶段配置解析知识库/工具;禁用或缺失时返回 None,由 Agent 决定行为。"""

    if not plugin_id or not registry.has(plugin_id):
        return None
    if not registry.is_enabled(plugin_id):
        return None
    try:
        return registry.get(plugin_id)
    except (NotFoundError, PluginUnavailableError):
        return None


__all__: list[Any] = ["resolve_llm", "resolve_orchestrator", "resolve_optional_plugin"]
