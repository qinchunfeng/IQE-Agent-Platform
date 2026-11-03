"""Reporting Agent:输出 Trace 汇总与业务指标。

文档 4.2 最后一个 Agent;文档未定义 report_item 字段【已确认 Q23】。
TAT 口径见【已确认 Q12】:Mock 模式使用文档场景的模拟耗时,并在 payload 标注来源。
"""

from __future__ import annotations

from typing import Any

from ...models.event import EventEnvelope, EventStatus
from .base import IQEAgent, require_str


class ReportingAgent(IQEAgent):
    plugin_id = "reporting_agent"
    display_name = "Reporting Agent"
    description = "汇总本次流水线结果与 TAT 指标"
    input_event_types = ["review_result"]
    output_event_type = "report_item"
    payload_required_fields = ("case_id", "tat_seconds", "tat_source", "summary")
    dependencies = {"llm_provider": ["qoder_cn", "mock_llm"]}

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        run_context = self.dependencies.get("run_context") or {}
        tat_seconds = int(run_context.get("tat_seconds", 0))
        context = {
            "case_id": event.payload.get("case_id"),
            "category": event.payload.get("category"),
            "confidence": event.confidence,
            "ticket_key": run_context.get("ticket_key"),
            "tat_seconds": tat_seconds,
            "knowledge_hit": event.payload.get("kb_hit", False),
        }
        model_result, fallback_reason = await self.call_llm("report", context)
        content = model_result["content"]

        payload = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "category": event.payload.get("category"),
            "confidence": event.confidence,
            "ticket_key": run_context.get("ticket_key"),
            "tat_seconds": tat_seconds,
            "tat_source": run_context.get("tat_source", "measured"),
            "knowledge_hit": event.payload.get("kb_hit", False),
            "summary": require_str(content, "summary"),
        }
        return self.build_event(
            event,
            confidence=event.confidence,
            status=EventStatus.PASSED,
            payload=payload,
            model_result=model_result,
            fallback_reason=fallback_reason,
        )
