"""SQLite 存储插件。

文档第 2 节存储插件;文档未定义存储接口与表结构【已确认 Q15/Q17】。
本插件负责初始化/检查 SQLite,平台服务通过 app.db 的参数化 SQL 访问数据。
"""

from __future__ import annotations

from typing import Any

from .. import db
from .base import StoragePlugin


class SQLiteStoragePlugin(StoragePlugin):
    plugin_id = "sqlite_storage"
    display_name = "SQLite Storage"
    description = "Demo 持久化插件,生产可替换 PostgreSQL + S3(文档 2 节)"
    config_schema = {}

    def load(self) -> None:
        db.init_db()
        super().load()

    async def health(self) -> tuple[bool, str]:
        try:
            db.list_pipelines()
            return True, "SQLite ready"
        except Exception as exc:  # noqa: BLE001 - health 必须捕获所有异常
            return False, f"SQLite 不可用: {exc.__class__.__name__}"

    def info(self) -> dict[str, Any]:
        return {"pipelines": len(db.list_pipelines())}
