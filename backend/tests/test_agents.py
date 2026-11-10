"""Agent 阈值、置信度传递、知识库命中与降级测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import db
from app.errors import SchemaValidationFailure
from app.models.event import EventEnvelope, EventStatus, EventType, ModelInfo, ModelLoc
from app.plugins.agents.monitor_agent import MonitorAgent
from app.plugins.agents.reporting_agent import ReportingAgent
from app.plugins.agents.reproduction_agent import ReproductionAgent
from app.plugins.agents.reviewer_agent import ReviewerAgent
from app.plugins.agents.ticket_agent import TicketAgent
from app.plugins.agents.triage_agent import TriageAgent
from app.plugins.memory_vector_kb import MemoryVectorKBPlugin
from app.plugins.mock_jarvis import MockJarvisPlugin
from app.plugins.mock_jenkins import MockJenkinsPlugin
from app.plugins.mock_llm import MockLLMPlugin


def _event(event_type: EventType, confidence: float, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        event_id="event-1",
        event_type=event_type,
        source_agent="test",
        timestamp=datetime.now(timezone.utc),
        trace_id="trace-1",
        confidence=confidence,
        evidence_links=[],
        status=EventStatus.PASSED,
        model_info=ModelInfo(
            model_loc=ModelLoc.MOCK, model_name="mock-llm-v1", latency_ms=0, cost_token=0
        ),
        payload=payload,
    )


@pytest.fixture()
def llm():
    return MockLLMPlugin(config={}, dependencies={})


@pytest.mark.asyncio
async def test_triage_low_confidence_is_0_6(llm):
    agent = TriageAgent(config={}, dependencies={"llm_provider": llm, "mock_llm": llm})
    agent.load()
    try:
        event = MockJenkinsPlugin(config={}).build_alert("IQE-CASE-019")
        result = await agent.run(event)
        assert result.confidence == 0.6
        assert result.payload["category"] == "unknown"
        assert result.model_info.latency_ms == 180_000
    finally:
        agent.unload()


@pytest.mark.asyncio
async def test_triage_driver_case_without_kb_is_0_75(llm):
    agent = TriageAgent(config={}, dependencies={"llm_provider": llm, "mock_llm": llm})
    agent.load()
    try:
        event = MockJenkinsPlugin(config={}).build_alert("IQE-CASE-017")
        result = await agent.run(event)
        assert result.confidence == 0.75
        assert result.payload["category"] == "driver_compatibility"
        assert result.payload["kb_hit"] is False
    finally:
        agent.unload()


@pytest.mark.asyncio
async def test_triage_hits_knowledge_and_raises_confidence(llm):
    db.init_db()
    kb = MemoryVectorKBPlugin(config={})
    kb.load()
    kb.add(
        title="GPU 驱动兼容性 A - driver_compatibility",
        content="GPU driver 25.10 crash when initializing device 0 after firmware update",
        category="driver_compatibility",
        source_trace_id="seed-trace",
    )
    agent = TriageAgent(
        config={},
        dependencies={"llm_provider": llm, "mock_llm": llm, "knowledge_base": kb},
    )
    agent.load()
    try:
        event = MockJenkinsPlugin(config={}).build_alert("IQE-CASE-018")
        result = await agent.run(event)
        assert result.confidence == 0.92
        assert result.payload["kb_hit"] is True
        assert result.model_info.latency_ms == 30_000
    finally:
        agent.unload()
        kb.unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confidence", "expected_status"),
    [(0.6, EventStatus.HANDOVER_HUMAN), (0.7, EventStatus.PASSED), (0.92, EventStatus.PASSED)],
)
async def test_reviewer_threshold(llm, confidence, expected_status):
    agent = ReviewerAgent(config={}, dependencies={"llm_provider": llm, "mock_llm": llm})
    agent.load()
    try:
        event = _event(
            EventType.TICKET_DRAFT,
            confidence,
            {
                "case_id": "IQE-CASE-TEST",
                "ticket_title": "test ticket",
                "log_excerpt": "assert failure",
                "category": "product_bug",
                "priority": "P1",
            },
        )
        result = await agent.run(event)
        assert result.status == expected_status
        assert result.payload["threshold"] == 0.7
    finally:
        agent.unload()


@pytest.mark.asyncio
async def test_reviewer_missing_required_payload_field_is_rejected(llm):
    agent = ReviewerAgent(config={}, dependencies={"llm_provider": llm, "mock_llm": llm})
    agent.load()
    try:
        event = _event(
            EventType.TICKET_DRAFT,
            0.9,
            {
                "case_id": "IQE-CASE-TEST",
                "log_excerpt": "assert failure",
                "category": "product_bug",
                "priority": "P1",
            },
        )
        with pytest.raises(SchemaValidationFailure):
            await agent.run(event)
    finally:
        agent.unload()


class RecordingLLM:
    plugin_id = "recording_llm"

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def chat_completion(self, messages, config):
        self.messages = messages
        return {
            "content": {"summary": "normalized", "noise": False, "confidence": 0.99},
            "model_loc": "mock",
            "model_name": "recording-llm",
            "latency_ms": 1,
            "cost_token": 1,
        }


@pytest.mark.parametrize(
    "agent_class",
    [
        MonitorAgent,
        TriageAgent,
        ReproductionAgent,
        TicketAgent,
        ReviewerAgent,
        ReportingAgent,
    ],
)
def test_all_agents_expose_multiline_prompt_config(agent_class):
    field = agent_class.config_schema["system_prompt"]
    assert field["multiline"] is True
    assert field["max_length"] == 12000
    assert field["default"]


@pytest.mark.asyncio
async def test_monitor_uses_plugin_prompt_and_records_prompt_meta():
    recorder = RecordingLLM()
    agent = MonitorAgent(
        config={"system_prompt": "CUSTOM MONITOR PROMPT"},
        dependencies={
            "llm_provider": recorder,
            "mock_llm": recorder,
            "prompt_source": "plugin",
        },
    )
    agent.load()
    try:
        event = MockJenkinsPlugin(config={}).build_alert("IQE-CASE-001")
        result = await agent.run(event)
        assert recorder.messages[0] == {
            "role": "system",
            "content": "CUSTOM MONITOR PROMPT",
        }
        assert result.payload["prompt_source"] == "plugin"
        assert result.payload["prompt_version"]
        assert len(result.payload["prompt_hash"]) == 12
        assert result.payload["prompt_text"] == "CUSTOM MONITOR PROMPT"
    finally:
        agent.unload()


@pytest.mark.asyncio
async def test_stage_prompt_source_is_recorded():
    recorder = RecordingLLM()
    agent = MonitorAgent(
        config={"system_prompt": "STAGE MONITOR PROMPT"},
        dependencies={
            "llm_provider": recorder,
            "mock_llm": recorder,
            "prompt_source": "stage",
        },
    )
    agent.load()
    try:
        event = MockJenkinsPlugin(config={}).build_alert("IQE-CASE-001")
        result = await agent.run(event)
        assert recorder.messages[0]["content"] == "STAGE MONITOR PROMPT"
        assert result.payload["prompt_source"] == "stage"
        assert result.payload["prompt_text"] == "STAGE MONITOR PROMPT"
    finally:
        agent.unload()


@pytest.mark.asyncio
async def test_reproduction_preserves_upstream_confidence(llm):
    agent = ReproductionAgent(
        config={},
        dependencies={
            "llm_provider": llm,
            "mock_llm": llm,
            "tool": MockJarvisPlugin(config={}),
        },
    )
    agent.load()
    try:
        event = _event(
            EventType.TRIAGE_RESULT,
            0.6,
            {
                "category": "unknown",
                "root_cause": "unclear",
                "log_excerpt": "ambiguous failure",
                "case_id": "IQE-CASE-019",
                "title": "low",
            },
        )
        result = await agent.run(event)
        assert result.confidence == 0.6
        assert result.status == EventStatus.PASSED
    finally:
        agent.unload()
