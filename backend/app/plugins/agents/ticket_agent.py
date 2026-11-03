"""Ticket Agent:生成工单草案。

文档 6 场景 2:Agent 不直接写 Jira,人工有最终决定权。
因此这里只调用 Mock Jira 的 create_draft,不创建正式工单【已确认 Q5】。
"""

from __future__ import annotations

from typing import Any

from ...errors import ToolExecutionError
from ...models.event import EventEnvelope, EventStatus
from .base import IQEAgent, require_str


class TicketAgent(IQEAgent):
    plugin_id = "ticket_agent"
    display_name = "Ticket Agent"
    description = "生成 Jira 工单草案,不直接写入 Jira"
    input_event_types = ["repro_result"]
    output_event_type = "ticket_draft"
    payload_required_fields = (
        "case_id",
        "draft_id",
        "ticket_title",
        "ticket_description",
        "priority",
    )
    dependencies = {
        "llm_provider": ["qoder_cn", "mock_llm"],
        "tool": ["jira_mock"],
    }

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        tool = self.dependencies.get("tool")
        if tool is None:
            raise ToolExecutionError("未注入 jira_mock 工具")

        category = str(event.payload.get("category", "unknown"))
        context = {
            "case_id": event.payload.get("case_id"),
            "case_title": event.payload.get("title"),
            "category": category,
            "root_cause": event.payload.get("root_cause"),
            "log_excerpt": event.payload.get("log_excerpt", ""),
            "confidence": event.confidence,
            "reproduced": event.payload.get("reproduced"),
        }
        model_result, fallback_reason = await self.call_llm("ticket", context)
        content = model_result["content"]

        title = require_str(content, "title")
        description = require_str(content, "description")
        priority = require_str(content, "priority")
        draft = {
            "trace_id": event.trace_id,
            "title": title,
            "description": description,
            "priority": priority,
            "category": category,
            "source_case_id": event.payload.get("case_id"),
            "confidence": event.confidence,
        }
        try:
            draft_result = tool.create_draft(draft)
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"Jira 草稿创建失败: {exc.__class__.__name__}") from exc

        payload = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "job_name": event.payload.get("job_name"),
            "log_excerpt": event.payload.get("log_excerpt"),
            "artifact_url": event.payload.get("artifact_url"),
            "category": category,
            "root_cause": event.payload.get("root_cause"),
            "kb_hit": event.payload.get("kb_hit", False),
            "kb_entry_id": event.payload.get("kb_entry_id"),
            "draft_id": draft_result.get("draft_id"),
            "ticket_title": title,
            "ticket_description": description,
            "priority": priority,
        }
        return self.build_event(
            event,
            confidence=event.confidence,
            status=EventStatus.PASSED,
            payload=payload,
            model_result=model_result,
            fallback_reason=fallback_reason,
        )
