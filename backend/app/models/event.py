"""标准事件信封。

逐字对齐文档 3.1:
- event_type: monitor_alert | triage_result | repro_result | ticket_draft | review_result | report_item
- status: pending | passed | rejected | need_more_info | handover_human
- model_loc: local_strix_halo | cloud_qoder_cn | mock
- confidence: 0.0 ~ 1.0
- 必填字段: event_id、event_type、source_agent、timestamp、trace_id、confidence、
  evidence_links、status、model_info{model_loc, model_name, latency_ms, cost_token}、payload
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class EventType(str, Enum):
    MONITOR_ALERT = "monitor_alert"
    TRIAGE_RESULT = "triage_result"
    REPRO_RESULT = "repro_result"
    TICKET_DRAFT = "ticket_draft"
    REVIEW_RESULT = "review_result"
    REPORT_ITEM = "report_item"


class EventStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    REJECTED = "rejected"
    NEED_MORE_INFO = "need_more_info"
    HANDOVER_HUMAN = "handover_human"


class ModelLoc(str, Enum):
    LOCAL_STRIX_HALO = "local_strix_halo"
    CLOUD_QODER_CN = "cloud_qoder_cn"
    MOCK = "mock"


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_loc: ModelLoc
    model_name: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
    cost_token: int = Field(ge=0)


class EventEnvelope(BaseModel):
    """文档 3.1 标准事件信封。额外字段一律拒绝。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: EventType
    source_agent: str = Field(min_length=1)
    timestamp: datetime
    trace_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_links: list[str] = Field(default_factory=list)
    status: EventStatus
    model_info: ModelInfo
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_event(data: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope.model_validate(data)
