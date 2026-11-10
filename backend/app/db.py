"""SQLite 持久化。

文档第 2 节要求“存储插件”可插拔;文档未定义表结构【已确认 Q15/Q17】。
本模块由 sqlite_storage 插件封装为存储能力,平台服务通过该模块读写
run / trace event / knowledge / ticket / dead letter。
所有 SQL 使用参数绑定,避免注入。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DB_PATH

_WRITE_LOCK = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plugin_state (
    plugin_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id TEXT PRIMARY KEY,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    trace_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    orchestrator_configured TEXT NOT NULL,
    orchestrator_used TEXT NOT NULL,
    orchestrator_run_id TEXT,
    fallback_reason TEXT,
    current_stage TEXT,
    human_reason TEXT,
    error_reason TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    input_event_json TEXT NOT NULL,
    input_source TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id, id);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    entry_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT,
    root_cause TEXT,
    source_trace_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    ticket_key TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_trace_id ON tickets(trace_id);

CREATE TABLE IF NOT EXISTS dead_letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    trace_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    event_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_events (
    source_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_id, event_key)
);

CREATE TABLE IF NOT EXISTS run_notifications (
    run_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    status TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, plugin_id, status)
);
"""

_RUN_UPDATABLE = {
    "status",
    "orchestrator_used",
    "orchestrator_configured",
    "orchestrator_run_id",
    "fallback_reason",
    "current_stage",
    "human_reason",
    "error_reason",
    "finished_at",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _reader() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def _writer() -> Iterator[sqlite3.Connection]:
    with _WRITE_LOCK:
        connection = _connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _migrate_knowledge_columns(connection: sqlite3.Connection) -> None:
    """【已确认 Q6】为既有 Demo 数据库补齐知识条目结构化字段。"""

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(knowledge_entries)").fetchall()
    }
    if "summary" not in columns:
        connection.execute("ALTER TABLE knowledge_entries ADD COLUMN summary TEXT")
    if "root_cause" not in columns:
        connection.execute("ALTER TABLE knowledge_entries ADD COLUMN root_cause TEXT")


def _migrate_run_columns(connection: sqlite3.Connection) -> None:
    """为既有 Demo 数据库补充输入源列(输入源插件化扩展)。"""

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(runs)").fetchall()
    }
    if "input_source" not in columns:
        connection.execute("ALTER TABLE runs ADD COLUMN input_source TEXT")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _writer() as connection:
        connection.executescript(_SCHEMA)
        _migrate_knowledge_columns(connection)
        _migrate_run_columns(connection)


def reset_db_for_tests(path: Path) -> None:
    """仅供测试使用:切换 DB 文件并重建表。"""

    global DB_PATH
    DB_PATH = path
    init_db()


# ---------------------------------------------------------------- plugin state


