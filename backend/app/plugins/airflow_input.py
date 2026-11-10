"""Airflow 输入源插件(真实 REST 集成)。

文档 2/3.2 将 Airflow 定义为可选集成;本 Demo 按【已确认 Q24】将 Airflow
改为与 Jenkins 同类的输入源:
- 监控指定 Airflow 平台上的 DAG 运行结果;
- dag_ids 为空时监控全部 DAG,否则只监控配置的 DAG;
- 发现 failed DAG Run 时构造标准 monitor_alert 事件,由平台自动触发 6 个 Agent。

兼容 Airflow 2(REST v1 + Basic Auth)与 Airflow 3(REST v2 + /auth/token JWT)。
只读运行记录与任务日志,不修改外部 Airflow 的任何配置。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

from .. import db
from ..config import HEALTH_CHECK_TIMEOUT_SECONDS
from ..errors import PluginUnavailableError
from ..models.event import EventEnvelope, EventStatus, EventType, ModelInfo, ModelLoc
from .base import InputSourcePlugin

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer)\s+\S+"),
)
_ALLOWED_ID = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_text(value: str, max_chars: int = 6000) -> str:
    """裁剪并脱敏外部日志,避免把凭据写入平台 Trace。"""

    text = _ANSI.sub("", value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=***", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _safe_id(value: str, max_length: int = 100) -> str:
    cleaned = _ALLOWED_ID.sub("-", value).strip("-")
    return (cleaned or "airflow-case")[:max_length]


def _parse_dag_ids(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\s]+", raw or "") if item.strip()]


class AirflowInputSourcePlugin(InputSourcePlugin):
    plugin_id = "airflow_input"
    display_name = "Airflow 输入源"
    description = "监控 Airflow DAG 运行结果,失败时自动触发 IQE Agent(真实 REST 集成)"
    plugin_type = "input_source"
    # 真实 Airflow 由用户显式启用,默认不访问外部网络。
    enabled_by_default = False
    # 真实外部系统健康检查允许超过默认 2 秒。
    health_timeout_seconds = 10
    capabilities = {
        "polling": True,
        "webhook": False,
        "supports_all_dags": True,
        "description": "轮询 failed DAG Run;dag_ids 为空监控全部 DAG,否则只监控指定 DAG。",
    }
    config_schema = {
        "api_url": {
            "type": "string",
            "label": "Airflow URL",
            "default": "",
            "required": False,
            "pattern": r"(^$|^https?://[^\s]+$)",
            "description": "例如 http://airflow.example.com:8080;不要包含 /api/v1 或 /api/v2。",
        },
        "username": {
            "type": "string",
            "label": "用户名",
            "default": "",
            "required": False,
        },
        "password": {
            "type": "string",
            "label": "密码 / Token",
            "default": "",
            "required": False,
            "secret": True,
            "description": "Airflow 3 使用用户名密码换取 JWT;Airflow 2 使用 Basic Auth。",
        },
        "dag_ids": {
            "type": "string",
            "label": "监控流水线 DAG ID",
            "default": "",
            "required": False,
            "description": "多个 DAG 用逗号/换行分隔;留空表示监控该 Airflow 上的全部 DAG。",
        },
        "api_version": {
            "type": "string",
            "label": "REST API 版本",
            "default": "auto",
            "required": False,
            "enum": ["auto", "v2", "v1"],
            "description": "auto 会优先尝试 Airflow 3 的 /api/v2;失败再尝试 /api/v1。",
        },
        "poll_interval_seconds": {
            "type": "number",
            "label": "轮询间隔(秒)",
            "default": 60,
            "min": 5,
            "max": 3600,
            "required": False,
        },
        "lookback_minutes": {
            "type": "number",
            "label": "首次回看窗口(分钟)",
            "default": 60,
            "min": 1,
            "max": 10080,
            "required": False,
            "description": "仅处理窗口内失败的 DAG Run;手动“立即检查”可覆盖该值。",
        },
        "max_events_per_poll": {
            "type": "integer",
            "label": "单次最多触发数",
            "default": 3,
            "min": 1,
            "max": 10,
            "required": False,
        },
        "max_tasks_per_run": {
            "type": "integer",
            "label": "单次运行最多读取失败任务数",
            "default": 3,
            "min": 1,
            "max": 10,
            "required": False,
        },
        "timeout_seconds": {
            "type": "number",
            "label": "调用超时(秒)",
            "default": 15,
            "min": 1,
            "max": 300,
            "required": False,
        },
    }

    def __init__(
        self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None
    ) -> None:
        super().__init__(config, dependencies)
        self._version: str | None = None
        self._token: str | None = None

    # --------------------------------------------------------------- transport

    @property
    def _root(self) -> str:
        return str(self.config.get("api_url", "")).rstrip("/")

    def _timeout(self) -> float:
        return float(self.config.get("timeout_seconds", 15))

    async def _detect_version(self, client: httpx.AsyncClient) -> str:
        configured = str(self.config.get("api_version", "auto"))
        if configured in {"v1", "v2"}:
            self._version = configured
            return configured
        if self._version:
            return self._version
        try:
            response = await client.get(f"{self._root}/api/v2/version")
            if response.status_code < 400:
                self._version = "v2"
                return "v2"
        except httpx.HTTPError:
            pass
        try:
            response = await client.get(
                f"{self._root}/api/v1/version", auth=self._basic_auth()
            )
            if response.status_code < 400:
                self._version = "v1"
                return "v1"
        except httpx.HTTPError:
            pass
        # 未能探测时默认 v2,让后续请求给出明确 HTTP 错误。
        self._version = "v2"
        return "v2"

    def _basic_auth(self) -> tuple[str, str] | None:
        username = str(self.config.get("username", ""))
        password = str(self.config.get("password", ""))
        if not username and not password:
            return None
        return username, password

    async def _fetch_token(self, client: httpx.AsyncClient) -> str | None:
        """Airflow 3:用用户名密码换取 JWT;失败则回退 Basic Auth。"""

        if self._version != "v2" or not self._basic_auth():
            return None
        try:
            response = await client.post(
                f"{self._root}/auth/token",
                json={
                    "username": str(self.config.get("username", "")),
                    "password": str(self.config.get("password", "")),
                },
            )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            token = str(response.json().get("access_token") or "")
        except ValueError:
            return None
        self._token = token or None
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> Any:
        if not self._root:
            raise PluginUnavailableError("未配置 Airflow URL")
        timeout = self._timeout()
        async with httpx.AsyncClient(timeout=timeout) as client:
            version = await self._detect_version(client)
            if version == "v2" and self._token is None:
                await self._fetch_token(client)

            async def send() -> httpx.Response:
                headers: dict[str, str] = {}
                auth = self._basic_auth()
                if version == "v2" and self._token:
                    headers["Authorization"] = f"Bearer {self._token}"
                    auth = None
                return await client.request(
                    method,
                    f"{self._root}/api/{version}/{path.lstrip('/')}",
                    params=params,
                    headers=headers,
                    auth=auth,
                )

            try:
                response = await send()
                if response.status_code == 401 and version == "v2" and self._token:
                    self._token = None
                    await self._fetch_token(client)
                    response = await send()
            except httpx.HTTPError as exc:
                raise PluginUnavailableError(
                    f"Airflow 请求失败: {exc.__class__.__name__}"
                ) from exc

        if response.status_code >= 400:
            detail = response.text[:200].replace("\n", " ")
            raise PluginUnavailableError(
                f"Airflow 请求失败(HTTP {response.status_code}): {detail}"
            )
        if raw:
            return response.text
        try:
            return response.json()
        except ValueError as exc:
            raise PluginUnavailableError("Airflow 响应不是合法 JSON") from exc

    # ------------------------------------------------------------------- health

    async def health(self) -> tuple[bool, str]:
        if not self._root:
            return False, "未配置 Airflow URL"
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT_SECONDS) as client:
                version = await self._detect_version(client)
                if version == "v1":
                    response = await client.get(
                        f"{self._root}/api/v1/health", auth=self._basic_auth()
                    )
                    if response.status_code < 400:
                        return True, "Airflow v1 可访问"
                    return False, f"Airflow 健康检查失败(HTTP {response.status_code})"
                version_response = await client.get(f"{self._root}/api/v2/version")
                if version_response.status_code >= 400:
                    return False, f"Airflow v2 不可访问(HTTP {version_response.status_code})"
                try:
                    version_text = str(version_response.json().get("version", ""))
                except ValueError:
                    version_text = ""
                dags = await self.list_dags()
            return True, f"Airflow {version_text or 'v2'} 可访问,发现 {len(dags)} 个 DAG"
        except (PluginUnavailableError, httpx.HTTPError) as exc:
            message = getattr(exc, "message", str(exc))
            return False, f"Airflow 不可达: {message}"

    # -------------------------------------------------------------------- query

    async def list_dags(self) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", "dags", params={"limit": 100, "only_active": "true"}
        )
        dags = payload.get("dags", []) if isinstance(payload, dict) else []
        return [dict(item) for item in dags if isinstance(item, dict)]

    async def list_failed_runs(
        self, dag_id: str, lookback_minutes: int, limit: int = 2
    ) -> list[dict[str, Any]]:
        version = self._version or "v2"
        since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        if version == "v2":
            params = {
                "state": "failed",
                "limit": limit,
                "order_by": "-logical_date",
                "logical_date_gte": since.isoformat().replace("+00:00", "Z"),
            }
        else:
            params = {
                "state": "failed",
                "limit": limit,
                "order_by": "-execution_date",
                "execution_date_gte": since.isoformat().replace("+00:00", "Z"),
            }
        try:
            payload = await self._request(
                "GET", f"dags/{dag_id}/dagRuns", params=params
            )
        except PluginUnavailableError:
            # 部分 Airflow 版本排序字段不同;去掉 order_by 再试一次。
            params.pop("order_by", None)
            payload = await self._request(
                "GET", f"dags/{dag_id}/dagRuns", params=params
            )
        runs = payload.get("dag_runs", []) if isinstance(payload, dict) else []
        return [dict(item) for item in runs if isinstance(item, dict)]

    async def list_failed_tasks(
        self, dag_id: str, dag_run_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
            params={"state": "failed", "limit": limit},
        )
        tasks = payload.get("task_instances", []) if isinstance(payload, dict) else []
        return [dict(item) for item in tasks if isinstance(item, dict)]

    async def _task_log(
        self, dag_id: str, dag_run_id: str, task_id: str, try_number: int
    ) -> str:
        raw = await self._request(
            "GET",
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}",
            raw=True,
        )
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return _sanitize_text(raw)
        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, str):
                return _sanitize_text(content)
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        value = item.get("event") or item.get("message")
                        if value:
                            parts.append(str(value))
                    elif item:
                        parts.append(str(item))
                return _sanitize_text("\n".join(parts))
        if isinstance(payload, list):
            return _sanitize_text(
                "\n".join(
                    str(item.get("event") or item) if isinstance(item, dict) else str(item)
                    for item in payload
                )
            )
        return _sanitize_text(raw)

    # ------------------------------------------------------------------ collect

    async def collect_alerts(
        self, limit: int | None = None, lookback_minutes: int | None = None
    ) -> list[EventEnvelope]:
        max_events = min(int(limit or self.config.get("max_events_per_poll", 3)), 10)
        lookback = int(lookback_minutes or self.config.get("lookback_minutes", 60))
        dag_ids = _parse_dag_ids(str(self.config.get("dag_ids", "")))
        if not dag_ids:
            dag_ids = [str(item.get("dag_id")) for item in await self.list_dags()]
        max_tasks = int(self.config.get("max_tasks_per_run", 3))
        events: list[EventEnvelope] = []

        for dag_id in dag_ids[:50]:
            if len(events) >= max_events:
                break
            try:
                runs = await self.list_failed_runs(dag_id, lookback, limit=2)
            except PluginUnavailableError:
                continue
            for run in runs:
                if len(events) >= max_events:
                    break
                dag_run_id = str(run.get("dag_run_id") or "")
                if not dag_run_id:
                    continue
                event_key = f"{dag_id}:{dag_run_id}"
                # 先构造事件再标记,避免日志抓取失败导致该 Run 永久丢失。
                try:
                    tasks = await self.list_failed_tasks(
                        dag_id, dag_run_id, limit=max_tasks
                    )
                except PluginUnavailableError:
                    tasks = []
                log_parts: list[str] = []
                for task in tasks[:max_tasks]:
                    task_id = str(task.get("task_id") or "")
                    try_number = int(task.get("try_number") or 1)
                    try:
                        log_parts.append(
                            f"[{task_id} try {try_number}]\n"
                            + await self._task_log(dag_id, dag_run_id, task_id, try_number)
                        )
                    except PluginUnavailableError as exc:
                        log_parts.append(f"[{task_id}] 日志获取失败: {exc.message}")
                if not db.mark_source_event_seen(self.plugin_id, event_key):
                    continue
                events.append(
                    self._build_event(
                        dag_id=dag_id,
                        run=run,
                        tasks=tasks,
                        log_excerpt="\n\n".join(log_parts),
                    )
                )
        return events

    # -------------------------------------------------------------- event build

    def _build_event(
        self,
        *,
        dag_id: str,
        run: dict[str, Any],
        tasks: list[dict[str, Any]],
        log_excerpt: str,
    ) -> EventEnvelope:
        dag_run_id = str(run.get("dag_run_id") or "")
        logical_date = str(
            run.get("logical_date") or run.get("execution_date") or run.get("start_date") or ""
        )
        raw_conf = run.get("conf")
        conf: dict[str, Any] = raw_conf if isinstance(raw_conf, dict) else {}
        primary = tasks[0] if tasks else {}
        task_id = str(primary.get("task_id") or "dag_run")
        try_number = int(primary.get("try_number") or 0)
        operator = str(primary.get("operator") or primary.get("task_display_name") or "")
        run_type = str(run.get("run_type") or "")
        title = f"{dag_id} / {task_id} 失败"[:120]
        case_id = _safe_id(f"AIRFLOW-{dag_id}-{dag_run_id}")
        artifact_url = f"{self._root}/dags/{dag_id}/runs/{dag_run_id}"
        repository = str(
            conf.get("ENV_TESTS_REPO")
            or conf.get("REPO")
            or conf.get("repository")
            or ""
        )
        branch = str(conf.get("BRANCH") or conf.get("branch") or "")
        commit = str(conf.get("COMMIT") or conf.get("commit") or "")
        failed_tasks = [
            {
                "task_id": str(item.get("task_id") or ""),
                "try_number": int(item.get("try_number") or 0),
                "operator": str(item.get("operator") or ""),
                "state": str(item.get("state") or ""),
            }
            for item in tasks
        ]
        payload: dict[str, Any] = {
            "case_id": case_id,
            "title": title,
            "job_name": dag_id,
            "build_number": try_number,
            "repository": repository,
            "branch": branch,
            "commit": commit,
            "stage": task_id,
            "log_excerpt": _sanitize_text(log_excerpt or "Airflow DAG Run 失败,未获取到任务日志"),
            "artifact_url": artifact_url,
            "airflow_dag_id": dag_id,
            "airflow_dag_run_id": dag_run_id,
            "airflow_logical_date": logical_date,
            "airflow_run_type": run_type,
            "airflow_operator": operator,
            "failed_tasks": failed_tasks,
        }
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type=EventType.MONITOR_ALERT,
            source_agent=self.plugin_id,
            timestamp=datetime.now(timezone.utc),
            trace_id=str(uuid4()),
            confidence=1.0,
            evidence_links=[artifact_url],
            status=EventStatus.PENDING,
            model_info=ModelInfo(
                model_loc=ModelLoc.MOCK,
                model_name="airflow-input",
                latency_ms=0,
                cost_token=0,
            ),
            payload=payload,
        )
