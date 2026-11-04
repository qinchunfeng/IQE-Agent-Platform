"""飞书通知插件测试。

全部使用 httpx.MockTransport,不访问真实飞书,也不使用真实凭据。
覆盖:卡片内容、Webhook/应用两种发送、重试、幂等与失败隔离、密钥脱敏。
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.errors import NotificationError
from app.main import app
from app.plugins.feishu_notifier import FeishuNotifierPlugin
from app.security import mask_config
from app.services.notification_service import NotificationService

REPORT = {
    "run_id": "run-123",
    "trace_id": "trace-123",
    "pipeline_id": "iqe_validation_v1",
    "status": "completed",
    "case_id": "IQE-CASE-001",
    "title": "GPU init failed",
    "category": "driver_compatibility",
    "confidence": 0.92,
    "ticket_key": "IQE-7",
    "tat_seconds": 480,
    "tat_source": "simulated_mock",
    "input_source": "airflow_input",
    "orchestrator_used": "memory_orchestrator",
    "stages": [
        {"agent": "monitor_agent", "status": "passed"},
        {"agent": "triage_agent", "status": "passed"},
        {"agent": "reporting_agent", "status": "passed"},
    ],
}


@pytest.fixture(autouse=True)
def _ensure_db():
    db.init_db()


def _webhook_plugin(handler, **overrides: Any) -> FeishuNotifierPlugin:
    config = {
        "mode": "webhook",
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/secret-token",
        "dashboard_url": "http://127.0.0.1:3200",
        "timeout_seconds": 3,
        "max_retries": 0,
        "retry_delay_seconds": 0,
        **overrides,
    }
    return FeishuNotifierPlugin(
        config=config,
        dependencies={"http_transport": httpx.MockTransport(handler)},
    )


def test_webhook_card_contains_report_fields():
    plugin = _webhook_plugin(lambda request: httpx.Response(200, json={"code": 0}))
    card = plugin.build_card(REPORT)
    assert card["header"]["template"] == "green"
    content = json.dumps(card, ensure_ascii=False)
    assert "IQE-CASE-001" in content
    assert "IQE-7" in content
    assert "driver_compatibility" in content
    assert "480 秒(模拟业务耗时)" in content
    assert "http://127.0.0.1:3200/traces/trace-123" in content
    assert plugin.is_configured()[0] is True


async def test_webhook_send_payload():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    plugin = _webhook_plugin(handler, max_retries=2)
    result = await plugin.send_report(REPORT)
    assert result["mode"] == "webhook"
    assert result["attempts"] == 1

    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == plugin.config["webhook_url"]
    body = json.loads(request.content)
    assert body["msg_type"] == "interactive"
    assert body["card"]["header"]["template"] == "green"
    # URL/密钥不得出现在卡片或错误信息中
    assert "secret-token" not in json.dumps(body)


async def test_app_mode_fetches_token_and_sends_message():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "msg": "ok", "tenant_access_token": "t-token"}
            )
        if request.url.path.endswith("/im/v1/messages"):
            return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})
        return httpx.Response(404, json={"code": 404})

    plugin = FeishuNotifierPlugin(
        config={
            "mode": "app",
            "app_id": "cli_test",
            "app_secret": "app-secret-value",
            "api_base": "https://open.feishu.cn",
            "receive_id_type": "chat_id",
            "receive_id": "oc_group",
            "dashboard_url": "http://127.0.0.1:3200",
            "timeout_seconds": 3,
            "max_retries": 0,
            "retry_delay_seconds": 0,
        },
        dependencies={"http_transport": httpx.MockTransport(handler)},
    )
    result = await plugin.send_report(REPORT)
    assert result["mode"] == "app"
    assert result["message_id"] == "om_1"

    token_request, message_request = seen
    assert json.loads(token_request.content)["app_secret"] == "app-secret-value"
    assert message_request.headers["Authorization"] == "Bearer t-token"
    assert message_request.url.params["receive_id_type"] == "chat_id"
    body = json.loads(message_request.content)
    assert body["receive_id"] == "oc_group"
    assert body["msg_type"] == "interactive"
    assert json.loads(body["content"])["header"]["template"] == "green"


async def test_retry_on_server_error_and_stop_on_client_error():
    attempts = {"count": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(500, json={"code": 500})
        return httpx.Response(200, json={"code": 0})

    plugin = _webhook_plugin(flaky, max_retries=2)
    result = await plugin.send_report(REPORT)
    assert result["attempts"] == 3
    assert attempts["count"] == 3

    attempts["count"] = 0

    def bad_request(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"code": 9499, "msg": "invalid"})

    plugin = _webhook_plugin(bad_request, max_retries=2)
    with pytest.raises(NotificationError) as excinfo:
        await plugin.send_report(REPORT)
    assert excinfo.value.retryable is False
    assert attempts["count"] == 1


def test_webhook_and_secret_are_masked():
    masked = mask_config(
        FeishuNotifierPlugin.config_schema,
        {
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/secret-token",
            "app_secret": "app-secret-value",
            "app_id": "cli_test",
        },
    )
    assert masked["webhook_url"] == "***"
    assert masked["app_secret"] == "***"
    assert masked["app_id"] == "cli_test"


class _StubNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    def enabled_for_status(self, status: str) -> bool:
        return True

    def is_configured(self) -> tuple[bool, str]:
        return True, "ok"

    async def send_report(self, report: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(report)
        if self.fail:
            raise NotificationError("mock failure", retryable=False)
        return {"attempts": 1}


class _StubRegistry:
    def __init__(self, plugin: _StubNotifier, enabled: bool = True) -> None:
        self.plugin = plugin
        self.enabled = enabled

    def has(self, plugin_id: str) -> bool:
        return True

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled

    def get(self, plugin_id: str) -> _StubNotifier:
        return self.plugin


def _create_run(run_id: str) -> dict[str, Any]:
    run = {
        "run_id": run_id,
        "pipeline_id": "p_notify",
        "trace_id": f"trace-{run_id}",
        "status": "completed",
        "orchestrator_configured": "memory_orchestrator",
        "orchestrator_used": "memory_orchestrator",
        "orchestrator_run_id": None,
        "fallback_reason": None,
        "current_stage": None,
        "human_reason": None,
        "error_reason": None,
        "started_at": db.utc_now_iso(),
        "finished_at": db.utc_now_iso(),
        "input_event": {"payload": {"case_id": "IQE-CASE-001", "title": "notify"}},
        "input_source": "mock_jenkins",
    }
    db.create_run(run)
    return run


async def test_notification_service_is_idempotent_per_status():
    plugin = _StubNotifier()
    service = NotificationService(_StubRegistry(plugin))
    run = _create_run("run-notify-idempotent")

    await service.notify_run(run["run_id"], "completed")
    await service.notify_run(run["run_id"], "completed")
    assert len(plugin.calls) == 1
    assert plugin.calls[0]["case_id"] == "IQE-CASE-001"

    record = service.get_notification(run["run_id"], "completed")
    assert record is not None
    assert record["state"] == "sent"

    # 同一 Run 的不同状态允许各自通知一次。
    await service.notify_run(run["run_id"], "rejected", "证据不足")
    assert len(plugin.calls) == 2


async def test_notification_failure_is_isolated():
    plugin = _StubNotifier()
    plugin.fail = True
    service = NotificationService(_StubRegistry(plugin))
    run = _create_run("run-notify-failure")

    result = await service.notify_run(run["run_id"], "failed", "boom")
    assert result is not None
    assert result["state"] == "failed"
    assert "mock failure" in result["error"]


async def test_disabled_notifier_is_skipped():
    plugin = _StubNotifier()
    service = NotificationService(_StubRegistry(plugin, enabled=False))
    run = _create_run("run-notify-disabled")

    assert await service.notify_run(run["run_id"], "completed") is None
    assert plugin.calls == []


def test_plugin_is_registered_and_disabled_by_default():
    with TestClient(app) as client:
        categories = client.get("/api/plugins?check_health=false").json()["categories"]
        plugin = next(
            item
            for category in categories
            for item in category["plugins"]
            if item["plugin_id"] == "feishu_notifier"
        )
        assert plugin["plugin_type"] == "tool"
        assert plugin["enabled"] is False
        assert plugin["config"]["mode"] == "webhook"
        assert plugin["config_schema"]["webhook_url"]["secret"] is True
        assert plugin["config_schema"]["app_secret"]["secret"] is True


def test_pipeline_schedules_notification_on_completion(monkeypatch):
    with TestClient(app) as client:
        service = app.state.service
        calls: list[tuple[str, str, str | None]] = []
        monkeypatch.setattr(
            service.notifications,
            "schedule",
            lambda run_id, status, reason=None: calls.append((run_id, status, reason)),
        )
        response = client.post(
            "/api/input-sources/mock_jenkins/push", json={"case_id": "IQE-CASE-001"}
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        trace_id = response.json()["trace_id"]

        deadline = time.time() + 8
        while time.time() < deadline:
            trace = client.get(f"/api/traces/{trace_id}").json()
            if trace["run"]["status"] == "completed":
                break
            time.sleep(0.05)

        assert (run_id, "completed", None) in calls
