"""Mock Jarvis 工具插件(复现工具)。

文档 4.2 中 reproduction_agent 使用 jarvis_mock;文档未定义工具接口【已确认 Q2】。
"""

from __future__ import annotations

from typing import Any

from .base import ToolPlugin


class MockJarvisPlugin(ToolPlugin):
    plugin_id = "jarvis_mock"
    display_name = "Mock Jarvis"
    description = "模拟复现工具,环境类/flaky 类失败不复现(文档 7.4)"
    config_schema = {}

    async def health(self) -> tuple[bool, str]:
        return True, "Mock Jarvis ready"

    def reproduce(self, case: dict[str, Any]) -> dict[str, Any]:
        category = str(case.get("category", "unknown"))
        reproduced = category not in {"environment", "flaky"}
        attempts = 1 if reproduced else 3
        return {
            "reproduced": reproduced,
            "attempts": attempts,
            "summary": (
                "在隔离环境重跑复现成功"
                if reproduced
                else f"{category} 类失败未能稳定复现,建议判定为噪声"
            ),
        }
