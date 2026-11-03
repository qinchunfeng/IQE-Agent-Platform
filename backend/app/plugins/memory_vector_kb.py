"""内存向量知识库插件。

文档 7.4:无真实 Milvus 时使用内存向量库。
文档未定义相似度算法/阈值/TopK/入库内容【已确认 Q7】;临时基线:
- 分词 + 词频余弦相似度
- 默认阈值 0.35,TopK 3(可通过插件配置调整)
- 条目持久化到 SQLite,启动时重建内存索引
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .. import db
from ..config import KB_SIMILARITY_THRESHOLD, KB_TOP_K
from .base import KnowledgeBasePlugin

_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "at",
    "in",
    "on",
    "to",
    "of",
    "for",
    "with",
    "during",
    "after",
    "before",
    "is",
    "was",
    "were",
    "be",
    "by",
    "from",
    "this",
    "that",
    "it",
    "as",
    "while",
}


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in (match.group(0).lower() for match in _TOKEN_RE.finditer(text))
        if token not in _STOPWORDS
    ]


def _coverage(query: str, document: str) -> float:
    """查询词覆盖率:短查询(如 UI 搜索)在长日志上余弦会被稀释。"""

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0
    document_tokens = set(_tokenize(document))
    return len(query_tokens & document_tokens) / len(query_tokens)


def _cosine(left: str, right: str) -> float:
    left_counter = Counter(_tokenize(left))
    right_counter = Counter(_tokenize(right))
    if not left_counter or not right_counter:
        return 0.0
    common = set(left_counter) & set(right_counter)
    numerator = sum(left_counter[token] * right_counter[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left_counter.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counter.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class MemoryVectorKBPlugin(KnowledgeBasePlugin):
    plugin_id = "memory_vector_kb"
    display_name = "内存向量知识库"
    description = "Demo 知识库,词频余弦相似度;生产可替换 Milvus/PGVector(文档 7.4)"
    config_schema = {
        "similarity_threshold": {
            "type": "number",
            "label": "相似度阈值",
            "default": KB_SIMILARITY_THRESHOLD,
            "min": 0,
            "max": 1,
            "required": False,
        },
        "top_k": {
            "type": "integer",
            "label": "TopK",
            "default": KB_TOP_K,
            "min": 1,
            "max": 10,
            "required": False,
        },
    }

    def __init__(self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None):
        super().__init__(config, dependencies)
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        with self._lock:
            self._entries = {row["entry_id"]: dict(row) for row in db.list_knowledge(limit=1000)}
        super().load()

    async def health(self) -> tuple[bool, str]:
        with self._lock:
            return True, f"内存向量库 ready,{len(self._entries)} 条知识"

    def add(
        self,
        *,
        title: str,
        content: str,
        category: str,
        summary: str | None = None,
        root_cause: str | None = None,
        source_trace_id: str | None = None,
    ) -> dict[str, Any]:
        # 【已确认 Q6】结构化保存日志摘要、Triage 结论与分类;
        # 检索仍只使用 title/content,避免结论文本稀释相似度。
        entry = {
            "entry_id": str(uuid4()),
            "title": title,
            "content": content,
            "category": category,
            "summary": summary or "",
            "root_cause": root_cause or "",
            "source_trace_id": source_trace_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        db.save_knowledge(entry)
        with self._lock:
            self._entries[entry["entry_id"]] = entry
        return entry

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        limit = int(top_k or self.config.get("top_k", KB_TOP_K))
        threshold = float(self.config.get("similarity_threshold", KB_SIMILARITY_THRESHOLD))
        with self._lock:
            entries = list(self._entries.values())
        scored: list[dict[str, Any]] = []
        for entry in entries:
            # 【已确认 Q7】标题常含中文/分类,可能与英文日志稀释相似度;
            # 取标题余弦、正文余弦、正文查询词覆盖率三者最大值。
            # 0.8 系数用于压制“仅命中少量通用词”的误召回。
            score = max(
                _cosine(query, entry["title"]),
                _cosine(query, entry["content"]),
                0.8 * _coverage(query, entry["content"]),
            )
            if score >= threshold:
                scored.append({**entry, "score": round(score, 4)})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def list_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                (dict(entry) for entry in self._entries.values()),
                key=lambda item: item["created_at"],
                reverse=True,
            )
