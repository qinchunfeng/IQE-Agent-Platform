"""HTTP API 请求/响应模型。

文档未定义 API 路径与响应结构【已确认 Q1】。这里的字段只服务 Demo UI,
不改变文档 3.1 的事件信封字段。所有请求模型禁止额外字段,避免静默忽略。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .event import EventEnvelope


class PipelineStage(BaseModel):
    """文档 4.2 流水线阶段字段。"""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    input_source: str | None = None
    llm_provider: str | None = None
    knowledge_base: str | None = None
    tool: str | None = None
    human_gate: bool | None = None
    # 阶段级 Prompt 覆盖;留空使用 Agent 插件配置中的 system_prompt。
    system_prompt: str | None = Field(default=None, max_length=12000)


class PipelineDefinition(BaseModel):
    """文档 4.2 流水线组合结构。"""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str = Field(min_length=1, max_length=100)
    orchestrator: str = Field(min_length=1)
    stages: list[PipelineStage] = Field(min_length=1)


class PushEventRequest(BaseModel):
    """【已确认 Q18】文档未定义模拟事件入参;Demo 以案例 ID 触发 Mock Jenkins。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str | None = Field(default=None, min_length=1, max_length=100)


class ReviewRequest(BaseModel):
    """人工审批入参。文档场景 2 要求驳回时填写原因,但未说明是否必填【待确认 Q5】。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)


class PluginConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]


class PluginHealthOut(BaseModel):
    healthy: bool
    message: str
    checked_at: str | None = None


class PluginOut(BaseModel):
    plugin_id: str
    display_name: str
    description: str
    plugin_type: str
    plugin_type_label: str
    config_schema: dict[str, Any]
    config: dict[str, Any]
    dependencies: dict[str, Any]
    capabilities: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    state: str
    health: PluginHealthOut | None = None


class PluginCategoryOut(BaseModel):
    type: str
    label: str
    plugins: list[PluginOut]


class PluginListOut(BaseModel):
    categories: list[PluginCategoryOut]


class PushEventOut(BaseModel):
    run_id: str
    trace_id: str
    case_id: str
    orchestrator_configured: str
    orchestrator_effective: str
    fallback_reason: str | None = None
    event: EventEnvelope


class KnowledgeEntryOut(BaseModel):
    entry_id: str
    title: str
    content: str
    category: str
    summary: str | None = None
    root_cause: str | None = None
    source_trace_id: str | None = None
    created_at: str
    score: float | None = None


class KnowledgeListOut(BaseModel):
    items: list[KnowledgeEntryOut]


class ReviewOut(BaseModel):
    run: dict[str, Any]
    events: list[dict[str, Any]]
    ticket: dict[str, Any] | None = None


class ExperimentBaselineOut(BaseModel):
    name: str
    model_loc: str | None = None
    tat_minutes: float
    cost_per_ticket: float | None = None
    confidence: float | None = None
    source: str


class ExperimentSummaryOut(BaseModel):
    baselines: list[ExperimentBaselineOut]
    computed: dict[str, Any]
