"""IQE Agent 公共基类。

文档附录 A:Agent 通过依赖注入获得 llm_provider / knowledge_base,返回标准事件信封。
文档 7.2:LLM 不可用时降级到 Mock LLM;输出 Schema 校验失败进入死信队列。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, ClassVar
from uuid import uuid4

from ...errors import LLMUnavailableError, SchemaValidationFailure
from ...models.event import EventEnvelope, EventStatus, ModelInfo, validate_event
from ..base import AgentPlugin
from .prompts import AGENT_PROMPTS, PROMPT_VERSION


class IQEAgent(AgentPlugin):
    config_schema: dict[str, dict[str, Any]] = {}
    # 【已确认 Q2】payload v0 的必填字段;字段名见产品设计说明,
    # 未列出的扩展字段仍允许存在,避免把未确认的外部输出直接拒绝。
    payload_required_fields: ClassVar[tuple[str, ...]] = ()
    default_system_prompt: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """为每个 Agent 自动注入可配置的 system_prompt 字段。"""

        super().__init_subclass__(**kwargs)
        default_prompt = AGENT_PROMPTS.get(cls.plugin_id) or (
            f"You are the IQE Agent '{cls.plugin_id}'. "
            "Return a strict JSON object only."
        )
        cls.default_system_prompt = default_prompt
        schema = dict(getattr(cls, "config_schema", {}) or {})
        schema.setdefault(
            "system_prompt",
            {
                "type": "string",
                "label": "System Prompt",
                "default": default_prompt,
                "required": False,
                "min_length": 1,
                "max_length": 12000,
                "multiline": True,
                "description": "插件级默认 Prompt;流水线阶段可覆盖,留空使用内置默认值。",
            },
        )
        cls.config_schema = schema

    def __init__(
        self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None
    ) -> None:
        super().__init__(config, dependencies)
        configured = str(self.config.get("system_prompt") or "").strip()
        self.system_prompt = configured or self.default_system_prompt
        source = str(self.dependencies.get("prompt_source", "plugin"))
        if source == "plugin" and (
            not configured or configured == self.default_system_prompt
        ):
            source = "default"
        self.prompt_source = source

    def _prompt_meta(self) -> dict[str, str]:
        prompt = self.system_prompt or self.default_system_prompt
        return {
            "version": PROMPT_VERSION,
            "source": self.prompt_source,
            "hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
        }

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        missing = [
            field
            for field in self.payload_required_fields
            if field not in payload
            or payload[field] is None
            or (isinstance(payload[field], str) and not payload[field].strip())
        ]
        if missing:
            raise SchemaValidationFailure(
                f"{self.plugin_id} 输出缺少必填 payload 字段: {', '.join(missing)}"
            )

    def ensure_input(self, input_event: EventEnvelope | dict[str, Any]) -> EventEnvelope:
        event = (
            input_event
            if isinstance(input_event, EventEnvelope)
            else validate_event(dict(input_event))
        )
        if event.event_type.value not in self.input_event_types:
            raise SchemaValidationFailure(
                f"{self.plugin_id} 不接受事件类型 {event.event_type.value}"
            )
        return event

    async def call_llm(
        self, task: str, context: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        llm = self.dependencies.get("llm_provider")
        mock = self.dependencies.get("mock_llm")
        if llm is None:
            llm = mock
        if llm is None:
            raise LLMUnavailableError("未注入 LLM 提供商")

        # 插件/阶段配置的 system_prompt 是唯一系统指令来源;task 与 context
        # 仍通过 user 消息传入,便于 Trace 与 Mock 规则复用。
        system_prompt = self.system_prompt or self.default_system_prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        fallback_reason: str | None = None
        try:
            result = await llm.chat_completion(messages, {"task": task, "context": context})
        except LLMUnavailableError as exc:
            # 文档 7.4:LLM 不可用或超时 → 降级到 Mock LLM
            if mock is None or mock is llm:
                raise
            result = await mock.chat_completion(messages, {"task": task, "context": context})
            fallback_reason = f"{getattr(llm, 'plugin_id', 'llm')} 降级: {exc.message}"

        if not isinstance(result, dict) or not isinstance(result.get("content"), dict):
            raise SchemaValidationFailure("LLM 响应缺少 content 对象")
        try:
            ModelInfo(
                model_loc=result["model_loc"],
                model_name=result["model_name"],
                latency_ms=int(result["latency_ms"]),
                cost_token=int(result["cost_token"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SchemaValidationFailure("LLM 响应的 model_info 不合法") from exc
        result["prompt_meta"] = self._prompt_meta()
        return result, fallback_reason

    def build_event(
        self,
        input_event: EventEnvelope,
        *,
        confidence: float,
        status: EventStatus,
        payload: dict[str, Any],
        model_result: dict[str, Any],
        evidence_links: list[str] | None = None,
        fallback_reason: str | None = None,
    ) -> EventEnvelope:
        safe_payload = dict(payload)
        prompt_meta = model_result.get("prompt_meta")
        if isinstance(prompt_meta, dict):
            # Prompt 审计字段放在 payload 顶层,不改变文档 3.1 事件信封。
            safe_payload.setdefault("prompt_version", prompt_meta.get("version"))
            safe_payload.setdefault("prompt_source", prompt_meta.get("source"))
            safe_payload.setdefault("prompt_hash", prompt_meta.get("hash"))
        if fallback_reason:
            # 【已确认 Q10】降级原因放入 payload,便于 Trace 页面展示。
            safe_payload["llm_fallback_reason"] = fallback_reason
        self._validate_payload(safe_payload)
        data = {
            "event_id": str(uuid4()),
            "event_type": self.output_event_type,
            "source_agent": self.plugin_id,
            "timestamp": datetime.now(timezone.utc),
            "trace_id": input_event.trace_id,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "evidence_links": evidence_links or list(input_event.evidence_links),
            "status": status,
            "model_info": {
                "model_loc": model_result["model_loc"],
                "model_name": model_result["model_name"],
                "latency_ms": int(model_result["latency_ms"]),
                "cost_token": int(model_result["cost_token"]),
            },
            "payload": safe_payload,
        }
        return validate_event(data)


def require_str(content: dict[str, Any], field: str) -> str:
    value = content.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationFailure(f"LLM 输出缺少字符串字段 {field}")
    return value


def require_number(content: dict[str, Any], field: str) -> float:
    value = content.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaValidationFailure(f"LLM 输出缺少数字字段 {field}")
    return float(value)
