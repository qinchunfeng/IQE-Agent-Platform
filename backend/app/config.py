"""全局配置。

端口取值依据文档 0.4「本机端口约定」(v2.2):
- 前端 3200、后端 8000、Airflow 18080。
文档未定义的运行参数统一在 docs/待确认问题清单.md 中登记,已确认基线见 F 节。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("IQE_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("IQE_DB_PATH", str(DATA_DIR / "iqe_demo.db")))

# 文档 0.4:后端 API 8000
APP_HOST = os.getenv("IQE_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("IQE_PORT", "8000"))

# 文档 0.4:前端 3200
FRONTEND_ORIGINS = [
    "http://localhost:3200",
    "http://127.0.0.1:3200",
]

# 文档 7.2:置信度低于阈值(默认 0.7)自动流转人工节点
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

APP_NAME = "IQE-Agent Platform"
APP_VERSION = "0.1.0-demo"

# 【已确认 Q10】插件健康检查 2 秒,外部调用超时由插件配置决定(默认 10 秒)。
HEALTH_CHECK_TIMEOUT_SECONDS = 2.0
DEFAULT_EXTERNAL_TIMEOUT_SECONDS = 10.0

# 【已确认 Q7】知识库相似度算法/阈值/TopK 的 Demo 基线。
KB_SIMILARITY_THRESHOLD = 0.35
KB_TOP_K = 3

# 【已确认 Q16】Agent 单次执行超时;超时后失败 Run 并写入死信。
AGENT_TIMEOUT_SECONDS = max(1.0, float(os.getenv("IQE_AGENT_TIMEOUT_SECONDS", "120")))

# 【已确认 Q21】内置编排器最大并发 Run 数。
MAX_CONCURRENT_RUNS = max(1, int(os.getenv("IQE_MAX_CONCURRENT_RUNS", "8")))

# 【已确认 Q13】可选 Bearer Token;为空表示本机 Demo 不鉴权。
API_TOKEN = os.getenv("IQE_API_TOKEN", "").strip()

# 【已确认 Q19】“今日”统计时区;为空时使用服务端本地时区。
TIMEZONE = os.getenv("IQE_TIMEZONE", "").strip()


def local_now() -> datetime:
    """返回统计口径使用的当前时间。"""

    if TIMEZONE:
        try:
            return datetime.now(ZoneInfo(TIMEZONE))
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone()


def local_timezone_name() -> str:
    """返回可读的统计时区名称;本机时区用 UTC 偏移表示,避免 CST 等歧义缩写。"""

    if TIMEZONE:
        try:
            ZoneInfo(TIMEZONE)
            return TIMEZONE
        except ZoneInfoNotFoundError:
            pass
    now = local_now()
    offset = now.utcoffset()
    if offset is None:
        return now.tzname() or ""
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"

# 文档 6 场景 5 的管理层对比基线。UI 必须标注“文档基线/模拟指标”。
# 数值逐字来自文档场景 5 与场景 1,不得改写。
DOC_BASELINES = {
    "cloud": {
        "name": "Qoder CN Cloud",
        "model_loc": "cloud_qoder_cn",
        "tat_minutes": 8,
        "cost_per_ticket": 2.5,
        "confidence": 0.88,
        "source": "文档 6 场景 5",
    },
    "local": {
        "name": "Mock Local(模拟 Strix Halo)",
        "model_loc": "local_strix_halo",
        "tat_minutes": 12,
        "cost_per_ticket": 0.3,
        "confidence": 0.85,
        "source": "文档 6 场景 5",
    },
    "human": {
        "name": "人工处理基线",
        "tat_minutes": 45,
        "source": "文档 6 场景 1",
    },
}

# 【已确认 Q12】Mock 环境的“业务耗时”按文档场景 3 做可配置模拟,
# 以便复现 3 分钟 → 30 秒、整链约 8 分钟的业务叙事;
# Trace 同时保留真实墙钟时间,UI 标注“模拟耗时”。
MOCK_LATENCY_MS = {
    # 30s + 180s + 120s + 60s + 30s + 30s = 450s;再加 30s 归一化使整链约 8 分钟,
    # 与文档场景 1/5 的 8 分钟基线一致。
    "monitor": 60_000,
    "triage_no_kb": 180_000,
    "triage_kb_hit": 30_000,
    "reproduction": 120_000,
    "ticket": 60_000,
    "review": 30_000,
    "report": 30_000,
}
