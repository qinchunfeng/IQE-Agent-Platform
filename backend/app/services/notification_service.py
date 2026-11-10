"""Run 结束后的通知投递服务。

平台内核只负责在状态变更时调用一次通知;具体渠道由工具插件实现。
当前只接入 feishu_notifier,插件缺失/禁用/未配置时静默跳过,发送失败只记录
``run_notifications`` 与日志,绝不影响流水线终态。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..errors import NotificationError, PluginUnavailableError
from ..logging_config import get_logger
from ..models.event import EventType
from ..plugins.capabilities import as_notifier
from ..plugins.registry import PluginRegistry

logger = get_logger("iqe.notification")

NOTIFIER_PLUGIN_ID = "feishu_notifier"
NOTIFIABLE_STATUSES = {"completed", "rejected", "failed", "stopped", "waiting_human"}


class NotificationService:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self._tasks: set[asyncio.Task[Any]] = set()

    def schedule(self, run_id: str, status: str, reason: str | None = None) -> None:
        """后台投递,不阻塞 Run 状态流转。"""

        if status not in NOTIFIABLE_STATUSES:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.notify_run(run_id, status, reason))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def notify_run(
        self, run_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any] | None:
        if not self.registry.has(NOTIFIER_PLUGIN_ID):
            return None
        if not self.registry.is_enabled(NOTIFIER_PLUGIN_ID):
            return None

        try:
            plugin = as_notifier(self.registry.get(NOTIFIER_PLUGIN_ID))
            if plugin is None:
                raise PluginUnavailableError(f"插件未实现通知投递能力: {NOTIFIER_PLUGIN_ID}")
        except Exception as exc:  # noqa: BLE001 - 通知失败不能影响主链路
            logger.warning(
                "notifier unavailable",
                extra={"run_id": run_id, "error": exc.__class__.__name__},
            )
            return None

        if not plugin.enabled_for_status(status):
            return None
        configured, message = plugin.is_configured()
        if not configured:
            logger.info(
                "notifier not configured, skipped",
                extra={"run_id": run_id, "status": status, "reason": message},
            )
            return None

        if not db.claim_run_notification(run_id, NOTIFIER_PLUGIN_ID, status):
            # 同一 Run 的同一状态只投递一次,避免重复回调/重试叠加。
            return self.get_notification(run_id, status)

        run = db.get_run(run_id)
        if run is None:
            return None

        try:
            report = self.build_report(run, status, reason)
            result = await plugin.send_report(report)
        except NotificationError as exc:
            attempts = _attempts(exc)
            db.update_run_notification(
                run_id,
                NOTIFIER_PLUGIN_ID,
                status,
                state="failed",
                attempts=attempts,
                error=exc.message,
            )
            logger.warning(
                "notification failed",
                extra={
                    "run_id": run_id,
                    "status": status,
                    "error": exc.message,
                    "attempts": attempts,
                },
            )
        except Exception as exc:  # noqa: BLE001 - 通知失败不能影响主链路
            db.update_run_notification(
                run_id,
                NOTIFIER_PLUGIN_ID,
                status,
                state="failed",
                attempts=0,
                error=exc.__class__.__name__,
            )
            logger.warning(
                "notification crashed",
                extra={"run_id": run_id, "status": status, "error": exc.__class__.__name__},
            )
        else:
            attempts = int((result or {}).get("attempts") or 1)
            db.update_run_notification(
                run_id,
                NOTIFIER_PLUGIN_ID,
                status,
                state="sent",
                attempts=attempts,
                error=None,
            )
            logger.info(
                "notification sent",
                extra={"run_id": run_id, "status": status},
            )
        return self.get_notification(run_id, status)

    def get_notification(self, run_id: str, status: str) -> dict[str, Any] | None:
        for item in db.list_run_notifications(run_id):
            if item["plugin_id"] == NOTIFIER_PLUGIN_ID and item["status"] == status:
                return item
        return None

    # ---------------------------------------------------------------- report

    def build_report(
        self, run: dict[str, Any], status: str, reason: str | None = None
    ) -> dict[str, Any]:
        run_id = run["run_id"]
        events = db.list_events(run_id)
        triage = db.get_latest_event(run_id, EventType.TRIAGE_RESULT.value)
        review = db.get_latest_event(run_id, EventType.REVIEW_RESULT.value)
        report = db.get_latest_event(run_id, EventType.REPORT_ITEM.value)
        ticket = db.get_ticket_by_trace(run["trace_id"])
        input_payload = run.get("input_event", {}).get("payload", {})
        confidence_event = review or triage
        report_payload = (report or {}).get("payload", {})

        actual = _elapsed_seconds(run["started_at"])
        simulated = _simulated_seconds(events)
        tat_seconds = int(report_payload.get("tat_seconds") or max(actual, simulated))
        tat_source = report_payload.get("tat_source") or (
            "simulated_mock" if simulated > actual + 0.5 else "measured"
        )

        return {
            "run_id": run_id,
            "trace_id": run["trace_id"],
            "pipeline_id": run["pipeline_id"],
            "status": status,
            "case_id": input_payload.get("case_id"),
            "title": input_payload.get("title") or input_payload.get("job_name"),
            "category": (triage or {}).get("payload", {}).get("category"),
            "confidence": confidence_event.get("confidence") if confidence_event else None,
            "ticket_key": ticket["ticket_key"] if ticket else None,
            "tat_seconds": tat_seconds,
            "tat_source": tat_source,
            "human_reason": run.get("human_reason"),
            "error_reason": run.get("error_reason"),
            "reason": reason,
            "input_source": run.get("input_source"),
            "orchestrator_used": run.get("orchestrator_used"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "stages": _stage_summary(run, events),
        }


def _stage_summary(run: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pipeline = db.get_pipeline(run["pipeline_id"])
    stages = (pipeline or {}).get("definition", {}).get("stages", [])
    summary: list[dict[str, Any]] = []
    cursor = 0
    for stage in stages:
        matched = None
        for index in range(cursor, len(events)):
            if events[index].get("source_agent") == stage.get("agent"):
                matched = events[index]
                cursor = index + 1
                break
        if matched is not None:
            stage_status = str(matched.get("status"))
        elif run.get("current_stage") == stage.get("agent"):
            stage_status = "running"
        else:
            stage_status = "pending"
        summary.append(
            {
                "agent": stage.get("agent"),
                "status": stage_status,
                "confidence": matched.get("confidence") if matched else None,
            }
        )
    return summary


def _attempts(exc: NotificationError) -> int:
    details = exc.details if isinstance(exc.details, dict) else {}
    return int(details.get("attempts") or 0)


def _elapsed_seconds(started_at: str | None) -> float:
    if not started_at:
        return 0.0
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


def _simulated_seconds(events: list[dict[str, Any]]) -> float:
    return (
        sum(int(event.get("model_info", {}).get("latency_ms", 0)) for event in events) / 1000
    )
