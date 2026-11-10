"""Mock LLM 提供商插件。

文档 7.4:Qoder CN 不可用或超时 → 降级到 Mock LLM。
文档未定义 Mock 的提示词/输出结构【已确认 Q2】,这里用确定性规则保证演示可重复。
文档 6 场景 3/5 的耗时与置信度作为可配置模拟指标【已确认 Q12】。
"""

from __future__ import annotations

import json
from typing import Any

from ..config import MOCK_LATENCY_MS
from .base import LLMProviderPlugin

_AMBIGUOUS_MARKERS = ("unable to confirm", "ambiguous", "unknown root cause", "root cause unclear")
_DRIVER_MARKERS = ("gpu driver", "driver crash", "device initialization")
_FLAKY_MARKERS = (
    "flaky",
    "passed on rerun",
    "passed after retry",
    "inconsistent test result",
    "intermittent",
    "not reproducible",
    "timing jitter",
)
_ENVIRONMENT_MARKERS = (
    "no space left",
    "oomkilled",
    "out of memory",
    "dns resolution",
    "address already in use",
    "missing environment variable",
    "docker daemon",
    "quota exceeded",
    "disk quota",
)
_PRODUCT_MARKERS = (
    "assertionerror",
    "assert",
    "nullpointer",
    "null pointer",
    "schema mismatch",
    "deadlock",
    "data corruption",
    "regression",
    "contract test",
    "missing required field",
    "security scan",
    "cve-",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _clamp_confidence(value: Any, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


class MockLLMPlugin(LLMProviderPlugin):
    plugin_id = "mock_llm"
    display_name = "Mock LLM"
    description = "本地确定性 LLM,用于 Qoder CN 不可用时的降级演示(文档 7.4)"
    config_schema = {
        "model_name": {
            "type": "string",
            "label": "模型名",
            "default": "mock-llm-v1",
            "required": False,
        },
        # 【已确认 Q12】是否使用文档场景的模拟业务耗时
        "simulate_business_latency": {
            "type": "boolean",
            "label": "模拟业务耗时",
            "default": True,
            "required": False,
        },
    }

    async def health(self) -> tuple[bool, str]:
        return True, "Mock LLM ready"

    def _latency(self, key: str) -> int:
        if not self.config.get("simulate_business_latency", True):
            return 0
        return int(MOCK_LATENCY_MS.get(key, 0))

    def _triage(self, context: dict[str, Any]) -> dict[str, Any]:
        log = str(context.get("log_excerpt", ""))
        lower = log.lower()
        kb_hits = context.get("kb_hits") or []

        if _contains_any(lower, _AMBIGUOUS_MARKERS):
            return {
                "category": "unknown",
                "root_cause": "日志证据不足以确认根因",
                "confidence": 0.6,
                "confidence_reason": "日志同时出现环境与产品信号,无法确认根因",
                "kb_hit": False,
                "kb_entry_id": None,
                "log_summary": log,
                "latency_key": "triage_no_kb",
            }

        if kb_hits:
            top = max(kb_hits, key=lambda item: float(item.get("score", 0)))
            return {
                "category": top.get("category", "unknown"),
                "root_cause": f"命中历史案例 #{top.get('entry_id')}",
                "confidence": 0.92,
                "confidence_reason": "知识库命中相似历史案例",
                "kb_hit": True,
                "kb_entry_id": top.get("entry_id"),
                "log_summary": log,
                "latency_key": "triage_kb_hit",
            }

        if _contains_any(lower, _DRIVER_MARKERS):
            category, confidence = "driver_compatibility", 0.75
        elif _contains_any(lower, _FLAKY_MARKERS):
            category, confidence = "flaky", 0.82
        elif _contains_any(lower, _ENVIRONMENT_MARKERS):
            category, confidence = "environment", 0.8
        elif _contains_any(lower, _PRODUCT_MARKERS):
            category, confidence = "product_bug", 0.86
        else:
            category, confidence = "unknown", 0.7

        return {
            "category": category,
            "root_cause": f"基于日志关键词判定为 {category}",
            "confidence": confidence,
            "confidence_reason": "关键词与规则匹配",
            "kb_hit": False,
            "kb_entry_id": None,
            "log_summary": log,
            "latency_key": "triage_no_kb",
        }

    def _reproduction(self, context: dict[str, Any]) -> dict[str, Any]:
        category = context.get("category", "unknown")
        reproduced = category not in {"environment", "flaky"}
        return {
            "reproduced": reproduced,
            "attempts": 1 if reproduced else 3,
            "summary": "在隔离环境重跑复现成功" if reproduced else f"{category} 类失败未能稳定复现",
            "confidence": 0.9 if reproduced else 0.55,
            "latency_key": "reproduction",
        }

    def _ticket(self, context: dict[str, Any]) -> dict[str, Any]:
        category = context.get("category", "unknown")
        priority_map = {
            "driver_compatibility": "P1",
            "product_bug": "P1",
            "unknown": "P2",
            "flaky": "P3",
            "environment": "P3",
        }
        title = context.get("case_title") or context.get("case_id") or "CI failure"
        return {
            "title": f"[IQE] {title}",
            "description": (
                f"CI 失败自动分诊结果: {category}\n"
                f"根因: {context.get('root_cause', '')}\n"
                f"日志摘要: {context.get('log_excerpt', '')}"
            ),
            "priority": priority_map.get(category, "P2"),
            "category": category,
            "latency_key": "ticket",
        }

    def _review(self, context: dict[str, Any]) -> dict[str, Any]:
        decision = "pass" if float(context.get("confidence", 0)) >= float(
            context.get("threshold", 0.7)
        ) else "handover_human"
        return {
            "decision": decision,
            "summary": (
                "置信度达到阈值,建议自动通过"
                if decision == "pass"
                else "置信度低于阈值,转人工复核"
            ),
            "latency_key": "review",
        }

    def _report(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": (
                f"流水线完成,TAT {context.get('tat_seconds', 0)} 秒,"
                f"工单 {context.get('ticket_key') or '未创建'}"
            ),
            "latency_key": "report",
        }

    def _monitor(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": "CI 失败事件已归一化",
            "noise": False,
            "confidence": 0.99,
            "latency_key": "monitor",
        }

    async def chat_completion(
        self, messages: list[dict[str, str]], config: dict[str, Any]
    ) -> dict[str, Any]:
        task = str(config.get("task", ""))
        context = dict(config.get("context") or {})
        if not context:
            # 允许调用方把上下文放在最后一条 user 消息里
            for message in reversed(messages):
                if message.get("role") == "user":
                    try:
                        parsed = json.loads(message.get("content", "{}"))
                        if isinstance(parsed, dict):
                            context = parsed
                    except json.JSONDecodeError:
                        context = {"log_excerpt": message.get("content", "")}
                    break

        handlers = {
            "monitor": self._monitor,
            "triage": self._triage,
            "reproduction": self._reproduction,
            "ticket": self._ticket,
            "review": self._review,
            "report": self._report,
        }
        handler = handlers.get(task)
        content = handler(context) if handler else {"summary": "mock response"}
        latency_key = str(content.pop("latency_key", ""))
        latency_ms = self._latency(latency_key)

        prompt_size = sum(len(message.get("content", "")) for message in messages)
        prompt_size += len(json.dumps(context, ensure_ascii=False))
        return {
            "content": content,
            "model_loc": "mock",
            "model_name": self.config.get("model_name", "mock-llm-v1"),
            "latency_ms": latency_ms,
            "cost_token": max(0, prompt_size // 4),
            "simulated_latency": bool(latency_ms),
        }
