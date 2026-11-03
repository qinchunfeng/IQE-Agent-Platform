"""Monitor Agent:归一化 CI 失败事件。

文档 4.2 首个 Agent;文档事件枚举没有独立的 monitor 输出类型【已确认 Q3】,
因此输出仍为 monitor_alert。
"""

from __future__ import annotations

from typing import Any

from ...models.event import EventEnvelope, EventStatus
from .base import IQEAgent, require_number, require_str


class MonitorAgent(IQEAgent):
    plugin_id = "monitor_agent"
    display_name = "Monitor Agent"
    description = "接收 CI 失败事件,归一化并做初步噪声判断"
    input_event_types = ["monitor_alert"]
    output_event_type = "monitor_alert"
    payload_required_fields = ("monitor_summary", "noise")
    dependencies = {"llm_provider": ["qoder_cn", "mock_llm"]}

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        context = {
            "case_id": event.payload.get("case_id"),
            "title": event.payload.get("title"),
            "job_name": event.payload.get("job_name"),
            "log_excerpt": event.payload.get("log_excerpt", ""),
        }
        model_result, fallback_reason = await self.call_llm("monitor", context)
        content = model_result["content"]

        noise = bool(content.get("noise", False))
        payload = dict(event.payload)
        payload["monitor_summary"] = require_str(content, "summary")
        payload["noise"] = noise
        return self.build_event(
            event,
            confidence=require_number(content, "confidence"),
            status=EventStatus.REJECTED if noise else EventStatus.PASSED,
            payload=payload,
            model_result=model_result,
            fallback_reason=fallback_reason,
        )
