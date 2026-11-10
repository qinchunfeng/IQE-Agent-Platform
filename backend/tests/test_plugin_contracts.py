"""插件能力契约与类型收口的回归测试(FEATURES.md Task 24)。

这里不重复 mypy 的工作,只锁住两件"以后会被悄悄还回去"的事:
1. backend/mypy.ini 不得重新出现 per-module `disable_error_code` 豁免;
2. 内核不得 import 具体插件类——只能经过 registry / base / capabilities。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.plugins.airflow_input import AirflowInputSourcePlugin
from app.plugins.base import BasePlugin
from app.plugins.capabilities import (
    as_alert_source,
    as_knowledge,
    as_notifier,
    as_orchestrator,
    as_ticket_tool,
)
from app.plugins.feishu_notifier import FeishuNotifierPlugin
from app.plugins.memory_orchestrator import MemoryOrchestratorPlugin
from app.plugins.memory_vector_kb import MemoryVectorKBPlugin
from app.plugins.mock_jira import MockJiraPlugin

BACKEND = Path(__file__).resolve().parents[1]
# 内核允许依赖的插件侧模块:注册中心、契约基类、能力协议。
KERNEL_ALLOWED_PLUGIN_IMPORTS = {"registry", "base", "capabilities"}
KERNEL_FILES = [
    BACKEND / "app" / "main.py",
    BACKEND / "app" / "db.py",
    BACKEND / "app" / "security.py",
    *sorted((BACKEND / "app" / "services").glob("*.py")),
]


def test_mypy_config_has_no_module_exemptions() -> None:
    config = (BACKEND / "mypy.ini").read_text(encoding="utf-8")
    assert "disable_error_code" not in config, "类型豁免回来了:见 PROGRESS.md I4 / Task 24"
    assert not re.search(r"^\[mypy-app\.", config, re.MULTILINE), "出现了 per-module 豁免段落"


def test_kernel_does_not_import_concrete_plugin_modules() -> None:
    offenders: list[str] = []
    for path in KERNEL_FILES:
        for match in re.finditer(
            r"from\s+\.+plugins\.([a-z_]+)\s+import|import\s+app\.plugins\.([a-z_]+)",
            path.read_text(encoding="utf-8"),
        ):
            module = match.group(1) or match.group(2)
            if module not in KERNEL_ALLOWED_PLUGIN_IMPORTS:
                offenders.append(f"{path.name}:{module}")
    assert offenders == [], f"内核直接依赖了具体插件模块: {offenders}"


def test_capability_guards_accept_real_plugins() -> None:
    assert as_knowledge(MemoryVectorKBPlugin()) is not None
    assert as_ticket_tool(MockJiraPlugin()) is not None
    assert as_orchestrator(MemoryOrchestratorPlugin()) is not None
    assert as_alert_source(AirflowInputSourcePlugin()) is not None
    assert as_notifier(FeishuNotifierPlugin()) is not None


def test_capability_guards_reject_plugins_without_the_method() -> None:
    plain = BasePlugin()
    assert as_knowledge(plain) is None
    assert as_ticket_tool(plain) is None
    assert as_orchestrator(plain) is None
    assert as_alert_source(plain) is None
    assert as_notifier(plain) is None
    assert as_knowledge(None) is None
