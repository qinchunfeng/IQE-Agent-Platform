"""Qoder CN LLM 提供商插件。

文档 3.3 要求实现 chat_completion 与 health;真实 Qoder CN API 细节仍以官方文档为准
【已确认 Q9:Demo 采用 OpenAI 兼容基线】。凭据缺失或不可达时由调用方降级到
Mock LLM(文档 7.4)。响应不是合法 JSON 时按“Schema 校验失败”处理(文档 7.2)。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from ..config import HEALTH_CHECK_TIMEOUT_SECONDS
from ..errors import LLMUnavailableError, SchemaValidationFailure
from .base import LLMProviderPlugin

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_json_object(raw: Any) -> dict[str, Any] | None:
    """兼容真实模型的 ```json 围栏/前后解释文字,只提取第一个 JSON 对象。"""

    if isinstance(raw, dict):
        return raw
    text = _JSON_FENCE.sub("", str(raw or "")).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class QoderCNLLMPlugin(LLMProviderPlugin):
    plugin_id = "qoder_cn"
    display_name = "Qoder CN Cloud"
    description = "Qoder CN 云端 LLM(OpenAI 兼容基线已确认,真实 API 契约待确认)"
    config_schema = {
        "api_url": {
            "type": "string",
            "label": "API URL",
            "default": "",
            "required": False,
            "pattern": r"(^$|^https?://[^\s]+$)",
            "description": "例如 http://127.0.0.1:3000",
        },
        "api_key": {
            "type": "string",
            "label": "API Key",
            "default": "",
            "required": False,
            "secret": True,
        },
        "model": {
            "type": "string",
            "label": "模型名",
            "default": "",
            "required": False,
        },
        # 【已确认 Q10】外部调用超时基线 10 秒。
        "timeout_seconds": {
            "type": "number",
            "label": "调用超时(秒)",
            "default": 10,
            "min": 1,
            "max": 300,
            "required": False,
        },
    }

    def _api_base(self) -> str:
        url = str(self.config.get("api_url", "")).rstrip("/")
        if not url:
            return ""
        if url.endswith("/v1"):
            return url
        return f"{url}/v1"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self.config.get("api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def health(self) -> tuple[bool, str]:
        base = self._api_base()
        if not base:
            return False, "未配置 API URL"
        if not self.config.get("api_key"):
            return False, "未配置 API Key"
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{base}/models", headers=self._headers())
            if response.status_code < 400:
                return True, f"Qoder CN 可访问(HTTP {response.status_code})"
            return False, f"Qoder CN 健康检查失败(HTTP {response.status_code})"
        except httpx.HTTPError as exc:
            return False, f"Qoder CN 不可达: {exc.__class__.__name__}"

    async def chat_completion(
        self, messages: list[dict[str, str]], config: dict[str, Any]
    ) -> dict[str, Any]:
        base = self._api_base()
        if not base:
            raise LLMUnavailableError("未配置 Qoder CN API URL")
        if not self.config.get("api_key"):
            raise LLMUnavailableError("未配置 Qoder CN API Key")

        payload: dict[str, Any] = {
            "model": self.config.get("model") or "qoder-cn",
            "messages": messages,
        }
        timeout = float(self.config.get("timeout_seconds", 10))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base}/chat/completions", headers=self._headers(), json=payload
                )
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("Qoder CN 调用超时") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Qoder CN 调用失败: {exc.__class__.__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise LLMUnavailableError(f"Qoder CN 返回 HTTP {response.status_code}")

        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise SchemaValidationFailure("Qoder CN 响应结构不符合预期") from exc

        content = _extract_json_object(raw_content)
        if content is None:
            raise SchemaValidationFailure("Qoder CN 响应不是合法 JSON 对象")

        usage = body.get("usage") or {}
        cost_token = int(usage.get("total_tokens", 0) or 0)
        return {
            "content": content,
            "model_loc": "cloud_qoder_cn",
            "model_name": str(body.get("model") or self.config.get("model") or "qoder-cn"),
            "latency_ms": latency_ms,
            "cost_token": max(0, cost_token),
            "simulated_latency": False,
        }
