"""IQE-Agent Platform Demo 后端入口。

运行:
    cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
文档 0.4:后端端口 8000。
"""

from __future__ import annotations

import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import API_TOKEN, APP_HOST, APP_NAME, APP_PORT, APP_VERSION, FRONTEND_ORIGINS
from .errors import DomainError
from .logging_config import configure_logging, get_logger
from .models.api import (
    ExperimentSummaryOut,
    FileUploadRequest,
    KnowledgeEntryOut,
    KnowledgeListOut,
    PipelineDefinition,
    PluginConfigRequest,
    PluginHealthOut,
    PluginListOut,
    PluginOut,
    PushEventOut,
    PushEventRequest,
    ReviewRequest,
    SourcePollRequest,
)
from .plugins.registry import registry
from .seed import seed_default_pipeline
from .services.pipeline_service import PipelineService
from .services.source_monitor import SourceMonitor

configure_logging()
logger = get_logger("iqe.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.initialize()
    service = PipelineService(registry)
    registry.set_runner(service.execute_run_task)
    seed_default_pipeline()
    monitor = SourceMonitor(registry, service)
    app.state.registry = registry
    app.state.service = service
    app.state.monitor = monitor
    await monitor.start()
    logger.info(
        "IQE-Agent Platform started",
        extra={"host": APP_HOST, "port": APP_PORT, "version": APP_VERSION},
    )
    try:
        yield
    finally:
        await monitor.stop()
        await registry.shutdown()
        logger.info("IQE-Agent Platform stopped")


app = FastAPI(
    title=f"{APP_NAME} Demo API",
    version=APP_VERSION,
    description="插件化 AI Agent 编排平台 Demo;确认结论与外部契约见 docs/待确认问题清单.md",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    # 【已确认 Q13】默认空 Token 表示本机 Demo 无鉴权;设置 IQE_API_TOKEN 后
    # 仅保护 /api/*,健康检查保持公开,便于探活。
    if not API_TOKEN:
        return await call_next(request)
    if request.method == "OPTIONS":
        # 交给 CORS 中间件处理预检,避免 Token 保护阻断浏览器预检。
        return await call_next(request)
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        expected = f"Bearer {API_TOKEN}"
        provided = request.headers.get("authorization", "")
        if not secrets.compare_digest(provided, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


@app.exception_handler(DomainError)
async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled api error", extra={"error": exc.__class__.__name__})
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    return response


def _service(request: Request) -> PipelineService:
    return request.app.state.service


def _registry(request: Request):
    return request.app.state.registry


# ---------------------------------------------------------------------- health


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# --------------------------------------------------------------------- plugins


@app.get("/api/plugins", response_model=PluginListOut)
async def list_plugins(
    request: Request, check_health: bool = Query(default=True)
) -> dict[str, Any]:
    categories = await _registry(request).list_plugins(check_health=check_health)
    return {"categories": categories}


@app.get("/api/plugins/{plugin_id}", response_model=PluginOut)
async def get_plugin(request: Request, plugin_id: str) -> dict[str, Any]:
    reg = _registry(request)
    health = await reg.health(plugin_id)
    return reg.plugin_summary(plugin_id, health)


@app.get("/api/plugins/{plugin_id}/health", response_model=PluginHealthOut)
async def plugin_health(request: Request, plugin_id: str) -> dict[str, Any]:
    return await _registry(request).health(plugin_id)


@app.post("/api/plugins/{plugin_id}/config", response_model=PluginOut)
async def configure_plugin(
    request: Request, plugin_id: str, payload: PluginConfigRequest
) -> dict[str, Any]:
    reg = _registry(request)
    reg.configure(plugin_id, payload.config)
    health = await reg.health(plugin_id)
    return reg.plugin_summary(plugin_id, health)


@app.post("/api/plugins/{plugin_id}/enable", response_model=PluginOut)
async def enable_plugin(request: Request, plugin_id: str) -> dict[str, Any]:
    reg = _registry(request)
    reg.set_enabled(plugin_id, True)
    health = await reg.health(plugin_id)
    return reg.plugin_summary(plugin_id, health)


@app.post("/api/plugins/{plugin_id}/disable", response_model=PluginOut)
async def disable_plugin(request: Request, plugin_id: str) -> dict[str, Any]:
    reg = _registry(request)
    reg.set_enabled(plugin_id, False)
    return reg.plugin_summary(plugin_id)


# ---------------------------------------------------------------- input source


@app.get("/api/input-sources/mock_jenkins/cases")
async def list_mock_cases(request: Request) -> dict[str, Any]:
    plugin = _registry(request).get("mock_jenkins")
    return {"items": plugin.list_cases()}


@app.post("/api/input-sources/mock_jenkins/push", response_model=PushEventOut)
async def push_mock_event(
    request: Request, payload: PushEventRequest
) -> dict[str, Any]:
    return await _service(request).push_event(payload.case_id)


@app.get("/api/input-sources/airflow_input/dags")
async def list_airflow_dags(request: Request) -> dict[str, Any]:
    plugin = _registry(request).get("airflow_input")
    dags = await plugin.list_dags()
    return {
        "items": [
            {
                "dag_id": dag.get("dag_id"),
                "is_paused": dag.get("is_paused"),
                "is_stale": dag.get("is_stale"),
                "timetable_summary": dag.get("timetable_summary"),
            }
            for dag in dags
        ]
    }


@app.post("/api/input-sources/file_input/upload")
async def upload_external_log(
    request: Request, payload: FileUploadRequest
) -> dict[str, Any]:
    plugin = _registry(request).get("file_input")
    path = plugin.save_upload(payload.filename, payload.content)
    return {"filename": path.name, "path": str(path), "size": path.stat().st_size}


@app.post("/api/input-sources/{plugin_id}/poll")
async def poll_input_source(
    request: Request, plugin_id: str, payload: SourcePollRequest
) -> dict[str, Any]:
    monitor = request.app.state.monitor
    items = await monitor.poll_plugin(
        plugin_id, limit=payload.limit, lookback_minutes=payload.lookback_minutes
    )
    return {"items": items, "count": len(items)}


# ------------------------------------------------------------------- pipelines


@app.get("/api/pipelines")
async def list_pipelines(request: Request) -> dict[str, Any]:
    return {"items": _service(request).list_pipelines()}


@app.post("/api/pipelines")
async def create_pipeline(
    request: Request, payload: PipelineDefinition
) -> dict[str, Any]:
    return _service(request).create_pipeline(payload)


@app.get("/api/pipelines/{pipeline_id}")
async def get_pipeline(request: Request, pipeline_id: str) -> dict[str, Any]:
    return _service(request).get_pipeline(pipeline_id)


# ---------------------------------------------------------------------- traces


@app.get("/api/traces")
async def list_traces(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    return {"items": _service(request).list_traces(limit=limit, status=status)}


@app.get("/api/traces/{trace_id}")
async def get_trace(request: Request, trace_id: str) -> dict[str, Any]:
    return _service(request).get_trace(trace_id)


@app.post("/api/runs/{run_id}/review")
async def review_run(
    request: Request, run_id: str, payload: ReviewRequest
) -> dict[str, Any]:
    # 返回完整 Trace(含 stages/metrics/available_actions),供前端审批后直接刷新。
    return await _service(request).review_run(run_id, payload.action, payload.reason)


@app.post("/api/runs/{run_id}/knowledge", response_model=KnowledgeEntryOut)
async def mark_knowledge(request: Request, run_id: str) -> dict[str, Any]:
    return _service(request).mark_knowledge(run_id)


@app.post("/api/runs/{run_id}/stop")
async def stop_run(request: Request, run_id: str) -> dict[str, Any]:
    return await _service(request).stop_run(run_id)


@app.get("/api/runs/{run_id}/notifications")
async def list_run_notifications(request: Request, run_id: str) -> dict[str, Any]:
    return {"items": _service(request).list_notifications(run_id)}


# ------------------------------------------------------------------- knowledge


@app.get("/api/knowledge", response_model=KnowledgeListOut)
async def list_knowledge(
    request: Request, query: str | None = Query(default=None, max_length=500)
) -> dict[str, Any]:
    return {"items": _service(request).list_knowledge(query)}


# ------------------------------------------------------------------- dashboards


@app.get("/api/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    return await _service(request).dashboard()


@app.get("/api/experiments/summary", response_model=ExperimentSummaryOut)
async def experiment_summary(request: Request) -> dict[str, Any]:
    return await _service(request).experiments()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=False)
