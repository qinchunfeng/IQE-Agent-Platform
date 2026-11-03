"""Reproduction Agent:调用复现工具。

文档 4.2:reproduction_agent 使用 jarvis_mock。
文档未定义工具返回结构【已确认 Q2】;未能复现时按 rejected 停止流水线。
"""

from __future__ import annotations

from typing import Any

from ...errors import ToolExecutionError
from ...models.event import EventEnvelope, EventStatus
from .base import IQEAgent


class ReproductionAgent(IQEAgent):
    plugin_id = "reproduction_agent"
    display_name = "Reproduction Agent"
    description = "调用 Jarvis 复现工具,过滤环境/flaky 噪声"
    input_event_types = ["triage_result"]
    output_event_type = "repro_result"
    payload_required_fields = ("case_id", "category", "reproduced", "attempts")
    dependencies = {
        "llm_provider": ["qoder_cn", "mock_llm"],
        "tool": ["jarvis_mock"],
    }

    async def run(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = self.ensure_input(input_event)
        tool = self.dependencies.get("tool")
        if tool is None:
            raise ToolExecutionError("未注入 jarvis_mock 工具")

        category = str(event.payload.get("category", "unknown"))
        try:
            tool_result = tool.reproduce(
                {
                    "category": category,
                    "log_excerpt": event.payload.get("log_excerpt", ""),
                    "case_id": event.payload.get("case_id"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - 工具故障需转为领域错误并进入 Trace
            raise ToolExecutionError(f"复现工具执行失败: {exc.__class__.__name__}") from exc

        if not isinstance(tool_result, dict) or "reproduced" not in tool_result:
            raise ToolExecutionError("复现工具返回结构不合法")

        context = {
            "case_id": event.payload.get("case_id"),
            "category": category,
            "root_cause": event.payload.get("root_cause"),
            "log_excerpt": event.payload.get("log_excerpt", ""),
            "tool_result": tool_result,
        }
        model_result, fallback_reason = await self.call_llm("reproduction", context)
        content = model_result["content"]

        reproduced = bool(tool_result["reproduced"])
        # 【已确认 Q4】文档未定义链路置信度传递规则;Demo 采用“沿链传递 Triage 置信度”：
        # 0.75/0.92/0.6 均原样进入 Reviewer,保证场景 2/3 的阈值行为与文档一致。
        confidence = event.confidence
        if not reproduced:
            confidence = min(confidence, 0.55)

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
            "reproduced": reproduced,
            "attempts": int(tool_result.get("attempts", 1)),
            "reproduction_summary": content.get("summary") or tool_result.get("summary"),
        }
        return self.build_event(
            event,
            confidence=confidence,
            status=EventStatus.PASSED if reproduced else EventStatus.REJECTED,
            payload=payload,
            model_result=model_result,
            fallback_reason=fallback_reason,
        )
