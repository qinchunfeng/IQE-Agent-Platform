"""飞书通知工具插件。

平台在 Run 进入终态(或等待人工)后调用本插件发送汇总卡片。
文档未定义通知渠道【Q25 已确认】,这里同时支持两种飞书接入方式:

- webhook:自定义机器人 Webhook,只能发到该机器人所在群;
- app:企业自建应用 tenant_access_token,可按 chat_id/open_id/email/user_id
  发到群或个人,需要 ``im:message:send_as_bot`` 权限。

Webhook URL 与应用密钥均按 secret 字段保存/脱敏,错误信息只包含 HTTP 状态码
与飞书业务 code,不输出 URL、token 或 app_secret。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from ..errors import NotificationError
from .base import ToolPlugin

STATUS_LABELS = {
    "completed": "已完成",
    "rejected": "已驳回",
    "failed": "失败",
    "stopped": "已停止",
    "waiting_human": "等待人工",
}
STATUS_TEMPLATES = {
    "completed": "green",
    "rejected": "orange",
    "failed": "red",
    "stopped": "grey",
    "waiting_human": "orange",
}
STAGE_STATUS_LABELS = {
    "passed": "通过",
    "rejected": "驳回",
    "handover_human": "转人工",
    "need_more_info": "待补充",
    "running": "执行中",
    "pending": "未执行",
    "failed": "失败",
}
TAT_SOURCE_LABELS = {
    "measured": "实测",
    "simulated_mock": "模拟业务耗时",
    "mixed": "混合",
}
# 飞书 token 失效类错误允许重试,其余业务错误直接失败,避免无效重放。
_RETRYABLE_FEISHU_CODES = {99991661, 99991663, 99991668}


class FeishuNotifierPlugin(ToolPlugin):
    plugin_id = "feishu_notifier"
    display_name = "飞书通知"
    description = "流水线结束后向飞书群或个人发送汇总卡片(Webhook / 自建应用)"
    enabled_by_default = False
    capabilities = {
        "notification": True,
        "modes": ["webhook", "app"],
        "secret_masked": True,
    }
    config_schema = {
        "mode": {
            "type": "string",
            "label": "发送方式",
            "enum": ["webhook", "app"],
            "default": "webhook",
            "required": False,
            "description": "webhook=群自定义机器人;app=自建应用,可发群或个人",
        },
        "webhook_url": {
            "type": "string",
            "label": "Webhook URL",
            "default": "",
            "required": False,
            "secret": True,
            "pattern": r"(^$|^https?://[^\s]+$)",
            "description": "含 token,仅保存在后端,响应与日志中脱敏",
        },
        "app_id": {
            "type": "string",
            "label": "App ID",
            "default": "",
            "required": False,
        },
        "app_secret": {
            "type": "string",
            "label": "App Secret",
            "default": "",
            "required": False,
            "secret": True,
        },
        "api_base": {
            "type": "string",
            "label": "飞书 API 地址",
            "default": "https://open.feishu.cn",
            "required": False,
            "pattern": r"^https?://[^\s]+$",
        },
        "receive_id_type": {
            "type": "string",
            "label": "接收者 ID 类型",
            "enum": ["chat_id", "open_id", "email", "user_id"],
            "default": "chat_id",
            "required": False,
            "description": "应用模式必填;群用 chat_id,个人可用 open_id/email/user_id",
        },
        "receive_id": {
            "type": "string",
            "label": "接收者 ID",
            "default": "",
            "required": False,
            "description": "应用模式必填;对应上面的 ID 类型",
        },
        "notify_on_completed": {
            "type": "boolean",
            "label": "完成时通知",
            "default": True,
            "required": False,
        },
        "notify_on_rejected": {
            "type": "boolean",
            "label": "驳回时通知",
            "default": True,
            "required": False,
        },
        "notify_on_failed": {
            "type": "boolean",
            "label": "失败时通知",
            "default": True,
            "required": False,
        },
        "notify_on_waiting_human": {
            "type": "boolean",
            "label": "待人工时通知",
            "default": False,
            "required": False,
            "description": "等待人工不是终态,默认关闭,避免与最终结果重复",
        },
        "notify_on_stopped": {
            "type": "boolean",
            "label": "停止时通知",
            "default": False,
            "required": False,
        },
        "title_prefix": {
            "type": "string",
            "label": "卡片标题前缀",
            "default": "【IQE 流水线】",
            "required": False,
            "max_length": 40,
        },
        "dashboard_url": {
            "type": "string",
            "label": "平台前端地址",
            "default": "http://127.0.0.1:3200",
            "required": False,
            "pattern": r"(^$|^https?://[^\s]+$)",
            "description": "用于卡片里的“查看 Trace”按钮",
        },
        "timeout_seconds": {
            "type": "number",
            "label": "调用超时(秒)",
            "default": 10,
            "min": 1,
            "max": 60,
            "required": False,
        },
        "max_retries": {
            "type": "integer",
            "label": "失败重试次数",
            "default": 2,
            "min": 0,
            "max": 5,
            "required": False,
        },
        "retry_delay_seconds": {
            "type": "number",
            "label": "重试间隔(秒)",
            "default": 1,
            "min": 0,
            "max": 30,
            "required": False,
        },
    }

    def _mode(self) -> str:
        return str(self.config.get("mode") or "webhook")

    def enabled_for_status(self, status: str) -> bool:
        return bool(self.config.get(f"notify_on_{status}", False))

    def is_configured(self) -> tuple[bool, str]:
        if self._mode() == "webhook":
            if not str(self.config.get("webhook_url") or "").strip():
                return False, "未配置 Webhook URL"
            return True, "Webhook 模式已配置(健康检查不发送测试消息)"
        if not str(self.config.get("app_id") or "").strip():
            return False, "未配置 App ID"
        if not str(self.config.get("app_secret") or "").strip():
            return False, "未配置 App Secret"
        if not str(self.config.get("receive_id") or "").strip():
            return False, "未配置接收者 ID"
        return True, f"应用模式已配置({self.config.get('receive_id_type')})"

    async def health(self) -> tuple[bool, str]:
        # 飞书没有无副作用的 webhook 探活接口;健康检查只校验配置完整性,
        # 避免插件列表刷新时向真实群聊发送消息。
        return self.is_configured()

    # ------------------------------------------------------------------ card

    def build_card(self, report: dict[str, Any]) -> dict[str, Any]:
        status = str(report.get("status") or "")
        label = STATUS_LABELS.get(status, status or "未知状态")
        case = str(report.get("case_id") or report.get("run_id") or "")
        headline = f"{self.config.get('title_prefix') or ''}{label} · {case or '未命名案例'}"

        confidence = report.get("confidence")
        confidence_text = (
            f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "-"
        )
        tat_seconds = report.get("tat_seconds")
        tat_text = "-"
        if tat_seconds is not None:
            source = TAT_SOURCE_LABELS.get(str(report.get("tat_source") or ""), "未知来源")
            tat_text = f"{int(tat_seconds)} 秒({source})"

        fields = [
            ("状态", f"**{label}**"),
            ("案例", str(report.get("title") or case or "-")),
            ("分类", str(report.get("category") or "-")),
            ("置信度", confidence_text),
            ("工单", str(report.get("ticket_key") or "未创建")),
            ("TAT", tat_text),
            ("输入源", str(report.get("input_source") or "-")),
            ("编排器", str(report.get("orchestrator_used") or "-")),
        ]
        elements: list[dict[str, Any]] = [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**{key}**\n{value}"},
                    }
                    for key, value in fields
                ],
            }
        ]

        reason = report.get("human_reason") or report.get("error_reason") or report.get("reason")
        if reason:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**原因**\n{_truncate(str(reason), 600)}",
                    },
                }
            )

        stages = report.get("stages") or []
        if stages:
            chain = " → ".join(
                f"{item.get('agent')} {STAGE_STATUS_LABELS.get(str(item.get('status')), str(item.get('status') or ''))}"
                for item in stages
            )
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**链路**\n{_truncate(chain, 800)}"},
                }
            )

        trace_url = self._trace_url(report)
        actions: list[dict[str, Any]] = []
        if trace_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看 Trace"},
                    "type": "primary",
                    "url": trace_url,
                }
            )
        if actions:
            elements.append({"tag": "action", "actions": actions})

        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": (
                            f"run_id: {report.get('run_id') or '-'} | "
                            f"trace_id: {report.get('trace_id') or '-'}"
                        ),
                    }
                ],
            }
        )

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": STATUS_TEMPLATES.get(status, "blue"),
                "title": {"tag": "plain_text", "content": _truncate(headline, 120)},
            },
            "elements": elements,
        }

    def _trace_url(self, report: dict[str, Any]) -> str:
        base = str(self.config.get("dashboard_url") or "").rstrip("/")
        trace_id = str(report.get("trace_id") or "")
        if not base or not trace_id:
            return ""
        return f"{base}/traces/{trace_id}"

    # --------------------------------------------------------------- deliver

    async def send_report(self, report: dict[str, Any]) -> dict[str, Any]:
        configured, message = self.is_configured()
        if not configured:
            raise NotificationError(message, retryable=False)

        card = self.build_card(report)
        max_retries = int(self.config.get("max_retries", 2))
        delay = float(self.config.get("retry_delay_seconds", 1))
        last_error: NotificationError | None = None

        for attempt in range(1, max_retries + 2):
            try:
                result = await self._deliver(card)
                return {**result, "attempts": attempt}
            except NotificationError as exc:
                last_error = exc
                if not exc.retryable or attempt > max_retries:
                    break
                if delay > 0:
                    await asyncio.sleep(delay)

        assert last_error is not None
        raise NotificationError(
            f"{last_error.message}(已尝试 {attempt} 次)",
            retryable=last_error.retryable,
            details={"attempts": attempt},
        ) from last_error

    async def _deliver(self, card: dict[str, Any]) -> dict[str, Any]:
        if self._mode() == "webhook":
            return await self._send_webhook(card)
        return await self._send_app(card)

    def _client(self) -> httpx.AsyncClient:
        # 测试可通过 dependencies["http_transport"] 注入 MockTransport,
        # 避免真实网络请求;生产环境不传即使用默认传输。
        return httpx.AsyncClient(
            timeout=float(self.config.get("timeout_seconds", 10)),
            transport=self.dependencies.get("http_transport"),
        )

    async def _send_webhook(self, card: dict[str, Any]) -> dict[str, Any]:
        url = str(self.config.get("webhook_url") or "")
        try:
            async with self._client() as client:
                response = await client.post(
                    url, json={"msg_type": "interactive", "card": card}
                )
        except httpx.TimeoutException as exc:
            raise NotificationError("飞书 Webhook 调用超时", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"飞书 Webhook 不可达: {exc.__class__.__name__}", retryable=True
            ) from exc
        body = _check_response(response, "飞书 Webhook")
        return {
            "mode": "webhook",
            "message_id": (body.get("data") or {}).get("message_id"),
        }

    async def _send_app(self, card: dict[str, Any]) -> dict[str, Any]:
        base = str(self.config.get("api_base") or "https://open.feishu.cn").rstrip("/")
        token = await self._tenant_token(base)
        receive_id_type = str(self.config.get("receive_id_type") or "chat_id")
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{base}/open-apis/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": str(self.config.get("receive_id") or ""),
                        "msg_type": "interactive",
                        "content": json.dumps(card, ensure_ascii=False),
                    },
                )
        except httpx.TimeoutException as exc:
            raise NotificationError("飞书消息接口调用超时", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"飞书消息接口不可达: {exc.__class__.__name__}", retryable=True
            ) from exc
        body = _check_response(response, "飞书消息接口")
        return {
            "mode": "app",
            "message_id": (body.get("data") or {}).get("message_id"),
        }

    async def _tenant_token(self, base: str) -> str:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{base}/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": str(self.config.get("app_id") or ""),
                        "app_secret": str(self.config.get("app_secret") or ""),
                    },
                )
        except httpx.TimeoutException as exc:
            raise NotificationError("飞书 token 接口调用超时", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise NotificationError(
                f"飞书 token 接口不可达: {exc.__class__.__name__}", retryable=True
            ) from exc
        body = _check_response(response, "飞书 token 接口")
        token = str(body.get("tenant_access_token") or "")
        if not token:
            raise NotificationError("飞书 token 响应缺少 tenant_access_token", retryable=False)
        return token


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _check_response(response: httpx.Response, label: str) -> dict[str, Any]:
    """校验飞书 HTTP 与业务 code;错误信息不包含 URL/密钥。"""

    retryable = response.status_code == 429 or response.status_code >= 500
    if response.status_code >= 400:
        raise NotificationError(
            f"{label}返回 HTTP {response.status_code}", retryable=retryable
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise NotificationError(f"{label}响应不是合法 JSON", retryable=False) from exc
    if not isinstance(body, dict):
        raise NotificationError(f"{label}响应结构不符合预期", retryable=False)
    code = body.get("code", body.get("StatusCode", 0))
    if code not in (0, None):
        try:
            retryable = int(code) in _RETRYABLE_FEISHU_CODES
        except (TypeError, ValueError):
            retryable = False
        raise NotificationError(
            f"{label}返回 code={code}",
            retryable=retryable,
        )
    return body
