"""平台流水线编排服务。

严格按文档 4.2 的 6 阶段顺序串行执行;文档 6 的 5 个演示场景由本服务支撑:
- 事件推送 → Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting
- 置信度 < 0.7 在 Reviewer 暂停,人工批准/驳回
- Reviewer 阶段到达后可标记入库知识库
- Airflow/Qoder CN 不可用时按文档 7.4 降级

文档未定义的 API/统计口径集中标注【待确认】。
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .. import db
from ..config import (
    AGENT_TIMEOUT_SECONDS,
    DOC_BASELINES,
    local_now,
    local_timezone_name,
)
from ..errors import (
    ConfigurationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PluginUnavailableError,
    SchemaValidationFailure,
    ToolExecutionError,
)
from ..logging_config import get_logger
from ..models.api import PipelineDefinition
from ..models.event import EventEnvelope, EventStatus, EventType, validate_event
from ..plugins.registry import PluginRegistry
from .fallback import resolve_llm, resolve_optional_plugin, resolve_orchestrator
from .notification_service import NotificationService

logger = get_logger("iqe.pipeline")

DEFAULT_PIPELINE_ID = "iqe_validation_v1"
TERMINAL_STATUSES = {"completed", "rejected", "failed", "stopped"}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


LEGACY_JENKINS_SOURCE = "jenkins_webhook"
DEFAULT_INPUT_SOURCE = "mock_jenkins"
SOURCE_LABELS = {
    "mock_jenkins": "Jenkins / Mock Jenkins",
    "airflow_input": "Airflow 输入源",
    "file_input": "外部日志文件",
}


def normalize_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """兼容旧流水线并补齐画布输入源节点。

    【待确认 Q24】文档 4.2 只在 Monitor 阶段声明 input_source;多输入源是
    Demo 扩展。旧定义没有 sources 时,从 Monitor 的 input_source 推导一个节点。
    """

    data = copy.deepcopy(definition)
    if data.get("orchestrator") in (None, "airflow_orchestrator"):
        # Airflow 已改为输入源插件,不再作为编排器。
        data["orchestrator"] = "memory_orchestrator"

    stages = data.get("stages") or []
    for stage in stages:
        if stage.get("input_source") == LEGACY_JENKINS_SOURCE:
            stage["input_source"] = DEFAULT_INPUT_SOURCE

    sources = data.get("sources")
    if not sources:
        stage_source = next(
            (stage.get("input_source") for stage in stages if stage.get("input_source")),
            DEFAULT_INPUT_SOURCE,
        )
        plugin_id = (
            DEFAULT_INPUT_SOURCE
            if stage_source == LEGACY_JENKINS_SOURCE
            else str(stage_source or DEFAULT_INPUT_SOURCE)
        )
        sources = [
            {
                "source_id": plugin_id,
                "plugin_id": plugin_id,
                "label": SOURCE_LABELS.get(plugin_id, plugin_id),
                "enabled": True,
            }
        ]
    normalized_sources: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        item = dict(source)
        plugin_id = str(item.get("plugin_id") or item.get("source_id") or "").strip()
        if not plugin_id:
            continue
        item["plugin_id"] = plugin_id
        item["source_id"] = str(item.get("source_id") or plugin_id).strip()
        item["label"] = str(item.get("label") or SOURCE_LABELS.get(plugin_id, plugin_id))
        item["enabled"] = bool(item.get("enabled", True))
        normalized_sources.append(item)
    if not normalized_sources:
        normalized_sources = [
            {
                "source_id": DEFAULT_INPUT_SOURCE,
                "plugin_id": DEFAULT_INPUT_SOURCE,
                "label": SOURCE_LABELS[DEFAULT_INPUT_SOURCE],
                "enabled": True,
            }
        ]
    data["sources"] = normalized_sources
    return data


class PipelineService:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self.notifications = NotificationService(registry)

    # --------------------------------------------------------------- pipeline

    def create_pipeline(self, definition: PipelineDefinition) -> dict[str, Any]:
        data = normalize_definition(definition.model_dump())
        if not self.registry.has(data["orchestrator"]) or not self.registry.is_type(
            data["orchestrator"], "orchestrator"
        ):
            raise ConfigurationError(f"编排器不存在: {data['orchestrator']}")
        for index, stage in enumerate(data["stages"]):
            agent_id = stage["agent"]
            if not self.registry.has(agent_id) or not self.registry.is_agent(agent_id):
                raise ConfigurationError(f"阶段 {index + 1} 的 Agent 不存在: {agent_id}")
            for field in ("llm_provider", "knowledge_base", "tool"):
                plugin_id = stage.get(field)
                if plugin_id and not self.registry.has(plugin_id):
                    raise ConfigurationError(
                        f"阶段 {index + 1} 的 {field} 插件不存在: {plugin_id}"
                    )
            input_source = stage.get("input_source")
            if input_source and not self.registry.has(input_source):
                raise ConfigurationError(f"输入源插件不存在: {input_source}")
        seen_sources: set[str] = set()
        for source in data["sources"]:
            plugin_id = source["plugin_id"]
            if not self.registry.has(plugin_id) or not self.registry.is_type(
                plugin_id, "input_source"
            ):
                raise ConfigurationError(f"输入源插件不存在: {plugin_id}")
            if source["source_id"] in seen_sources:
                raise ConfigurationError(f"输入源节点重复: {source['source_id']}")
            seen_sources.add(source["source_id"])
        db.save_pipeline(data)
        return self.get_pipeline(data["pipeline_id"])

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        record = db.get_pipeline(pipeline_id)
        if record is None:
            raise NotFoundError(f"流水线不存在: {pipeline_id}")
        record["definition"] = normalize_definition(record["definition"])
        return record

    def list_pipelines(self) -> list[dict[str, Any]]:
        records = db.list_pipelines()
        for record in records:
            record["definition"] = normalize_definition(record["definition"])
        return records

    def _default_pipeline(self) -> dict[str, Any]:
        record = db.get_pipeline(DEFAULT_PIPELINE_ID)
        if record is None:
            pipelines = db.list_pipelines()
            if not pipelines:
                raise NotFoundError("尚未配置流水线")
            record = pipelines[0]
        record["definition"] = normalize_definition(record["definition"])
        return record

    def _pipeline_for_source(self, source_id: str) -> dict[str, Any]:
        """按输入源节点选择流水线;未匹配时使用默认流水线。"""

        for record in db.list_pipelines():
            definition = normalize_definition(record["definition"])
            for source in definition["sources"]:
                if not source.get("enabled", True):
                    continue
                if source_id in (source["source_id"], source["plugin_id"]):
                    record["definition"] = definition
                    return record
        return self._default_pipeline()

    # ------------------------------------------------------------------- push

    async def push_event(self, case_id: str | None = None) -> dict[str, Any]:
        """Mock Jenkins 入口;保留原 API 行为,内部统一走 submit_external_event。"""

        input_source = self.registry.get(DEFAULT_INPUT_SOURCE)
        event = input_source.build_alert(case_id)
        return await self.submit_external_event(event, DEFAULT_INPUT_SOURCE)

    async def submit_external_event(
        self, event: EventEnvelope | dict[str, Any], source_id: str
    ) -> dict[str, Any]:
        """输入源事件统一入口。

        Airflow / 外部日志文件轮询得到的 monitor_alert,与 Mock Jenkins 共用
        同一条 Run 创建、事件落库与内置编排器执行链路。
        """

        envelope = event if isinstance(event, EventEnvelope) else validate_event(event)
        pipeline_record = self._pipeline_for_source(source_id)
        return await self._start_run(envelope, pipeline_record["definition"], source_id)

    async def _start_run(
        self, event: EventEnvelope, pipeline_def: dict[str, Any], source_id: str
    ) -> dict[str, Any]:
        configured = pipeline_def.get("orchestrator", "memory_orchestrator")
        orchestrator, fallback_reason = await resolve_orchestrator(self.registry, configured)
        run_id = str(uuid4())
        run = {
            "run_id": run_id,
            "pipeline_id": pipeline_def["pipeline_id"],
            "trace_id": event.trace_id,
            "status": "running",
            "orchestrator_configured": configured,
            "orchestrator_used": orchestrator.plugin_id,
            "orchestrator_run_id": None,
            "fallback_reason": fallback_reason,
            "current_stage": None,
            "human_reason": None,
            "error_reason": None,
            "started_at": db.utc_now_iso(),
            "finished_at": None,
            "input_event": event.model_dump(mode="json"),
            "input_source": source_id,
        }
        db.create_run(run)
        event_dict = event.model_dump(mode="json")
        db.save_event(run_id, event.trace_id, event_dict)
        await self._publish(event_dict)

        context = {"run_id": run_id, "trace_id": event.trace_id, "input_event": event_dict}
        try:
            await orchestrator.start_pipeline(pipeline_def, context=context)
        except DomainError as exc:
            self._fail_run(run, exc)
            raise

        return {
            "run_id": run_id,
            "trace_id": event.trace_id,
            "case_id": event.payload.get("case_id", ""),
            "orchestrator_configured": configured,
            "orchestrator_effective": (db.get_run(run_id) or run)["orchestrator_used"],
            "fallback_reason": (db.get_run(run_id) or run)["fallback_reason"],
            "input_source": source_id,
            "event": event,
        }

    # ---------------------------------------------------------------- execute

    async def execute_run_task(self, run_id: str, pipeline_def: dict[str, Any]) -> None:
        run = db.get_run(run_id)
        if run is None:
            logger.error("run not found for execution", extra={"run_id": run_id})
            return
        try:
            input_event = validate_event(run["input_event"])
            run_context = self._build_run_context(run)
            await self._execute_stages(run, pipeline_def, 0, input_event, run_context)
        except asyncio.CancelledError:
            db.update_run(run_id, status="stopped", finished_at=db.utc_now_iso())
            self.notifications.schedule(run_id, "stopped")
            logger.info("pipeline cancelled", extra={"run_id": run_id})
            raise
        except DomainError as exc:
            self._fail_run(run, exc)
        except Exception as exc:  # noqa: BLE001 - 任务必须落 Trace,不能静默
            logger.exception("pipeline crashed", extra={"run_id": run_id})
            self._fail_run(run, exc)

    async def _execute_stages(
        self,
        run: dict[str, Any],
        pipeline_def: dict[str, Any],
        start_index: int,
        current_event: EventEnvelope,
        run_context: dict[str, Any],
    ) -> None:
        run_id = run["run_id"]
        stages = pipeline_def.get("stages", [])
        events = db.list_events(run_id)
        latency_total = sum(int(event.get("model_info", {}).get("latency_ms", 0)) for event in events)
        llm_cache: dict[str, tuple[Any, Any, str | None]] = {}

        for index in range(start_index, len(stages)):
            stage = stages[index]
            if self._is_cancelled(run_id):
                db.update_run(run_id, status="stopped", finished_at=db.utc_now_iso())
                self.notifications.schedule(run_id, "stopped")
                return

            db.update_run(run_id, current_stage=stage["agent"])
            dependencies = await self._build_dependencies(stage, run_context, llm_cache)
            # 阶段级 Prompt 覆盖优先于 Agent 插件配置;来源写入 payload 便于审计。
            overrides: dict[str, Any] = {}
            stage_prompt = str(stage.get("system_prompt") or "").strip()
            if stage_prompt:
                overrides["system_prompt"] = stage_prompt
            dependencies["prompt_source"] = "stage" if overrides else "plugin"
            agent = self.registry.create_agent(
                stage["agent"], dependencies, overrides=overrides or None
            )
            try:
                # 文档 7.1:Agent 在独立线程执行,单插件崩溃不拖垮平台。
                # 【已确认 Q16】超时只保证调用方失败;线程本身无法被 Python 强杀。
                output = await agent.run_isolated(
                    lambda: agent.run(current_event), timeout=AGENT_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError as exc:
                raise PluginUnavailableError(
                    f"{stage['agent']} 执行超时(超过 {AGENT_TIMEOUT_SECONDS:g} 秒)"
                ) from exc
            finally:
                agent.unload()

            if not isinstance(output, EventEnvelope):
                output = validate_event(dict(output))
            event_dict = output.model_dump(mode="json")
            db.save_event(run_id, output.trace_id, event_dict)
            await self._publish(event_dict)
            latency_total += output.model_info.latency_ms
            self._update_tat(run, run_context, latency_total)
            current_event = output

            if output.status in (EventStatus.HANDOVER_HUMAN, EventStatus.NEED_MORE_INFO):
                reason = str(
                    output.payload.get("review_summary")
                    or output.payload.get("confidence_reason")
                    or output.status.value
                )
                db.update_run(
                    run_id,
                    status="waiting_human",
                    human_reason=reason,
                    current_stage=stage["agent"],
                )
                self.notifications.schedule(run_id, "waiting_human", reason)
                return
            if output.status == EventStatus.REJECTED:
                reject_reason = str(output.payload.get("review_summary") or "")
                db.update_run(
                    run_id,
                    status="rejected",
                    finished_at=db.utc_now_iso(),
                    current_stage=stage["agent"],
                )
                self.notifications.schedule(run_id, "rejected", reject_reason or None)
                return

            if stage.get("human_gate") and output.event_type == EventType.REVIEW_RESULT:
                # 文档场景 1:高置信度自动通过后写入 Mock Jira,再进入 Reporting
                _, current_event = self._create_ticket(run, current_event, run_context)

        self._finalize_report(run_id, run_context, latency_total)
        db.update_run(
            run_id,
            status="completed",
            finished_at=db.utc_now_iso(),
            current_stage=None,
        )
        self.notifications.schedule(run_id, "completed")

    async def _build_dependencies(
        self,
        stage: dict[str, Any],
        run_context: dict[str, Any],
        llm_cache: dict[str, tuple[Any, Any, str | None]] | None = None,
    ) -> dict[str, Any]:
        # 【已确认 Q10】同一次运行内缓存 LLM 解析结果,避免 6 个阶段重复做健康检查。
        cache = llm_cache if llm_cache is not None else {}
        cache_key = stage.get("llm_provider") or "mock_llm"
        if cache_key not in cache:
            cache[cache_key] = await resolve_llm(self.registry, stage.get("llm_provider"))
        primary_llm, mock_llm, _ = cache[cache_key]
        return {
            "llm_provider": primary_llm,
            "mock_llm": mock_llm,
            "knowledge_base": resolve_optional_plugin(
                self.registry, stage.get("knowledge_base")
            ),
            "tool": resolve_optional_plugin(self.registry, stage.get("tool")),
            "run_context": run_context,
        }

    def _build_run_context(
        self, run: dict[str, Any], ticket_key: str | None = None
    ) -> dict[str, Any]:
        events = db.list_events(run["run_id"])
        latency_total = sum(int(event.get("model_info", {}).get("latency_ms", 0)) for event in events)
        actual = self._elapsed_seconds(run["started_at"])
        simulated = latency_total / 1000
        return {
            "run_id": run["run_id"],
            "trace_id": run["trace_id"],
            "started_at": run["started_at"],
            "ticket_key": ticket_key,
            "tat_seconds": int(round(max(actual, simulated))),
            "tat_source": "simulated_mock" if simulated > actual + 0.5 else "measured",
        }

    def _update_tat(
        self, run: dict[str, Any], run_context: dict[str, Any], latency_total: int
    ) -> None:
        actual = self._elapsed_seconds(run["started_at"])
        simulated = latency_total / 1000
        run_context["tat_seconds"] = int(round(max(actual, simulated)))
        run_context["tat_source"] = (
            "simulated_mock" if simulated > actual + 0.5 else "measured"
        )

    def _finalize_report(
        self, run_id: str, run_context: dict[str, Any], latency_total: int
    ) -> None:
        run = db.get_run(run_id)
        if run is None:
            return
        actual = self._elapsed_seconds(run["started_at"])
        simulated = latency_total / 1000
        tat_seconds = int(round(max(actual, simulated)))
        tat_source = "simulated_mock" if simulated > actual + 0.5 else "measured"
        run_context["tat_seconds"] = tat_seconds
        run_context["tat_source"] = tat_source

        report = db.get_latest_event(run_id, EventType.REPORT_ITEM.value)
        if report is not None:
            report["payload"]["tat_seconds"] = tat_seconds
            report["payload"]["tat_source"] = tat_source
            # 文档未定义 report_item 字段【已确认 Q23】;同步摘要中的 TAT,避免
            # 摘要(不含 Reporting 自身耗时)与最终指标不一致。
            report["payload"]["summary"] = (
                f"流水线完成,TAT {tat_seconds} 秒,"
                f"工单 {run_context.get('ticket_key') or '未创建'}"
            )
            try:
                updated = validate_event(report)
                db.update_event(updated.model_dump(mode="json"))
            except SchemaValidationFailure:
                logger.warning("report event update skipped", extra={"run_id": run_id})

    def _create_ticket(
        self,
        run: dict[str, Any],
        current_event: EventEnvelope,
        run_context: dict[str, Any],
    ) -> tuple[dict[str, Any], EventEnvelope]:
        existing = db.get_ticket_by_trace(run["trace_id"])
        if existing is not None:
            run_context["ticket_key"] = existing["ticket_key"]
            return existing, current_event

        draft_event = db.get_latest_event(run["run_id"], EventType.TICKET_DRAFT.value)
        if draft_event is None:
            raise ToolExecutionError("未找到 ticket_draft,无法创建工单")
        payload = draft_event.get("payload", {})
        draft = {
            "trace_id": run["trace_id"],
            "draft_id": payload.get("draft_id"),
            "title": payload.get("ticket_title"),
            "description": payload.get("ticket_description"),
            "priority": payload.get("priority"),
            "category": payload.get("category"),
            "source_case_id": payload.get("case_id"),
            "confidence": draft_event.get("confidence"),
        }
        jira = resolve_optional_plugin(self.registry, "jira_mock")
        if jira is None:
            raise PluginUnavailableError("Mock Jira 不可用,无法创建工单")
        try:
            ticket = jira.create_ticket(draft)
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"工单创建失败: {exc.__class__.__name__}") from exc

        run_context["ticket_key"] = ticket["ticket_key"]
        event_dict = current_event.model_dump(mode="json")
        event_dict["payload"] = dict(event_dict.get("payload", {}))
        event_dict["payload"]["ticket_key"] = ticket["ticket_key"]
        updated = validate_event(event_dict)
        db.update_event(updated.model_dump(mode="json"))
        return ticket, updated

    # ----------------------------------------------------------------- review

    async def review_run(
        self, run_id: str, action: str, reason: str | None
    ) -> dict[str, Any]:
        run = db.get_run(run_id)
        if run is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        if run["status"] != "waiting_human":
            raise ConflictError("当前运行不在人工卡点状态")
        review_event = db.get_latest_event(run_id, EventType.REVIEW_RESULT.value)
        if review_event is None:
            raise ConflictError("未找到 Reviewer 事件")

        event_dict = dict(review_event)
        event_dict["payload"] = dict(event_dict.get("payload", {}))
        event_dict["payload"]["reviewed_by"] = "human"
        if reason is not None:
            event_dict["payload"]["review_reason"] = reason

        if action == "reject":
            event_dict["status"] = EventStatus.REJECTED.value
            event_dict["payload"]["decision"] = "reject"
            updated = validate_event(event_dict)
            db.update_event(updated.model_dump(mode="json"))
            db.update_run(
                run_id,
                status="rejected",
                human_reason=reason,
                finished_at=db.utc_now_iso(),
            )
            self.notifications.schedule(run_id, "rejected", reason)
            return self.get_trace(run["trace_id"])

        event_dict["status"] = EventStatus.PASSED.value
        event_dict["payload"]["decision"] = "pass"
        updated = validate_event(event_dict)
        db.update_event(updated.model_dump(mode="json"))
        db.update_run(run_id, status="running", human_reason=None)

        run = db.get_run(run_id) or run
        pipeline_record = db.get_pipeline(run["pipeline_id"])
        if pipeline_record is None:
            raise NotFoundError(f"流水线不存在: {run['pipeline_id']}")
        pipeline_def = pipeline_record["definition"]
        stages = pipeline_def.get("stages", [])
        reviewer_index = next(
            (index for index, stage in enumerate(stages) if stage.get("human_gate")), None
        )
        if reviewer_index is None:
            raise ConfigurationError("流水线缺少 human_gate 阶段")

        try:
            run_context = self._build_run_context(run)
            _, current_event = self._create_ticket(run, updated, run_context)
            existing_ticket = db.get_ticket_by_trace(run["trace_id"])
            if existing_ticket is not None:
                run_context["ticket_key"] = existing_ticket["ticket_key"]
            await self._execute_stages(
                run, pipeline_def, reviewer_index + 1, current_event, run_context
            )
        except DomainError as exc:
            db.save_dead_letter(run["trace_id"], str(exc), run_id=run_id)
            db.update_run(
                run_id,
                status="failed",
                error_reason=str(exc),
                finished_at=db.utc_now_iso(),
            )
            self.notifications.schedule(run_id, "failed", str(exc))
            raise
        return self.get_trace(run["trace_id"])

    # -------------------------------------------------------------- knowledge

    def mark_knowledge(self, run_id: str) -> dict[str, Any]:
        run = db.get_run(run_id)
        if run is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        # 文档场景 3:在 Reviewer 节点标记入库;0.75 自动通过后仍允许(矛盾 C2)
        if db.get_latest_event(run_id, EventType.REVIEW_RESULT.value) is None:
            raise ConflictError("尚未到达 Reviewer 阶段,不能入库知识库")
        triage = db.get_latest_event(run_id, EventType.TRIAGE_RESULT.value)
        if triage is None:
            raise ConflictError("未找到 Triage 结果")

        kb = resolve_optional_plugin(self.registry, "memory_vector_kb")
        if kb is None:
            raise PluginUnavailableError("内存向量知识库不可用")

        for entry in kb.list_entries():
            if entry.get("source_trace_id") == run["trace_id"]:
                return entry

        payload = triage.get("payload", {})
        title = f"{payload.get('title') or payload.get('case_id') or 'CI failure'} - {payload.get('category')}"
        # 【已确认 Q6】结构化满足“日志摘要 + Triage 结论 + 分类”;
        # 检索仍只用标题/日志计分,结论不参与相似度,避免稀释。
        content = str(payload.get("log_excerpt") or "")
        summary = str(payload.get("log_summary") or content)
        root_cause = str(payload.get("root_cause") or "")
        return kb.add(
            title=title,
            content=content,
            category=str(payload.get("category", "unknown")),
            summary=summary,
            root_cause=root_cause,
            source_trace_id=run["trace_id"],
        )

    def list_knowledge(self, query: str | None = None) -> list[dict[str, Any]]:
        kb = resolve_optional_plugin(self.registry, "memory_vector_kb")
        if query and query.strip():
            if kb is None:
                return []
            return kb.search(query.strip())
        if kb is not None:
            return kb.list_entries()
        return db.list_knowledge()

    # ------------------------------------------------------------------ traces

    def list_traces(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        runs = db.list_runs(limit=limit)
        items: list[dict[str, Any]] = []
        for run in runs:
            if status and run["status"] != status:
                continue
            items.append(self._trace_summary(run))
        return items

    def _trace_summary(self, run: dict[str, Any]) -> dict[str, Any]:
        events = db.list_events(run["run_id"])
        triage = db.get_latest_event(run["run_id"], EventType.TRIAGE_RESULT.value)
        review = db.get_latest_event(run["run_id"], EventType.REVIEW_RESULT.value)
        report = db.get_latest_event(run["run_id"], EventType.REPORT_ITEM.value)
        ticket = db.get_ticket_by_trace(run["trace_id"])
        input_payload = run["input_event"].get("payload", {})
        confidence_event = review or triage
        report_payload = (report or {}).get("payload", {})
        tat_seconds = int(
            report_payload.get("tat_seconds", self._simulated_seconds(events))
        )
        # 【已确认 Q12】等待中/驳回时可能尚无 report_item,按真实墙钟与模拟值
        # 比较后给出 tat_source,前端不得把模拟值显示为实测。
        tat_source = report_payload.get("tat_source")
        if not tat_source:
            actual = self._elapsed_seconds(run["started_at"])
            simulated = self._simulated_seconds(events)
            tat_source = "simulated_mock" if simulated > actual + 0.5 else "measured"
        return {
            "run_id": run["run_id"],
            "trace_id": run["trace_id"],
            "pipeline_id": run["pipeline_id"],
            "case_id": input_payload.get("case_id"),
            "title": input_payload.get("title"),
            "job_name": input_payload.get("job_name"),
            "status": run["status"],
            "current_stage": run["current_stage"],
            "orchestrator_configured": run["orchestrator_configured"],
            "orchestrator_used": run["orchestrator_used"],
            "fallback_reason": run["fallback_reason"],
            "confidence": confidence_event.get("confidence") if confidence_event else None,
            "category": (triage or {}).get("payload", {}).get("category"),
            "ticket_key": ticket["ticket_key"] if ticket else None,
            "tat_seconds": tat_seconds,
            "tat_source": tat_source,
            "human_reason": run["human_reason"],
            "error_reason": run["error_reason"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "input_source": run.get("input_source"),
        }

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        run = db.get_run_by_trace(trace_id)
        if run is None:
            raise NotFoundError(f"Trace 不存在: {trace_id}")
        events = db.list_events(run["run_id"])
        ticket = db.get_ticket_by_trace(trace_id)
        dead_letters = db.list_dead_letters(trace_id)
        pipeline = db.get_pipeline(run["pipeline_id"])
        knowledge = [
            entry
            for entry in db.list_knowledge(limit=1000)
            if entry.get("source_trace_id") == trace_id
        ]
        review = db.get_latest_event(run["run_id"], EventType.REVIEW_RESULT.value)
        triage = db.get_latest_event(run["run_id"], EventType.TRIAGE_RESULT.value)
        report = db.get_latest_event(run["run_id"], EventType.REPORT_ITEM.value)

        # 等待人工/驳回时尚无 report_item,按已产生事件的模拟耗时标注来源,
        # 避免把 Mock 模拟值显示成“实测耗时”【已确认 Q12】。
        actual_seconds = self._elapsed_seconds(run["started_at"])
        simulated_seconds = self._simulated_seconds(events)
        fallback_tat_source = (
            "simulated_mock" if simulated_seconds > actual_seconds + 0.5 else "measured"
        )

        stages: list[dict[str, Any]] = []
        event_cursor = 0
        for stage in (pipeline or {}).get("definition", {}).get("stages", []):
            # 画布允许重复 Agent;按出现顺序匹配事件,避免第二个同名阶段复用第一个事件。
            matched = None
            for index in range(event_cursor, len(events)):
                if events[index].get("source_agent") == stage["agent"]:
                    matched = events[index]
                    event_cursor = index + 1
                    break
            if matched is not None:
                stage_status = matched.get("status")
            elif run["current_stage"] == stage["agent"]:
                stage_status = "running"
            else:
                stage_status = "pending"
            event_payload = (matched or {}).get("payload", {})
            prompt_text = event_payload.get("prompt_text")
            prompt_source = event_payload.get("prompt_source")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                # 未执行/运行中阶段,以及旧数据没有快照时,按当前配置解析。
                try:
                    prompt_text, resolved_source = self.registry.resolve_agent_prompt(
                        stage["agent"], stage.get("system_prompt")
                    )
                except ConfigurationError:
                    prompt_text, resolved_source = "", "default"
                prompt_source = resolved_source
            stages.append(
                {
                    "agent": stage["agent"],
                    "human_gate": bool(stage.get("human_gate")),
                    "status": stage_status,
                    "event_id": matched.get("event_id") if matched else None,
                    "confidence": matched.get("confidence") if matched else None,
                    "latency_ms": (matched or {}).get("model_info", {}).get("latency_ms"),
                    "prompt": prompt_text,
                    "prompt_source": prompt_source,
                }
            )

        available_actions: list[str] = []
        if run["status"] == "waiting_human":
            available_actions.extend(["approve", "reject"])
        if review is not None:
            available_actions.append("mark_knowledge")
        if run["status"] in {"running", "waiting_human"}:
            available_actions.append("stop")

        model_usage: dict[str, int] = {}
        for event in events:
            loc = str(event.get("model_info", {}).get("model_loc", "unknown"))
            model_usage[loc] = model_usage.get(loc, 0) + 1

        return {
            "run": run,
            "events": events,
            "ticket": ticket,
            "dead_letters": dead_letters,
            "pipeline": pipeline,
            "knowledge": knowledge,
            "stages": stages,
            "available_actions": available_actions,
            "metrics": {
                "confidence": (review or triage or {}).get("confidence"),
                "tat_seconds": int(
                    (report or {}).get("payload", {}).get(
                        "tat_seconds", simulated_seconds
                    )
                ),
                "tat_source": (report or {}).get("payload", {}).get(
                    "tat_source", fallback_tat_source
                ),
                "model_usage": model_usage,
            },
        }

    # --------------------------------------------------------------- dashboard

    async def dashboard(self) -> dict[str, Any]:
        # 【已确认 Q19】“今日”按服务端本地时区(可通过 IQE_TIMEZONE 覆盖)自然日。
        now_local = local_now()
        midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        since = midnight.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        runs = db.list_runs(limit=1000, since=since)

        waiting = sum(1 for run in runs if run["status"] == "waiting_human")
        running = sum(1 for run in runs if run["status"] == "running")
        completed = sum(1 for run in runs if run["status"] == "completed")
        rejected = sum(1 for run in runs if run["status"] == "rejected")
        failed = sum(1 for run in runs if run["status"] == "failed")

        tats: list[int] = []
        tat_sources: set[str] = set()
        for run in runs:
            if run["status"] != "completed":
                continue
            report = db.get_latest_event(run["run_id"], EventType.REPORT_ITEM.value)
            if report and report.get("payload", {}).get("tat_seconds") is not None:
                tats.append(int(report["payload"]["tat_seconds"]))
                tat_sources.add(str(report["payload"].get("tat_source") or "measured"))
        avg_tat = int(round(sum(tats) / len(tats))) if tats else 0
        avg_tat_source = (
            "mixed" if len(tat_sources) > 1 else (next(iter(tat_sources)) if tat_sources else None)
        )

        kb = resolve_optional_plugin(self.registry, "memory_vector_kb")
        knowledge_count = len(kb.list_entries()) if kb is not None else len(db.list_knowledge())

        return {
            "timezone": local_timezone_name(),
            "today_start": midnight.isoformat(),
            "stats": {
                "pending_failures": waiting + running,
                "waiting_human": waiting,
                "running": running,
                "completed": completed,
                "rejected": rejected,
                "failed": failed,
                "avg_tat_seconds": avg_tat,
                "avg_tat_source": avg_tat_source,
                "ticket_count": db.count_tickets_since(since),
                "knowledge_count": knowledge_count,
                "total_today": len(runs),
            },
            "baselines": {
                "human_tat_minutes": DOC_BASELINES["human"]["tat_minutes"],
                "demo_tat_minutes": DOC_BASELINES["cloud"]["tat_minutes"],
                "source": "文档 6 场景 1",
            },
            "recent_traces": [self._trace_summary(run) for run in runs[:8]],
        }

    async def experiments(self) -> dict[str, Any]:
        runs = db.list_runs(limit=1000)
        model_usage: dict[str, int] = {}
        kb_hit_confidences: list[float] = []
        kb_hit_latencies: list[int] = []
        no_kb_confidences: list[float] = []
        no_kb_latencies: list[int] = []
        tats: list[int] = []
        tat_sources: set[str] = set()
        confidences: list[float] = []

        for run in runs:
            events = db.list_events(run["run_id"])
            for event in events:
                loc = str(event.get("model_info", {}).get("model_loc", "unknown"))
                model_usage[loc] = model_usage.get(loc, 0) + 1
            triage = db.get_latest_event(run["run_id"], EventType.TRIAGE_RESULT.value)
            if triage:
                confidence = float(triage.get("confidence", 0))
                latency = int(triage.get("model_info", {}).get("latency_ms", 0))
                confidences.append(confidence)
                if triage.get("payload", {}).get("kb_hit"):
                    kb_hit_confidences.append(confidence)
                    kb_hit_latencies.append(latency)
                else:
                    no_kb_confidences.append(confidence)
                    no_kb_latencies.append(latency)
            report = db.get_latest_event(run["run_id"], EventType.REPORT_ITEM.value)
            if report and report.get("payload", {}).get("tat_seconds") is not None:
                tats.append(int(report["payload"]["tat_seconds"]))
                tat_sources.add(str(report["payload"].get("tat_source") or "measured"))

        def _avg(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 3) if values else None

        def _avg_int(values: list[int]) -> int | None:
            return int(round(sum(values) / len(values))) if values else None

        baselines = [
            {"name": item["name"], "model_loc": item.get("model_loc"), **{
                key: value for key, value in item.items()
                if key in {"tat_minutes", "cost_per_ticket", "confidence", "source"}
            }}
            for item in DOC_BASELINES.values()
        ]
        return {
            "baselines": baselines,
            "computed": {
                "run_count": len(runs),
                "avg_tat_seconds": _avg_int(tats),
                # 【已确认 Q12】mixed 表示同时包含实测与模拟业务耗时。
                "avg_tat_source": (
                    "mixed"
                    if len(tat_sources) > 1
                    else (next(iter(tat_sources)) if tat_sources else None)
                ),
                "avg_confidence": _avg(confidences),
                "model_usage": model_usage,
                "knowledge_stats": {
                    "kb_hit": {
                        "count": len(kb_hit_confidences),
                        "avg_confidence": _avg(kb_hit_confidences),
                        "avg_triage_latency_ms": _avg_int(kb_hit_latencies),
                    },
                    "no_kb": {
                        "count": len(no_kb_confidences),
                        "avg_confidence": _avg(no_kb_confidences),
                        "avg_triage_latency_ms": _avg_int(no_kb_latencies),
                    },
                },
            },
        }

    # -------------------------------------------------------------------- stop

    async def stop_run(self, run_id: str) -> dict[str, Any]:
        run = db.get_run(run_id)
        if run is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        if run["status"] in TERMINAL_STATUSES:
            raise ConflictError("运行已结束,不能停止")
        if run["status"] == "waiting_human":
            db.update_run(run_id, status="stopped", finished_at=db.utc_now_iso())
            self.notifications.schedule(run_id, "stopped")
            return db.get_run(run_id) or run

        if run["orchestrator_used"] == "memory_orchestrator":
            memory = self.registry.get("memory_orchestrator")
            await memory.stop_pipeline(run_id)
        else:
            airflow = resolve_optional_plugin(self.registry, run["orchestrator_used"])
            if airflow is not None and run.get("orchestrator_run_id"):
                await airflow.stop_pipeline(run["orchestrator_run_id"])
            db.update_run(run_id, status="stopped", finished_at=db.utc_now_iso())
            self.notifications.schedule(run_id, "stopped")
        return db.get_run(run_id) or run

    # ------------------------------------------------------------------ notify

    def list_notifications(self, run_id: str) -> list[dict[str, Any]]:
        if db.get_run(run_id) is None:
            raise NotFoundError(f"运行不存在: {run_id}")
        return db.list_run_notifications(run_id)

    # ------------------------------------------------------------------ helper

    async def _publish(self, event: dict[str, Any]) -> None:
        if not self.registry.has("memory_event_bus") or not self.registry.is_enabled(
            "memory_event_bus"
        ):
            return
        try:
            bus = self.registry.get("memory_event_bus")
            await bus.publish(event)
        except Exception as exc:  # noqa: BLE001 - 事件总线故障不能阻断主链路
            logger.warning(
                "event bus publish failed",
                extra={"error": exc.__class__.__name__, "trace_id": event.get("trace_id")},
            )

    def _fail_run(self, run: dict[str, Any], exc: Exception) -> None:
        reason = getattr(exc, "message", str(exc))
        db.save_dead_letter(run["trace_id"], reason, run_id=run["run_id"])
        db.update_run(
            run["run_id"],
            status="failed",
            error_reason=reason,
            finished_at=db.utc_now_iso(),
        )
        self.notifications.schedule(run["run_id"], "failed", reason)
        logger.error(
            "pipeline failed",
            extra={
                "run_id": run["run_id"],
                "trace_id": run["trace_id"],
                "error": reason,
            },
        )

    def _is_cancelled(self, run_id: str) -> bool:
        run = db.get_run(run_id)
        if run is None:
            return True
        if run["status"] == "stopped":
            return True
        if self.registry.has("memory_orchestrator") and self.registry.is_enabled(
            "memory_orchestrator"
        ):
            memory = self.registry.get("memory_orchestrator")
            checker = getattr(memory, "is_cancelled", None)
            if callable(checker) and checker(run_id):
                return True
        return False

    @staticmethod
    def _elapsed_seconds(started_at: str) -> float:
        try:
            return max(0.0, (datetime.now(timezone.utc) - _parse_iso(started_at)).total_seconds())
        except ValueError:
            return 0.0

    @staticmethod
    def _simulated_seconds(events: list[dict[str, Any]]) -> int:
        return int(
            round(
                sum(
                    int(event.get("model_info", {}).get("latency_ms", 0))
                    for event in events
                )
                / 1000
            )
        )

    @staticmethod
    def _merge_reason(*reasons: str | None) -> str | None:
        merged = "；".join(reason for reason in reasons if reason)
        return merged or None
