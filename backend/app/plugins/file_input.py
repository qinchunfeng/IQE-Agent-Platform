"""外部运行日志/错误日志文件输入源。

【待确认 Q24】画布自定义输入源扩展:监控本地目录中的外部日志文件,
把新增/变更文件转换为标准 monitor_alert 事件,再触发 IQE Agent。

安全约束:
- 文件名只允许 basename,拒绝路径穿越;
- 单文件读取上限 5MB,超出跳过;
- 内容截断并脱敏 password/token/api_key/Bearer 等敏感字段。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .. import db
from ..config import DATA_DIR
from ..errors import ConfigurationError
from ..models.event import EventEnvelope, EventStatus, EventType, ModelInfo, ModelLoc
from .base import InputSourcePlugin

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer)\s+\S+"),
)
_ALLOWED_SUFFIXES = {".log", ".txt", ".json", ".md", ".out"}


def _sanitize_text(value: str, max_chars: int = 6000) -> str:
    text = value or ""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=***", text)
    text = text.strip()
    return text[-max_chars:] if len(text) > max_chars else text


def _safe_name(value: str) -> str:
    name = Path(value).name
    name = _SAFE_FILENAME.sub("-", name).strip("-.")
    if not name:
        name = f"external-{int(datetime.now(timezone.utc).timestamp())}.log"
    if Path(name).suffix.lower() not in _ALLOWED_SUFFIXES:
        name += ".log"
    return name[:200]


class FileInputSourcePlugin(InputSourcePlugin):
    plugin_id = "file_input"
    display_name = "外部日志文件输入源"
    description = "监控外部运行日志/错误日志文件,新增文件时自动触发 IQE Agent"
    plugin_type = "input_source"
    enabled_by_default = True
    capabilities = {
        "polling": True,
        "webhook": False,
        "upload": True,
        "description": "读取本地目录中的 .log/.txt/.json 文件;文件名与修改时间用于去重。",
    }
    config_schema = {
        "watch_dir": {
            "type": "string",
            "label": "监控目录",
            "default": str(DATA_DIR / "input_files"),
            "required": False,
            "max_length": 500,
            "description": "外部 log/txt/json 文件所在目录;平台只读取,不修改文件内容。",
        },
        "log_type": {
            "type": "string",
            "label": "日志类型",
            "default": "error_log",
            "required": False,
            "enum": ["run_log", "error_log"],
            "description": "仅用于事件标题与摘要标签,不影响解析。",
        },
        "poll_interval_seconds": {
            "type": "number",
            "label": "轮询间隔(秒)",
            "default": 15,
            "min": 5,
            "max": 3600,
            "required": False,
        },
        "max_events_per_poll": {
            "type": "integer",
            "label": "单次最多触发数",
            "default": 3,
            "min": 1,
            "max": 10,
            "required": False,
        },
        "max_log_chars": {
            "type": "integer",
            "label": "日志摘要最大字符数",
            "default": 6000,
            "min": 200,
            "max": 20000,
            "required": False,
        },
    }

    @property
    def _directory(self) -> Path:
        raw = str(self.config.get("watch_dir") or (DATA_DIR / "input_files"))
        return Path(raw).expanduser()

    def _ensure_directory(self) -> Path:
        directory = self._directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(f"无法创建日志目录: {exc.__class__.__name__}") from exc
        return directory

    async def health(self) -> tuple[bool, str]:
        try:
            directory = self._ensure_directory()
        except ConfigurationError as exc:
            return False, exc.message
        count = len([item for item in directory.iterdir() if item.is_file()])
        return True, f"日志目录可访问,{count} 个文件"

    # ------------------------------------------------------------------ upload

    def save_upload(self, filename: str, content: str) -> Path:
        directory = self._ensure_directory()
        target = directory / _safe_name(filename)
        # 只写文本,统一 UTF-8;不执行、不解析文件内容。
        target.write_text(content, encoding="utf-8")
        return target

    # ----------------------------------------------------------------- collect

    async def collect_alerts(
        self, limit: int | None = None, lookback_minutes: int | None = None
    ) -> list[EventEnvelope]:
        directory = self._ensure_directory()
        max_events = min(int(limit or self.config.get("max_events_per_poll", 3)), 10)
        max_chars = int(self.config.get("max_log_chars", 6000))
        candidates: list[Path] = []
        for item in directory.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in _ALLOWED_SUFFIXES:
                continue
            try:
                if item.stat().st_size > 5 * 1024 * 1024:
                    continue
            except OSError:
                continue
            candidates.append(item)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

        events: list[EventEnvelope] = []
        for path in candidates:
            if len(events) >= max_events:
                break
            try:
                stat = path.stat()
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            event_key = f"{path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
            if not db.mark_source_event_seen(self.plugin_id, event_key):
                continue
            events.append(self._build_event(path, stat, content, max_chars))
        return events

    def _build_event(
        self, path: Path, stat: Any, content: str, max_chars: int
    ) -> EventEnvelope:
        log_type = str(self.config.get("log_type", "error_log"))
        timestamp = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        case_id = f"FILE-{path.stem}-{int(stat.st_mtime)}"[:100]
        artifact_url = f"file://{path.resolve()}"
        title = f"{path.name} ({log_type})"[:120]
        payload = {
            "case_id": case_id,
            "title": title,
            "job_name": path.name,
            "build_number": int(stat.st_mtime),
            "repository": str(path.parent),
            "branch": "",
            "commit": "",
            "stage": log_type,
            "log_excerpt": _sanitize_text(content, max_chars),
            "artifact_url": artifact_url,
            "file_name": path.name,
            "file_path": str(path.resolve()),
            "log_type": log_type,
            "file_size": stat.st_size,
            "file_modified_at": timestamp.isoformat().replace("+00:00", "Z"),
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
                model_name="file-input",
                latency_ms=0,
                cost_token=0,
            ),
            payload=payload,
        )
