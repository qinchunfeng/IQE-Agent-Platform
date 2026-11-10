"""输入源实时监控循环。

【待确认 Q24】Airflow/外部日志文件属于轮询型输入源:
- 后台循环按插件配置的 poll_interval_seconds 调用 collect_alerts();
- 每个事件通过 PipelineService.submit_external_event() 创建 Run;
- Mock Jenkins 仍走现有推送 API,不参与轮询。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from ..errors import DomainError, PluginUnavailableError
from ..logging_config import get_logger
from ..plugins.capabilities import as_alert_source
from ..plugins.registry import PluginRegistry
from .pipeline_service import PipelineService

logger = get_logger("iqe.source_monitor")


class SourceMonitor:
    def __init__(self, registry: PluginRegistry, service: PipelineService) -> None:
        self.registry = registry
        self.service = service
        self._task: asyncio.Task[Any] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        # 等应用完成初始化,避免与插件健康检查并发抢占。
        await asyncio.sleep(5)
        while True:
            try:
                await self.poll_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 监控循环不能退出
                logger.warning(
                    "source monitor loop error",
                    extra={"error": exc.__class__.__name__},
                )
            await asyncio.sleep(self._interval())

    def _interval(self) -> float:
        intervals: list[float] = []
        for plugin_id in self.registry.input_source_ids():
            if not self.registry.is_enabled(plugin_id):
                continue
            plugin = self.registry.get(plugin_id)
            if not getattr(plugin, "capabilities", {}).get("polling"):
                continue
            intervals.append(float(plugin.config.get("poll_interval_seconds", 60)))
        return max(5.0, min(intervals) if intervals else 60.0)

    async def poll_all(
        self, limit: int | None = None, lookback_minutes: int | None = None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for plugin_id in self.registry.input_source_ids():
            results.extend(
                await self.poll_plugin(
                    plugin_id, limit=limit, lookback_minutes=lookback_minutes
                )
            )
        return results

    async def poll_plugin(
        self,
        plugin_id: str,
        *,
        limit: int | None = None,
        lookback_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            if not self.registry.is_enabled(plugin_id):
                raise PluginUnavailableError(f"输入源插件已禁用: {plugin_id}")
            if not self.registry.is_type(plugin_id, "input_source"):
                raise PluginUnavailableError(f"插件不是输入源: {plugin_id}")
            source = as_alert_source(self.registry.get(plugin_id))
            if source is None:
                raise PluginUnavailableError(f"输入源未实现事件采集能力: {plugin_id}")
            if not source.capabilities.get("polling"):
                return []
            try:
                events = await source.collect_alerts(
                    limit=limit, lookback_minutes=lookback_minutes
                )
            except PluginUnavailableError as exc:
                logger.warning(
                    "input source poll failed",
                    extra={"plugin_id": plugin_id, "error": exc.message},
                )
                raise

            results: list[dict[str, Any]] = []
            for event in events:
                try:
                    result = await self.service.submit_external_event(event, plugin_id)
                except DomainError as exc:
                    logger.error(
                        "input source event rejected",
                        extra={"plugin_id": plugin_id, "error": exc.message},
                    )
                    continue
                results.append(
                    {
                        "source_id": plugin_id,
                        "trace_id": result["trace_id"],
                        "run_id": result["run_id"],
                        "case_id": result.get("case_id"),
                        "event_id": result["event"].event_id,
                    }
                )
            return results
