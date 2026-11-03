"""文档 3.1 标准事件信封校验测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.event import EventEnvelope, EventStatus, EventType, ModelLoc


def _event(**overrides):
    data = {
        "event_id": "event-1",
        "event_type": "monitor_alert",
        "source_agent": "mock_jenkins",
        "timestamp": datetime.now(timezone.utc),
        "trace_id": "trace-1",
        "confidence": 0.7,
        "evidence_links": ["mock://jenkins/job/1/console"],
        "status": "pending",
        "model_info": {
            "model_loc": "mock",
            "model_name": "mock-llm-v1",
            "latency_ms": 0,
            "cost_token": 0,
        },
        "payload": {},
    }
    data.update(overrides)
    return data


def test_document_enum_values():
    assert {item.value for item in EventType} == {
        "monitor_alert",
        "triage_result",
        "repro_result",
        "ticket_draft",
        "review_result",
        "report_item",
    }
    assert {item.value for item in EventStatus} == {
        "pending",
        "passed",
        "rejected",
        "need_more_info",
        "handover_human",
    }
    assert {item.value for item in ModelLoc} == {
        "local_strix_halo",
        "cloud_qoder_cn",
        "mock",
    }


def test_valid_event_serializes_timestamp_with_z():
    event = EventEnvelope.model_validate(_event())
    dumped = event.model_dump(mode="json")
    assert dumped["timestamp"].endswith("Z")
    assert dumped["confidence"] == 0.7


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_must_be_between_zero_and_one(confidence):
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_event(confidence=confidence))


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_event(event_type="custom_event"))


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_event(status="done"))


def test_missing_model_info_is_rejected():
    data = _event()
    data.pop("model_info")
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_event(extra_field=True))
