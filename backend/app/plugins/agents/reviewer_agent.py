"""Reviewer Agent:人工卡点判定。

文档 7.2:置信度低于阈值(默认 0.7)自动流转人工节点。
文档场景 2:低置信度事件在 Reviewer 节点暂停,状态 handover_human。
文档场景 3:0.75 案例仍需在 Reviewer 节点可操作(矛盾 C2),因此 UI 在
Reviewer 阶段到达后即允许“标记入库知识库”。
"""

from __future__ import annotations

from typing import Any

from ...config import DEFAULT_CONFIDENCE_THRESHOLD
from ...models.event import EventEnvelope, EventStatus
from ..capabilities import as_knowledge
from .base import IQEAgent, require_str


class ReviewerAgent(IQEAgent):
    plugin_id = "reviewer_agent"
    display_name = "Reviewer Agent"
    description = "质量卡点:高置信度自动通过,低置信度转人工"
    input_event_types = ["ticket_draft"]
    output_event_type = "review_result"
    payload_required_fields = (
        "case_id",
        "decision",
        "threshold",
        "ticket_title",
        "review_summary",
    )
    dependencies = {
        "llm_provider": ["qoder_cn", "mock_llm"],
        "knowledge_base": ["memory_vector_kb", "milvus"],
    }
    config_schema = {
        # 文档 7.2:默认阈值 0.7
        "confidence_threshold": {
            "type": "number",
            "label": "置信度阈值",
            "default": DEFAULT_CONFIDENCE_THRESHOLD,
            "min": 0,
            "max": 1,
            "required": False,
        }
    }

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        threshold = float(
            self.config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
        )

        kb = as_knowledge(self.injected("knowledge_base"))
        query = f"{event.payload.get('ticket_title', '')} {event.payload.get('log_excerpt', '')}"
        kb_entries = kb.search(query) if kb is not None and query.strip() else []

        context = {
            "confidence": event.confidence,
            "threshold": threshold,
            "category": event.payload.get("category"),
            "ticket_title": event.payload.get("ticket_title"),
            "priority": event.payload.get("priority"),
            "kb_hits": [entry["entry_id"] for entry in kb_entries],
        }
        model_result, fallback_reason = await self.call_llm("review", context)
        content = model_result["content"]

        # 文档 7.2 原文“低于阈值”→ 阈值边界自动通过
        decision = "pass" if event.confidence >= threshold else "handover_human"
        payload = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "job_name": event.payload.get("job_name"),
            "log_excerpt": event.payload.get("log_excerpt"),
            "artifact_url": event.payload.get("artifact_url"),
            "category": event.payload.get("category"),
            "root_cause": event.payload.get("root_cause"),
            "kb_hit": event.payload.get("kb_hit", False),
            "kb_entry_id": event.payload.get("kb_entry_id"),
            "draft_id": event.payload.get("draft_id"),
            "ticket_title": event.payload.get("ticket_title"),
            "ticket_description": event.payload.get("ticket_description"),
            "priority": event.payload.get("priority"),
            "decision": decision,
            "threshold": threshold,
            "review_summary": require_str(content, "summary"),
            "kb_references": [entry["entry_id"] for entry in kb_entries],
        }
        evidence_links = list(event.evidence_links)
        evidence_links.extend(f"kb://knowledge/{entry['entry_id']}" for entry in kb_entries)

        return self.build_event(
            event,
            confidence=event.confidence,
            status=EventStatus.PASSED
            if decision == "pass"
            else EventStatus.HANDOVER_HUMAN,
            payload=payload,
            model_result=model_result,
            evidence_links=evidence_links,
            fallback_reason=fallback_reason,
        )
