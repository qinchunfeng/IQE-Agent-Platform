"""内置内存编排器(默认,无外部依赖)。

文档 3.2 接口:
- start_pipeline(pipeline_def) -> run_id
- get_pipeline_status(run_id) -> dict
- stop_pipeline(run_id)
文档未定义 context 参数【Q11 已确认;Q8 外部编排契约待确认】,这里增加可选 context
以传递平台 run_id、trace_id 与输入事件,不改变文档要求的位置参数。
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from .. import db
from ..config import MAX_CONCURRENT_RUNS
from ..errors import NotFoundError, PluginUnavailableError
from .base import OrchestratorPlugin


class MemoryOrchestratorPlugin(OrchestratorPlugin):
    plugin_id = "memory_orchestrator"
    display_name = "内置编排引擎"
    description = "平台自带的内存编排器,无外部依赖(文档 4.1)"
    config_schema = {
        # 【已确认 Q21】超出上限的 Run 进入等待,但保持 running 状态,不新增枚举。
        "max_concurrent_runs": {
            "type": "integer",
            "label": "最大并发 Run 数",
            "default": MAX_CONCURRENT_RUNS,
            "min": 1,
            "max": 64,
            "required": False,
        }
    }

    def __init__(self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None):
        super().__init__(config, dependencies)
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancelled: set[str] = set()
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_limit: int | None = None

    def _concurrency_semaphore(self) -> asyncio.Semaphore:
        limit = int(self.config.get("max_concurrent_runs", MAX_CONCURRENT_RUNS))
        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit
        return self._semaphore

    async def start_pipeline(
        self, pipeline_def: dict[str, Any], context: dict[str, Any] | None = None
    ) -> str:
        runner = self.dependencies.get("runner")
        if not callable(runner):
            raise PluginUnavailableError("内置编排器未注入流水线执行器")
        run_id = str((context or {}).get("run_id") or uuid4())
        semaphore = self._concurrency_semaphore()

        async def run_with_limit() -> None:
            async with semaphore:
                await runner(run_id, pipeline_def)

        task = asyncio.create_task(run_with_limit())
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run_id

    async def get_pipeline_status(self, run_id: str) -> dict[str, Any]:
        run = db.get_run(run_id)
        if run is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        return run

    async def stop_pipeline(self, run_id: str) -> None:
        run = db.get_run(run_id)
        if run is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        self._cancelled.add(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        db.update_run(
            run_id,
            status="stopped",
            finished_at=db.utc_now_iso(),
            current_stage=run.get("current_stage"),
        )

    def is_cancelled(self, run_id: str) -> bool:
        run = db.get_run(run_id)
        return run_id in self._cancelled or (run is not None and run["status"] == "stopped")
