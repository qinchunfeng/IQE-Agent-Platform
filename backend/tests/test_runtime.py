"""运行时隔离、超时与并发上限测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.plugins.base import BasePlugin
from app.plugins.memory_orchestrator import MemoryOrchestratorPlugin


class SlowPlugin(BasePlugin):
    plugin_id = "slow_plugin"
    display_name = "Slow Plugin"
    plugin_type = "tool"

    async def work(self) -> str:
        await asyncio.sleep(0.3)
        return "done"


@pytest.mark.asyncio
async def test_run_isolated_timeout_fails_fast():
    plugin = SlowPlugin()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await plugin.run_isolated(plugin.work, timeout=0.05)
    finally:
        plugin.unload()


@pytest.mark.asyncio
async def test_memory_orchestrator_enforces_concurrency_limit():
    active = 0
    peak = 0

    async def runner(_run_id: str, _pipeline_def: dict[str, Any]) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1

    plugin = MemoryOrchestratorPlugin(
        config={"max_concurrent_runs": 1},
        dependencies={"runner": runner},
    )
    plugin.load()
    try:
        await plugin.start_pipeline({"pipeline_id": "p1"})
        await plugin.start_pipeline({"pipeline_id": "p2"})
        await asyncio.sleep(0.2)
        assert peak == 1
    finally:
        plugin.unload()
