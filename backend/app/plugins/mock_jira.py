"""Mock Jira 工具插件。

文档 7.4:无真实 Jira 时使用 Mock Jira。
文档未定义草稿/工单字段与工单号规则【Q15 已确认;Q5 真实 Jira 契约待确认】;临时基线:
- ticket_agent 只调用 create_draft 生成草稿,不直接写 Jira;
- Reviewer 通过后由平台调用 create_ticket 写入 Mock Jira。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .. import db
from .base import ToolPlugin


class MockJiraPlugin(ToolPlugin):
    plugin_id = "jira_mock"
    display_name = "Mock Jira"
    description = "模拟 Jira 工具,演示工单草案与创建(文档 7.4)"
    config_schema = {
        # 【已确认 Q15】项目 Key 文档未定义,仅用于展示工单号。
        "project_key": {
            "type": "string",
            "label": "Jira 项目 Key",
            "default": "IQE",
            "required": False,
        }
    }

    async def health(self) -> tuple[bool, str]:
        return True, "Mock Jira ready"

    def create_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        return {
            "draft_id": str(uuid4()),
            "status": "draft",
            "title": draft["title"],
            "description": draft["description"],
            "priority": draft["priority"],
            "trace_id": draft["trace_id"],
        }

    def create_ticket(self, draft: dict[str, Any]) -> dict[str, Any]:
        project_key = self.config.get("project_key", "IQE")
        number = db.count_tickets() + 1
        ticket = {
            "ticket_id": str(uuid4()),
            "ticket_key": f"{project_key}-{number}",
            "trace_id": draft["trace_id"],
            "title": draft["title"],
            "status": "created",
            "payload": {
                "description": draft.get("description", ""),
                "priority": draft.get("priority"),
                "draft_id": draft.get("draft_id"),
                "category": draft.get("category"),
            },
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        db.save_ticket(ticket)
        return ticket
