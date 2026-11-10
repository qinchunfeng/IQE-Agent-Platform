"""内核侧插件能力协议。

内核只声明"我需要什么能力",不 import 具体插件类:`registry.get()` 返回 BasePlugin,
按能力协议取用才受类型检查。缺能力时在取用点报错,而不是在调用栈深处抛 AttributeError。

协议只描述文档已定义或平台已在调用的方法,新增方法等于新增契约【已确认 Q2/Q27】。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models.event import EventEnvelope


@runtime_checkable
class LLMProviderCapability(Protocol):
    """文档 3.3。"""

    async def chat_completion(
        self, messages: list[dict[str, str]], config: dict[str, Any]
    ) -> dict[str, Any]: ...


@runtime_checkable
class OrchestratorCapability(Protocol):
    """文档 3.2;`context` 见【待确认 Q27】。"""

    plugin_id: str

    async def start_pipeline(
        self, pipeline_def: dict[str, Any], context: dict[str, Any] | None = None
    ) -> str: ...

    async def get_pipeline_status(self, run_id: str) -> dict[str, Any]: ...

    async def stop_pipeline(self, run_id: str) -> None: ...


@runtime_checkable
class AlertSourceCapability(Protocol):
    """可轮询输入源【已确认 Q24】:平台按 capabilities.polling 决定是否轮询。"""

    config: dict[str, Any]
    capabilities: dict[str, Any]

    async def collect_alerts(
        self, limit: int | None = None, lookback_minutes: int | None = None
    ) -> list[EventEnvelope]: ...


@runtime_checkable
class AlertBuilderCapability(Protocol):
    """把一条演示/构建记录直接转成 monitor_alert 的输入源。"""

    def build_alert(self, case_id: str | None = None) -> EventEnvelope: ...


@runtime_checkable
class TicketCapability(Protocol):
    """工单工具:先草稿后正式单(文档 6 场景 2)。"""

    def create_draft(self, draft: dict[str, Any]) -> dict[str, Any]: ...

    def create_ticket(self, draft: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class ReproduceCapability(Protocol):
    """复现工具(文档 6 场景 1 的 Mock Jarvis)。"""

    def reproduce(self, case: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class KnowledgeCapability(Protocol):
    """知识库【已确认 Q6/Q7】:结构化入库,检索只用标题/正文。"""

    def add(
        self,
        *,
        title: str,
        content: str,
        category: str,
        summary: str | None = None,
        root_cause: str | None = None,
        source_trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]: ...

    def list_entries(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class NotifierCapability(Protocol):
    """通知工具【已确认 Q26】:先问是否启用/已配置,再投递。"""

    def enabled_for_status(self, status: str) -> bool: ...

    def is_configured(self) -> tuple[bool, str]: ...

    async def send_report(self, report: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class EventBusCapability(Protocol):
    async def publish(self, event: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------- 窄化访问器
#
# mypy 不允许把 Protocol 类对象传给 `type[T]`(type-abstract),因此窄化写成显式函数:
# 调用点 `kb = as_knowledge(registry.get(...))` 既保留运行期能力校验,又是静态可验证的。
# 返回 None 表示"插件存在但不具备所需能力",由调用方决定报错还是降级。


def as_llm_provider(plugin: object) -> LLMProviderCapability | None:
    return plugin if isinstance(plugin, LLMProviderCapability) else None


def as_orchestrator(plugin: object) -> OrchestratorCapability | None:
    return plugin if isinstance(plugin, OrchestratorCapability) else None


def as_alert_source(plugin: object) -> AlertSourceCapability | None:
    return plugin if isinstance(plugin, AlertSourceCapability) else None


def as_alert_builder(plugin: object) -> AlertBuilderCapability | None:
    return plugin if isinstance(plugin, AlertBuilderCapability) else None


def as_ticket_tool(plugin: object) -> TicketCapability | None:
    return plugin if isinstance(plugin, TicketCapability) else None


def as_reproduce_tool(plugin: object) -> ReproduceCapability | None:
    return plugin if isinstance(plugin, ReproduceCapability) else None


def as_knowledge(plugin: object) -> KnowledgeCapability | None:
    return plugin if isinstance(plugin, KnowledgeCapability) else None


def as_notifier(plugin: object) -> NotifierCapability | None:
    return plugin if isinstance(plugin, NotifierCapability) else None


def as_event_bus(plugin: object) -> EventBusCapability | None:
    return plugin if isinstance(plugin, EventBusCapability) else None
