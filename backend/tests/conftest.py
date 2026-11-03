"""测试环境:在导入 app 前切换到临时 SQLite。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="iqe-agent-test-")
os.environ["IQE_DATA_DIR"] = _tmp_dir
os.environ["IQE_DB_PATH"] = str(Path(_tmp_dir) / "test.db")
