"""Triage Agent:根因分诊 + 知识库检索。

文档 4.2/6 场景 3:知识库命中后提升置信度并缩短耗时。
文档未定义分类枚举与知识库检索算法【已确认 Q2/Q7】。
"""

from __future__ import annotations

from typing import Any

from ...models.event import EventEnvelope, EventStatus
from .base import IQEAgent, require_number, require_str


class TriageAgent(IQEAgent):
    plugin_id = "triage_agent"
    display_name = "Triage Agent"
    description = "日志分诊、知识库检索、输出根因与置信度"
    input_event_types = ["monitor_alert"]
    output_event_type = "triage_result"
    payload_required_fields = ("case_id", "log_excerpt", "category", "root_cause")
    dependencies = {
        "llm_provider": ["qoder_cn", "mock_llm"],
        "knowledge_base": ["memory_vector_kb", "milvus"],
    }

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        log_excerpt = str(event.payload.get("log_excerpt", ""))

        kb = self.dependencies.get("knowledge_base")
        kb_entries = kb.search(log_excerpt) if kb is not None and log_excerpt else []

        context = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "job_name": event.payload.get("job_name"),
            "log_excerpt": log_excerpt,
            "kb_hits": [
                {
                    "entry_id": entry["entry_id"],
                    "title": entry["title"],
                    "category": entry["category"],
                    "score": entry["score"],
                    "content": entry["content"][:500],
                }
                for entry in kb_entries
            ],
        }
        model_result, fallback_reason = await self.call_llm("triage", context)
        content = model_result["content"]

        category = require_str(content, "category")
        confidence = require_number(content, "confidence")
        root_cause = require_str(content, "root_cause")
        kb_hit = bool(content.get("kb_hit", False))
        kb_entry_id = content.get("kb_entry_id")
        if kb_hit and not kb_entry_id and kb_entries:
            kb_entry_id = kb_entries[0]["entry_id"]

        payload = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "job_name": event.payload.get("job_name"),
            "log_excerpt": log_excerpt,
            "artifact_url": event.payload.get("artifact_url"),
            "category": category,
            "root_cause": root_cause,
            "confidence_reason": content.get("confidence_reason"),
            "kb_hit": kb_hit,
            "kb_entry_id": kb_entry_id,
            "kb_hits": [
                {"entry_id": entry["entry_id"], "score": entry["score"]}
                for entry in kb_entries
            ],
            "log_summary": content.get("log_summary", log_excerpt),
        }

        evidence_links = list(event.evidence_links)
        if kb_entry_id:
            evidence_links.append(f"kb://knowledge/{kb_entry_id}")

        return self.build_event(
            event,
            confidence=confidence,
            status=EventStatus.PASSED,
            payload=payload,
            model_result=model_result,
            evidence_links=evidence_links,
            fallback_reason=fallback_reason,
        )
