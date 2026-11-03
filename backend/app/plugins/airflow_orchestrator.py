"""Airflow 编排插件(REST v1 客户端)。

文档 3.2/7.4:Airflow 是可选编排插件,API 不可用或超时降级到内置编排器。
文档未定义 DAG ID、认证、回调与停止语义【待确认 Q8】;这里采用 Airflow REST v1 +
Basic Auth,不做未经确认的跨系统 Agent 回调,因此本插件只负责触发与查询 DAG。
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import HEALTH_CHECK_TIMEOUT_SECONDS
from ..errors import NotFoundError, PluginUnavailableError
from .base import OrchestratorPlugin


class AirflowOrchestratorPlugin(OrchestratorPlugin):
    plugin_id = "airflow_orchestrator"
    display_name = "Airflow Orchestrator"
    description = "Airflow 可选编排插件(文档 3.2;Q8 Demo 行为已确认,外部 DAG/回调契约待确认)"
    # 文档场景 4:默认使用内置编排引擎,Airflow 由用户显式启用
    enabled_by_default = False
    # 【已确认 Q8】跨系统 Agent 回调契约尚未定义,不允许宣称完全委托执行。
    capabilities = {
        "agent_callback": False,
        "execution_delegation": "opt_in",
        "description": "仅支持触发/查询/停止;执行委托需显式开启并自行提供 DAG 与回调。",
    }
    config_schema = {
        "api_url": {
            "type": "string",
            "label": "Airflow URL",
            "default": "http://localhost:18080",
            "required": False,
            "pattern": r"(^$|^https?://[^\s]+$)",
            "description": "文档 0.4:8080 已被占用,本机建议 18080",
        },
        "username": {"type": "string", "label": "用户名", "default": "", "required": False},
        "password": {
            "type": "string",
            "label": "密码",
            "default": "",
            "required": False,
            "secret": True,
        },
        "dag_id_prefix": {
            "type": "string",
            "label": "DAG ID 前缀",
            "default": "",
            "required": False,
        },
        "delegate_execution": {
            "type": "boolean",
            "label": "启用执行委托",
            "default": False,
            "required": False,
            "description": (
                "默认关闭。开启后平台会触发 DAG 并等待外部执行;"
                "当前未实现 Agent 回调契约,未自行提供回调时 Run 可能停在等待状态。"
            ),
        },
        # 【已确认 Q10】
        "timeout_seconds": {
            "type": "number",
            "label": "调用超时(秒)",
            "default": 10,
            "min": 1,
            "max": 300,
            "required": False,
        },
    }

    def __init__(self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None):
        super().__init__(config, dependencies)
        self._dag_runs: dict[str, str] = {}

    def _base_url(self) -> str:
        return str(self.config.get("api_url", "")).rstrip("/")

    def _auth(self) -> tuple[str, str] | None:
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        if not username and not password:
            return None
        return username, password

    async def health(self) -> tuple[bool, str]:
        base = self._base_url()
        if not base:
            return False, "未配置 Airflow URL"
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT_SECONDS) as client:
                for path in ("/api/v1/health", "/health"):
                    response = await client.get(f"{base}{path}", auth=self._auth())
                    if response.status_code < 400:
                        return True, f"Airflow 可访问({path})"
            return False, "Airflow 健康检查失败"
        except httpx.HTTPError as exc:
            return False, f"Airflow 不可达: {exc.__class__.__name__}"

    async def start_pipeline(
        self, pipeline_def: dict[str, Any], context: dict[str, Any] | None = None
    ) -> str:
        base = self._base_url()
        if not base:
            raise PluginUnavailableError("未配置 Airflow URL")
        dag_id = f"{self.config.get('dag_id_prefix', '')}{pipeline_def['pipeline_id']}"
        timeout = float(self.config.get("timeout_seconds", 10))
        body = {
            "conf": {
                "pipeline": pipeline_def,
                "platform_run_id": (context or {}).get("run_id"),
            }
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base}/api/v1/dags/{dag_id}/dagRuns",
                    json=body,
                    auth=self._auth(),
                )
        except httpx.HTTPError as exc:
            raise PluginUnavailableError(f"Airflow 触发失败: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise PluginUnavailableError(f"Airflow 触发失败(HTTP {response.status_code})")
        payload = response.json()
        dag_run_id = str(payload.get("dag_run_id") or "")
        if not dag_run_id:
            raise PluginUnavailableError("Airflow 未返回 dag_run_id")
        self._dag_runs[dag_run_id] = dag_id
        return dag_run_id

    async def get_pipeline_status(self, run_id: str) -> dict[str, Any]:
        dag_id = self._dag_runs.get(run_id)
        if not dag_id:
            raise NotFoundError(f"未知 Airflow run: {run_id}")
        base = self._base_url()
        timeout = float(self.config.get("timeout_seconds", 10))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{base}/api/v1/dags/{dag_id}/dagRuns/{run_id}",
                    auth=self._auth(),
                )
        except httpx.HTTPError as exc:
            raise PluginUnavailableError(f"Airflow 查询失败: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise PluginUnavailableError(f"Airflow 查询失败(HTTP {response.status_code})")
        return response.json()

    async def stop_pipeline(self, run_id: str) -> None:
        dag_id = self._dag_runs.get(run_id)
        if not dag_id:
            raise NotFoundError(f"未知 Airflow run: {run_id}")
        base = self._base_url()
        timeout = float(self.config.get("timeout_seconds", 10))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.patch(
                    f"{base}/api/v1/dags/{dag_id}/dagRuns/{run_id}",
                    json={"state": "failed"},
                    auth=self._auth(),
                )
        except httpx.HTTPError as exc:
            raise PluginUnavailableError(f"Airflow 停止失败: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise PluginUnavailableError(f"Airflow 停止失败(HTTP {response.status_code})")
