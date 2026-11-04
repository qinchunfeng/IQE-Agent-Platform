"""输入源改造与画布扩展测试。

覆盖:
- Airflow 从编排器改为输入源插件,支持 dag_ids 为空=全部;
- 外部日志文件上传/轮询/去重/自动触发;
- 流水线画布新增输入源与 Agent(允许重复 Agent 阶段);
- 真实 LLM 常见的 ```json 围栏与前后解释文字解析。
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.agents.monitor_agent import MonitorAgent
from app.plugins.airflow_input import AirflowInputSourcePlugin, _parse_dag_ids
from app.plugins.qoder_cn_llm import _extract_json_object


def _default_definition(client: TestClient) -> dict:
    return client.get("/api/pipelines").json()["items"][0]["definition"]


def _wait_trace(client: TestClient, trace_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/traces/{trace_id}")
        if response.status_code == 200:
            last = response.json()
            if last["run"]["status"] in {"completed", "failed", "rejected", "stopped"}:
                return last
        time.sleep(0.2)
    return last


def test_airflow_plugin_is_input_source_with_all_dags_default():
    plugin = AirflowInputSourcePlugin(config={"api_url": "http://airflow.local"})
    assert plugin.plugin_type == "input_source"
    assert plugin.config["dag_ids"] == ""
    assert plugin.config["lookback_minutes"] == 60
    assert plugin.capabilities["polling"] is True
    assert _parse_dag_ids("") == []
    assert _parse_dag_ids("dag_a, dag_b\n dag_c") == ["dag_a", "dag_b", "dag_c"]


def test_airflow_event_contains_run_and_task_evidence():
    plugin = AirflowInputSourcePlugin(config={"api_url": "http://airflow.local"})
    run = {
        "dag_run_id": "manual__2026-11-01T22:27:56+00:00",
        "state": "failed",
        "run_type": "manual",
        "logical_date": "2026-11-01T22:27:56Z",
        "conf": {"ENV_TESTS_REPO": "http://git/testframework.git", "BRANCH": "main"},
    }
    tasks = [
        {
            "task_id": "run_9-stop-container",
            "state": "failed",
            "try_number": 1,
            "operator": "DeviceConnectionSSHRemoteJobOperator",
        }
    ]
    event = plugin._build_event(
        dag_id="test_flash_attention_flow",
        run=run,
        tasks=tasks,
        log_excerpt="docker stop timeout\npassword=secret-value\nAuthorization: Bearer abc",
    )
    assert event.event_type.value == "monitor_alert"
    assert event.source_agent == "airflow_input"
    assert event.payload["job_name"] == "test_flash_attention_flow"
    assert event.payload["stage"] == "run_9-stop-container"
    assert event.payload["airflow_dag_id"] == "test_flash_attention_flow"
    assert event.payload["failed_tasks"][0]["try_number"] == 1
    assert "password=***" in event.payload["log_excerpt"]
    assert "Bearer ***" not in event.payload["log_excerpt"]
    assert "secret-value" not in event.payload["log_excerpt"]


def test_file_input_upload_poll_and_auto_trigger():
    with TestClient(app) as client:
        original = _default_definition(client)
        definition = dict(original)
        definition["sources"] = list(original["sources"]) + [
            {
                "source_id": "file_input",
                "plugin_id": "file_input",
                "label": "外部日志文件",
                "enabled": True,
            }
        ]
        saved = client.post("/api/pipelines", json=definition)
        assert saved.status_code == 200, saved.text
        try:
            upload = client.post(
                "/api/input-sources/file_input/upload",
                json={
                    "filename": "gpu_error.log",
                    "content": "ERROR device init failed\npassword=abc123\nTraceback: driver crash",
                },
            )
            assert upload.status_code == 200, upload.text

            poll = client.post(
                "/api/input-sources/file_input/poll",
                json={"limit": 1, "lookback_minutes": 60},
            )
            assert poll.status_code == 200, poll.text
            items = poll.json()["items"]
            assert len(items) == 1
            trace = _wait_trace(client, items[0]["trace_id"])
            assert trace["run"]["input_source"] == "file_input"
            assert trace["run"]["status"] in {"completed", "running", "waiting_human"}
            assert "password=***" in trace["events"][0]["payload"]["log_excerpt"]

            # 同一文件未变化时不应重复触发。
            again = client.post(
                "/api/input-sources/file_input/poll",
                json={"limit": 1, "lookback_minutes": 60},
            )
            assert again.status_code == 200
            assert again.json()["items"] == []
        finally:
            client.post("/api/pipelines", json=original)


def test_canvas_can_add_source_and_duplicate_agent_stage():
    with TestClient(app) as client:
        original = _default_definition(client)
        definition = dict(original)
        definition["sources"] = list(original["sources"]) + [
            {
                "source_id": "airflow_input",
                "plugin_id": "airflow_input",
                "label": "Airflow 输入源",
                "enabled": True,
            }
        ]
        definition["stages"] = list(original["stages"]) + [
            {"agent": "monitor_agent", "llm_provider": "mock_llm"}
        ]
        try:
            saved = client.post("/api/pipelines", json=definition)
            assert saved.status_code == 200, saved.text
            body = saved.json()["definition"]
            assert len(body["sources"]) == len(original["sources"]) + 1
            assert len(body["stages"]) == len(original["stages"]) + 1
            assert body["stages"][-1]["agent"] == "monitor_agent"
        finally:
            client.post("/api/pipelines", json=original)


def test_canvas_rejects_non_input_source_plugin():
    with TestClient(app) as client:
        original = _default_definition(client)
        definition = dict(original)
        definition["sources"] = [
            {
                "source_id": "bad",
                "plugin_id": "monitor_agent",
                "label": "bad",
                "enabled": True,
            }
        ]
        response = client.post("/api/pipelines", json=definition)
        assert response.status_code == 422


def test_llm_extracts_json_from_fence_and_prose():
    assert _extract_json_object('```json\n{"summary":"ok"}\n```') == {"summary": "ok"}
    assert _extract_json_object('结果如下: {"summary":"ok"} 以上。') == {"summary": "ok"}
    assert _extract_json_object("not json") is None


def test_agent_duplicate_stage_prompt_schema_still_valid():
    # 画布允许重复 Agent;配置 schema 仍由插件类提供。
    assert "system_prompt" in MonitorAgent.config_schema
