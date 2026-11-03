"""端到端 API 流程测试(场景 1/2/3 + 插件脱敏)。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module", autouse=True)
def clean_api_database():
    """Agent 单测会写知识库,API 场景测试使用独立空库,避免跨测试污染。"""

    db_path = Path(os.environ["IQE_DB_PATH"])
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    yield


def _wait_trace(client: TestClient, trace_id: str, expected: set[str], timeout: float = 8.0):
    deadline = time.time() + timeout
    trace = {}
    while time.time() < deadline:
        response = client.get(f"/api/traces/{trace_id}")
        assert response.status_code == 200, response.text
        trace = response.json()
        if trace["run"]["status"] in expected:
            return trace
        time.sleep(0.05)
    raise AssertionError(f"trace did not reach {expected}: {trace}")


def _push(client: TestClient, case_id: str):
    response = client.post(
        "/api/input-sources/mock_jenkins/push", json={"case_id": case_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_scene_1_end_to_end_and_envelope():
    with TestClient(app) as client:
        payload = _push(client, "IQE-CASE-001")
        trace = _wait_trace(client, payload["trace_id"], {"completed", "failed", "rejected"})
        assert trace["run"]["status"] == "completed"
        assert trace["ticket"]["ticket_key"].startswith("IQE-")

        event_types = [event["event_type"] for event in trace["events"]]
        assert event_types == [
            "monitor_alert",
            "monitor_alert",
            "triage_result",
            "repro_result",
            "ticket_draft",
            "review_result",
            "report_item",
        ]
        for event in trace["events"]:
            assert set(event) == {
                "event_id",
                "event_type",
                "source_agent",
                "timestamp",
                "trace_id",
                "confidence",
                "evidence_links",
                "status",
                "model_info",
                "payload",
            }
            assert 0.0 <= event["confidence"] <= 1.0
            assert set(event["model_info"]) == {
                "model_loc",
                "model_name",
                "latency_ms",
                "cost_token",
            }
        assert trace["metrics"]["tat_seconds"] > 0
        assert trace["metrics"]["tat_source"] == "simulated_mock"
        assert "mark_knowledge" in trace["available_actions"]


def test_scene_2_low_confidence_human_gate_and_reject():
    with TestClient(app) as client:
        payload = _push(client, "IQE-CASE-019")
        trace = _wait_trace(client, payload["trace_id"], {"waiting_human", "failed"})
        assert trace["run"]["status"] == "waiting_human"
        assert trace["metrics"]["confidence"] == 0.6
        assert set(trace["available_actions"]) >= {"approve", "reject"}

        response = client.post(
            f"/api/runs/{payload['run_id']}/review",
            json={"action": "reject", "reason": "证据不足"},
        )
        assert response.status_code == 200, response.text
        rejected = response.json()
        assert rejected["run"]["status"] == "rejected"
        assert rejected["run"]["human_reason"] == "证据不足"
        assert rejected["ticket"] is None


def test_scene_3_knowledge_boost():
    with TestClient(app) as client:
        first = _push(client, "IQE-CASE-017")
        first_trace = _wait_trace(client, first["trace_id"], {"completed", "rejected", "failed"})
        assert first_trace["run"]["status"] == "completed"
        triage_before = next(
            event for event in first_trace["events"] if event["event_type"] == "triage_result"
        )
        assert triage_before["confidence"] == 0.75
        assert triage_before["model_info"]["latency_ms"] == 180_000

        response = client.post(f"/api/runs/{first['run_id']}/knowledge")
        assert response.status_code == 200, response.text
        entry = response.json()
        assert entry["category"] == "driver_compatibility"
        assert entry["root_cause"] == "基于日志关键词判定为 driver_compatibility"
        assert entry["summary"]

        second = _push(client, "IQE-CASE-018")
        second_trace = _wait_trace(client, second["trace_id"], {"completed", "rejected", "failed"})
        triage_after = next(
            event for event in second_trace["events"] if event["event_type"] == "triage_result"
        )
        assert triage_after["confidence"] == 0.92
        assert triage_after["payload"]["kb_hit"] is True
        assert triage_after["model_info"]["latency_ms"] == 30_000


def test_plugin_categories_and_secret_masking():
    with TestClient(app) as client:
        response = client.get("/api/plugins?check_health=false")
        assert response.status_code == 200
        categories = response.json()["categories"]
        assert {category["type"] for category in categories} == {
            "input_source",
            "agent",
            "knowledge_base",
            "tool",
            "orchestrator",
            "llm_provider",
            "event_bus",
            "storage",
        }
        assert len(next(c for c in categories if c["type"] == "agent")["plugins"]) == 6

        configured = client.post(
            "/api/plugins/qoder_cn/config",
            json={"config": {"api_url": "", "api_key": "super-secret", "model": "", "timeout_seconds": 10}},
        )
        assert configured.status_code == 200, configured.text
        assert configured.json()["config"]["api_key"] == "***"

        # 回传脱敏值不得覆盖真实密钥
        kept = client.post(
            "/api/plugins/qoder_cn/config",
            json={"config": {"api_url": "", "api_key": "***", "model": "", "timeout_seconds": 10}},
        )
        assert kept.status_code == 200
        assert kept.json()["config"]["api_key"] == "***"


def test_dashboard_and_experiments():
    with TestClient(app) as client:
        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        dashboard_body = dashboard.json()
        stats = dashboard_body["stats"]
        assert stats["completed"] >= 2
        assert stats["ticket_count"] >= 2
        assert dashboard_body["timezone"]
        assert stats["avg_tat_source"] in {"simulated_mock", "measured", "mixed"}

        experiments = client.get("/api/experiments/summary")
        assert experiments.status_code == 200
        body = experiments.json()
        assert {item["name"] for item in body["baselines"]} >= {
            "Qoder CN Cloud",
            "Mock Local(模拟 Strix Halo)",
        }
        assert body["computed"]["knowledge_stats"]["kb_hit"]["count"] >= 1
        assert body["computed"]["avg_tat_source"] in {
            "simulated_mock",
            "measured",
            "mixed",
        }


def test_airflow_without_delegation_uses_memory_orchestrator():
    with TestClient(app) as client:
        plugins = client.get("/api/plugins?check_health=false").json()["categories"]
        airflow = next(
            plugin
            for category in plugins
            for plugin in category["plugins"]
            if plugin["plugin_id"] == "airflow_orchestrator"
        )
        assert airflow["capabilities"]["agent_callback"] is False

        enabled = client.post("/api/plugins/airflow_orchestrator/enable")
        assert enabled.status_code == 200, enabled.text
        configured = client.post(
            "/api/plugins/airflow_orchestrator/config",
            json={
                "config": {
                    "api_url": "http://127.0.0.1:18080",
                    "username": "",
                    "password": "",
                    "dag_id_prefix": "",
                    "delegate_execution": False,
                    "timeout_seconds": 10,
                }
            },
        )
        assert configured.status_code == 200, configured.text
        try:
            payload = _push(client, "IQE-CASE-001")
            trace = _wait_trace(
                client, payload["trace_id"], {"completed", "failed", "rejected"}
            )
            assert trace["run"]["orchestrator_used"] == "memory_orchestrator"
            assert "执行委托" in (trace["run"]["fallback_reason"] or "")
        finally:
            client.post("/api/plugins/airflow_orchestrator/disable")


def test_optional_bearer_token(monkeypatch):
    monkeypatch.setattr("app.main.API_TOKEN", "secret-token")
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/health").status_code == 200
        authorized = client.get(
            "/api/dashboard", headers={"Authorization": "Bearer secret-token"}
        )
        assert authorized.status_code == 200
        preflight = client.options(
            "/api/dashboard",
            headers={
                "Origin": "http://127.0.0.1:3200",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200


def test_agent_prompt_plugin_config_and_stage_override():
    with TestClient(app) as client:
        plugins = client.get("/api/plugins?check_health=false").json()["categories"]
        monitor = next(
            plugin
            for category in plugins
            for plugin in category["plugins"]
            if plugin["plugin_id"] == "monitor_agent"
        )
        assert monitor["config_schema"]["system_prompt"]["multiline"] is True
        original_prompt = monitor["config"]["system_prompt"]
        assert original_prompt

        custom_prompt = "CUSTOM MONITOR PROMPT FROM API"
        configured = client.post(
            "/api/plugins/monitor_agent/config",
            json={"config": {"system_prompt": custom_prompt}},
        )
        assert configured.status_code == 200, configured.text
        assert configured.json()["config"]["system_prompt"] == custom_prompt

        pipeline = client.get("/api/pipelines/iqe_validation_v1").json()
        definition = pipeline["definition"]
        original_stage_prompt = definition["stages"][0].get("system_prompt")
        definition["stages"][0]["system_prompt"] = "STAGE MONITOR PROMPT"
        try:
            saved = client.post("/api/pipelines", json=definition)
            assert saved.status_code == 200, saved.text
            assert (
                saved.json()["definition"]["stages"][0]["system_prompt"]
                == "STAGE MONITOR PROMPT"
            )

            payload = _push(client, "IQE-CASE-001")
            trace = _wait_trace(
                client, payload["trace_id"], {"completed", "failed", "rejected"}
            )
            monitor_event = next(
                event
                for event in trace["events"]
                if event["source_agent"] == "monitor_agent"
            )
            assert monitor_event["payload"]["prompt_source"] == "stage"
            assert monitor_event["payload"]["prompt_version"]
            assert len(monitor_event["payload"]["prompt_hash"]) == 12
        finally:
            if original_stage_prompt is None:
                definition["stages"][0].pop("system_prompt", None)
            else:
                definition["stages"][0]["system_prompt"] = original_stage_prompt
            client.post("/api/pipelines", json=definition)
            client.post(
                "/api/plugins/monitor_agent/config",
                json={"config": {"system_prompt": original_prompt}},
            )
