"""Mock Jenkins 输入源插件。

文档 2 节输入源插件;文档 7.4 规定无真实 Jenkins 时使用 Mock Jenkins。
文档未定义输入源方法与事件 payload【已确认 Q2/Q18】。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..demo_cases import CASES, DEFAULT_CASE_ID, get_case
from ..errors import NotFoundError
from ..models.event import EventEnvelope, EventStatus, EventType, ModelInfo, ModelLoc
from .base import InputSourcePlugin


class MockJenkinsPlugin(InputSourcePlugin):
    plugin_id = "mock_jenkins"
    display_name = "Mock Jenkins"
    description = "模拟 Jenkins CI 失败事件输入源(文档 7.4 降级方案)"
    config_schema = {
        "default_case_id": {
            "type": "string",
            "label": "默认案例 ID",
            "default": DEFAULT_CASE_ID,
            "required": False,
        }
    }

    def list_cases(self) -> list[dict[str, Any]]:
        return [dict(case) for case in CASES]

    def build_alert(self, case_id: str | None = None) -> EventEnvelope:
        selected_id = case_id or self.config.get("default_case_id", DEFAULT_CASE_ID)
        case = get_case(selected_id)
        if case is None:
            raise NotFoundError(f"演示案例不存在: {selected_id}")

        trace_id = str(uuid4())
        artifact_url = (
            f"mock://jenkins/{case['job_name']}/{case['build_number']}/console"
        )
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type=EventType.MONITOR_ALERT,
            source_agent=self.plugin_id,
            timestamp=datetime.now(timezone.utc),
            trace_id=trace_id,
            confidence=1.0,
            evidence_links=[artifact_url],
            status=EventStatus.PENDING,
            model_info=ModelInfo(
                model_loc=ModelLoc.MOCK,
                model_name="mock-jenkins",
                latency_ms=0,
                cost_token=0,
            ),
            payload={
                "case_id": case["case_id"],
                "title": case["title"],
                "job_name": case["job_name"],
                "build_number": case["build_number"],
                "repository": case["repository"],
                "branch": case["branch"],
                "commit": case["commit"],
                "stage": case["stage"],
                "log_excerpt": case["log_excerpt"],
                "artifact_url": artifact_url,
            },
        )