def get_plugin_state(plugin_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute(
            "SELECT plugin_id, enabled, config_json, updated_at FROM plugin_state WHERE plugin_id = ?",
            (plugin_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "plugin_id": row["plugin_id"],
        "enabled": bool(row["enabled"]),
        "config": _loads(row["config_json"], {}),
        "updated_at": row["updated_at"],
    }


def list_plugin_states() -> dict[str, dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            "SELECT plugin_id, enabled, config_json, updated_at FROM plugin_state"
        ).fetchall()
    return {
        row["plugin_id"]: {
            "plugin_id": row["plugin_id"],
            "enabled": bool(row["enabled"]),
            "config": _loads(row["config_json"], {}),
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def upsert_plugin_state(plugin_id: str, enabled: bool, config: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO plugin_state(plugin_id, enabled, config_json, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET
                enabled = excluded.enabled,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (plugin_id, 1 if enabled else 0, _dumps(config), utc_now_iso()),
        )


# ------------------------------------------------------------------- pipelines


def save_pipeline(definition: dict[str, Any]) -> None:
    now = utc_now_iso()
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO pipelines(pipeline_id, definition_json, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(pipeline_id) DO UPDATE SET
                definition_json = excluded.definition_json,
                updated_at = excluded.updated_at
            """,
            (definition["pipeline_id"], _dumps(definition), now, now),
        )


def get_pipeline(pipeline_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute(
            "SELECT pipeline_id, definition_json, created_at, updated_at FROM pipelines WHERE pipeline_id = ?",
            (pipeline_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "pipeline_id": row["pipeline_id"],
        "definition": _loads(row["definition_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_pipelines() -> list[dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            "SELECT pipeline_id, definition_json, created_at, updated_at FROM pipelines ORDER BY created_at ASC"
        ).fetchall()
    return [
        {
            "pipeline_id": row["pipeline_id"],
            "definition": _loads(row["definition_json"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


# ------------------------------------------------------------------------ runs


def _run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "pipeline_id": row["pipeline_id"],
        "trace_id": row["trace_id"],
        "status": row["status"],
        "orchestrator_configured": row["orchestrator_configured"],
        "orchestrator_used": row["orchestrator_used"],
        "orchestrator_run_id": row["orchestrator_run_id"],
        "fallback_reason": row["fallback_reason"],
        "current_stage": row["current_stage"],
        "human_reason": row["human_reason"],
        "error_reason": row["error_reason"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "input_event": _loads(row["input_event_json"], {}),
        "input_source": row["input_source"],
    }


def create_run(run: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO runs(
                run_id, pipeline_id, trace_id, status, orchestrator_configured,
                orchestrator_used, orchestrator_run_id, fallback_reason, current_stage,
                human_reason, error_reason, started_at, finished_at, input_event_json,
                input_source
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["run_id"],
                run["pipeline_id"],
                run["trace_id"],
                run["status"],
                run["orchestrator_configured"],
                run["orchestrator_used"],
                run.get("orchestrator_run_id"),
                run.get("fallback_reason"),
                run.get("current_stage"),
                run.get("human_reason"),
                run.get("error_reason"),
                run["started_at"],
                run.get("finished_at"),
                _dumps(run["input_event"]),
                run.get("input_source"),
            ),
        )


def update_run(run_id: str, **fields: Any) -> None:
    unknown = set(fields) - _RUN_UPDATABLE
    if unknown:
        raise ValueError(f"不允许更新字段: {', '.join(sorted(unknown))}")
    if not fields:
        return
    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = list(fields.values()) + [run_id]
    with _writer() as connection:
        connection.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?", values)


def get_run(run_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _run_from_row(row) if row else None


def get_run_by_trace(trace_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute("SELECT * FROM runs WHERE trace_id = ?", (trace_id,)).fetchone()
    return _run_from_row(row) if row else None


def list_runs(limit: int = 50, since: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM runs"
    params: list[Any] = []
    if since:
        sql += " WHERE started_at >= ?"
        params.append(since)
    sql += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    with _reader() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [_run_from_row(row) for row in rows]


# ---------------------------------------------------------------------- events


def save_event(run_id: str, trace_id: str, event: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO events(
                run_id, trace_id, event_id, event_type, source_agent, status,
                confidence, event_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                status = excluded.status,
                confidence = excluded.confidence,
                event_json = excluded.event_json
            """,
            (
                run_id,
                trace_id,
                event["event_id"],
                str(event["event_type"]),
                event["source_agent"],
                str(event["status"]),
                float(event["confidence"]),
                _dumps(event),
                utc_now_iso(),
            ),
        )


def update_event(event: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            "UPDATE events SET status = ?, confidence = ?, event_json = ? WHERE event_id = ?",
            (
                str(event["status"]),
                float(event["confidence"]),
                _dumps(event),
                event["event_id"],
            ),
        )


def list_events(run_id: str) -> list[dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            "SELECT event_json FROM events WHERE run_id = ? ORDER BY id ASC", (run_id,)
        ).fetchall()
    return [_loads(row["event_json"], {}) for row in rows]


def get_latest_event(run_id: str, event_type: str | None = None) -> dict[str, Any] | None:
    sql = "SELECT event_json FROM events WHERE run_id = ?"
    params: list[Any] = [run_id]
    if event_type:
        sql += " AND event_type = ?"
        params.append(event_type)
    sql += " ORDER BY id DESC LIMIT 1"
    with _reader() as connection:
        row = connection.execute(sql, params).fetchone()
    return _loads(row["event_json"], {}) if row else None


# ------------------------------------------------------------------- knowledge


def save_knowledge(entry: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_entries(
                entry_id, title, content, category, summary, root_cause,
                source_trace_id, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["entry_id"],
                entry["title"],
                entry["content"],
                entry["category"],
                entry.get("summary"),
                entry.get("root_cause"),
                entry.get("source_trace_id"),
                entry["created_at"],
            ),
        )


def list_knowledge(limit: int = 200) -> list[dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            "SELECT * FROM knowledge_entries ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_knowledge(entry_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_entries WHERE entry_id = ?", (entry_id,)
        ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------- tickets


def count_tickets() -> int:
    with _reader() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()
    return int(row["count"])


def save_ticket(ticket: dict[str, Any]) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO tickets(ticket_id, ticket_key, trace_id, title, status, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket["ticket_id"],
                ticket["ticket_key"],
                ticket["trace_id"],
                ticket["title"],
                ticket["status"],
                _dumps(ticket.get("payload", {})),
                ticket["created_at"],
            ),
        )


def get_ticket_by_trace(trace_id: str) -> dict[str, Any] | None:
    with _reader() as connection:
        row = connection.execute(
            "SELECT * FROM tickets WHERE trace_id = ? ORDER BY created_at DESC LIMIT 1",
            (trace_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "ticket_id": row["ticket_id"],
        "ticket_key": row["ticket_key"],
        "trace_id": row["trace_id"],
        "title": row["title"],
        "status": row["status"],
        "payload": _loads(row["payload_json"], {}),
        "created_at": row["created_at"],
    }


def count_tickets_since(since: str) -> int:
    with _reader() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM tickets WHERE created_at >= ?", (since,)
        ).fetchone()
    return int(row["count"])


# ---------------------------------------------------------------- dead letters


def save_dead_letter(
    trace_id: str, reason: str, *, run_id: str | None = None, event: dict[str, Any] | None = None
) -> None:
    with _writer() as connection:
        connection.execute(
            """
            INSERT INTO dead_letters(run_id, trace_id, reason, event_json, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (run_id, trace_id, reason, _dumps(event) if event is not None else None, utc_now_iso()),
        )


def list_dead_letters(trace_id: str) -> list[dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            "SELECT * FROM dead_letters WHERE trace_id = ? ORDER BY id ASC", (trace_id,)
        ).fetchall()
    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "trace_id": row["trace_id"],
            "reason": row["reason"],
            "event": _loads(row["event_json"], None),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# -------------------------------------------------------------- source events


def mark_source_event_seen(source_id: str, event_key: str) -> bool:
    """输入源事件去重。返回 True 表示首次出现,False 表示已处理过。"""

    with _writer() as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO source_events(source_id, event_key, created_at) VALUES(?, ?, ?)",
            (source_id, event_key, utc_now_iso()),
        )
        return cursor.rowcount == 1


def reset_source_events(source_id: str) -> None:
    """仅用于测试/演示重放:清空指定输入源的已处理游标。"""

    with _writer() as connection:
        connection.execute("DELETE FROM source_events WHERE source_id = ?", (source_id,))


# ---------------------------------------------------------------- notifications


def claim_run_notification(run_id: str, plugin_id: str, status: str) -> bool:
    """按 Run + 插件 + 状态幂等认领一次通知。返回 True 表示由本次调用发送。"""

    now = utc_now_iso()
    with _writer() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO run_notifications(
                run_id, plugin_id, status, state, attempts, error, created_at, updated_at
            ) VALUES(?, ?, ?, 'pending', 0, NULL, ?, ?)
            """,
            (run_id, plugin_id, status, now, now),
        )
        return cursor.rowcount == 1


def update_run_notification(
    run_id: str, plugin_id: str, status: str, *, state: str, attempts: int, error: str | None
) -> None:
    with _writer() as connection:
        connection.execute(
            """
            UPDATE run_notifications
            SET state = ?, attempts = ?, error = ?, updated_at = ?
            WHERE run_id = ? AND plugin_id = ? AND status = ?
            """,
            (state, attempts, error, utc_now_iso(), run_id, plugin_id, status),
        )


def list_run_notifications(run_id: str) -> list[dict[str, Any]]:
    with _reader() as connection:
        rows = connection.execute(
            """
            SELECT run_id, plugin_id, status, state, attempts, error, created_at, updated_at
            FROM run_notifications WHERE run_id = ? ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]
