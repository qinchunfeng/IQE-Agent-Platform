#!/usr/bin/env python3
"""第 3 层验收：真实进程端到端冒烟（见 AGENTS.md「怎么算完成」）。

起一个真实 uvicorn 进程（独立临时库、随机空闲端口），跑通：
- 场景 1：Mock Jenkins 推事件 → 6 个 Agent 自动流转 → completed + 工单 + 7 段事件序列
- 场景 2：低置信度停在人工卡点 → approve → 补齐工单并跑完剩余阶段 → completed

不要求 Airflow / Qoder CN / 飞书在线（走降级到 Mock 的路径，这正是场景 4 的断言）。
不触碰 backend/data/iqe_demo.db，结尾会校验它没被改动。
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DEMO_DB = BACKEND / "data" / "iqe_demo.db"
EXPECTED_SEQUENCE = [
    "monitor_alert",
    "monitor_alert",
    "triage_result",
    "repro_result",
    "ticket_draft",
    "review_result",
    "report_item",
]


def die(step: str, why: str, fix: str) -> None:
    """面向 agent 的错误消息：哪里错、为什么、怎么改。"""

    print(f"ERROR  {step}\nWHY    {why}\nFIX    {fix}", file=sys.stderr)
    raise SystemExit(1)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(client: httpx.Client, base: str, proc: subprocess.Popen, deadline: float) -> None:
    while time.time() < deadline:
        if proc.poll() is not None:
            die(
                "启动后端进程",
                f"uvicorn 已退出，退出码 {proc.returncode}",
                "先单独跑 ./scripts/run_backend.sh 看启动日志，再回来查冒烟环境",
            )
        try:
            response = client.get(f"{base}/api/health", timeout=2.0)
            if response.status_code == 200 and response.json().get("status") == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    die("等待 /api/health 就绪", f"{deadline - time.time():.0f} 秒内没有探活成功", "检查端口冲突或 app.main 的 lifespan 是否卡住")


def wait_trace(
    client: httpx.Client, base: str, trace_id: str, expected: set[str], timeout: float
) -> dict[str, Any]:
    deadline = time.time() + timeout
    trace: dict[str, Any] = {}
    while time.time() < deadline:
        trace = client.get(f"{base}/api/traces/{trace_id}").json()
        if trace.get("run", {}).get("status") in expected:
            return trace
        time.sleep(0.1)
    die(
        "等待 Run 进入终态",
        f"trace {trace_id} 未在 {timeout:g} 秒内到达 {sorted(expected)}，实际状态 "
        f"{trace.get('run', {}).get('status')}",
        "看后端日志与 /api/traces/{trace_id} 的 events，定位卡在哪个阶段",
    )
    return {}  # pragma: no cover


def push(client: httpx.Client, base: str, case_id: str) -> dict[str, Any]:
    response = client.post(f"{base}/api/input-sources/mock_jenkins/push", json={"case_id": case_id})
    if response.status_code != 200:
        die("推送模拟事件", f"POST push 返回 {response.status_code}: {response.text}", "确认 mock_jenkins 输入源处于启用状态")
    return response.json()


def require(condition: bool, step: str, why: str, fix: str) -> None:
    if not condition:
        die(step, why, fix)


def main() -> int:
    if not (BACKEND / ".venv" / "bin" / "python").exists():
        die(
            "冒烟前置条件",
            "backend/.venv 不存在",
            "先跑一次 ./scripts/run_backend.sh（或 uv venv --python 3.12 backend/.venv && uv pip install -r backend/requirements.txt）",
        )

    workdir = Path(tempfile.mkdtemp(prefix="iqe-smoke-"))
    demo_db_before = DEMO_DB.stat().st_mtime_ns if DEMO_DB.exists() else None
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "IQE_DB_PATH": str(workdir / "smoke.db"),
        "IQE_HOST": "127.0.0.1",
        "IQE_PORT": str(port),
        "IQE_API_TOKEN": "",
    }
    log_path = workdir / "uvicorn.log"
    proc: subprocess.Popen | None = None

    try:
        with log_path.open("wb") as log_file:
            proc = subprocess.Popen(
                [
                    str(BACKEND / ".venv" / "bin" / "python"),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=str(BACKEND),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            with httpx.Client() as client:
                wait_health(client, base, proc, time.time() + 30)

                # 场景 1：全自动链路
                scene1 = push(client, base, "IQE-CASE-001")
                trace1 = wait_trace(client, base, scene1["trace_id"], {"completed", "failed", "rejected"}, 60)
                require(
                    trace1["run"]["status"] == "completed",
                    "场景 1 端到端",
                    f"预期 completed，实际 {trace1['run']['status']}（error_reason={trace1['run'].get('error_reason')}）",
                    "查 /api/traces 里失败的 Agent 与其 payload",
                )
                sequence = [event["event_type"] for event in trace1["events"]]
                require(
                    sequence == EXPECTED_SEQUENCE,
                    "场景 1 事件序列",
                    f"预期 {EXPECTED_SEQUENCE}，实际 {sequence}",
                    "确认 seed.py 的默认流水线 6 个阶段与 human_gate 配置未被改动",
                )
                require(
                    str((trace1.get("ticket") or {}).get("ticket_key", "")).startswith("IQE-"),
                    "场景 1 工单落库",
                    f"trace 中没有 Mock Jira 工单：{trace1.get('ticket')}",
                    "检查 ticket_agent 与 jira_mock 插件是否启用",
                )

                # 场景 2：人工卡点 → 批准后跑完剩余阶段
                scene2 = push(client, base, "IQE-CASE-019")
                trace2 = wait_trace(client, base, scene2["trace_id"], {"waiting_human", "failed"}, 60)
                require(
                    trace2["run"]["status"] == "waiting_human",
                    "场景 2 人工卡点",
                    f"低置信度案例应停在 waiting_human，实际 {trace2['run']['status']}",
                    "检查 reviewer 插件的 confidence_threshold 是否仍为 0.7",
                )
                approve = client.post(
                    f"{base}/api/runs/{scene2['run_id']}/review",
                    json={"action": "approve", "reason": "冒烟测试批准"},
                )
                require(
                    approve.status_code == 200,
                    "场景 2 批准后恢复执行",
                    f"POST review 返回 {approve.status_code}: {approve.text}",
                    "确认该 Run 仍处于 waiting_human 且流水线含 human_gate 阶段",
                )
                approved = approve.json()
                require(
                    approved["run"]["status"] == "completed",
                    "场景 2 批准后台账收敛",
                    f"批准后的状态是 {approved['run']['status']}",
                    "查恢复执行后 Reporting 阶段的输出事件是否通过信封校验",
                )
                require(
                    _review_approved(approved),
                    "场景 2 审批留痕",
                    "approve 后 review_result 事件未记为 passed / reviewed_by=human",
                    "检查 review_run 是否更新了事件状态与 payload.reviewed_by",
                )

                # 全局健康：没有失败 Run、没有死信、仪表盘与实验面板可查
                traces = client.get(f"{base}/api/traces", params={"limit": 50}).json()["items"]
                broken = [run["run_id"] for run in traces if run["status"] in ("failed", "rejected")]
                require(
                    not broken,
                    "无失败 Run",
                    f"存在失败或驳回的 Run：{broken}",
                    f"读 {log_path} 与 /api/traces/{{trace_id}} 的 dead_letters 定位首个失败阶段",
                )
                dead_letters = [
                    entry
                    for trace_id in [run["trace_id"] for run in traces]
                    for entry in (client.get(f"{base}/api/traces/{trace_id}").json().get("dead_letters") or [])
                ]
                require(
                    not dead_letters,
                    "无死信",
                    f"死信表非空：{dead_letters}",
                    "死信说明某阶段输出未过信封校验或外部插件不可用，先修对应插件",
                )
                for path in ("/api/dashboard", "/api/experiments/summary", "/api/plugins"):
                    response = client.get(f"{base}{path}")
                    require(
                        response.status_code == 200,
                        f"接口 {path}",
                        f"返回 {response.status_code}: {response.text}",
                        "确认对应 service 与插件注册中心未因改动报错",
                    )
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=15)
        if _has_error_line(log_path):
            print("--- 后端日志（含 error） ---", file=sys.stderr)
            sys.stderr.write(_tail(log_path, 40))
        shutil.rmtree(workdir, ignore_errors=True)

    if demo_db_before is not None and DEMO_DB.exists() and DEMO_DB.stat().st_mtime_ns != demo_db_before:
        die(
            "冒烟测试收尾",
            "backend/data/iqe_demo.db 被冒烟测试改动了",
            "冒烟只应写 IQE_DB_PATH 指向的临时库，检查是否有代码路径绕开了 config.DB_PATH",
        )

    print(
        "SMOKE OK  真实进程跑通场景 1（6 Agent 自动流转 + 工单）与场景 2（人工卡点 → 批准 → 完成），"
        "0 失败 Run、0 死信，Demo 库未被触碰"
    )
    return 0


def _review_approved(trace: dict[str, Any]) -> bool:
    review = next(
        (event for event in reversed(trace["events"]) if event["event_type"] == "review_result"),
        None,
    )
    return bool(
        review
        and review["status"] == "passed"
        and review["payload"].get("reviewed_by") == "human"
        and review["payload"].get("decision") == "pass"
    )


def _has_error_line(path: Path) -> bool:
    return any(marker in path.read_text(errors="replace").lower() for marker in ("error", "traceback", "exception"))


def _tail(path: Path, lines: int) -> str:
    content = path.read_text(errors="replace").splitlines()
    return "\n".join(content[-lines:]) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
