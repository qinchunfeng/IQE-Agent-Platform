"""领域异常。

文档没有定义错误码体系【已确认 Q1】。因此这里不发明业务错误码,
统一由 HTTP 状态码 + {"detail": str} 表达(FastAPI 默认结构)。
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400
    default_message = "请求无法处理"

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(DomainError):
    status_code = 404
    default_message = "资源不存在"


class ConflictError(DomainError):
    status_code = 409
    default_message = "当前状态不允许该操作"


class ConfigurationError(DomainError):
    status_code = 422
    default_message = "插件配置不合法"


class PluginUnavailableError(DomainError):
    status_code = 503
    default_message = "插件不可用"


class SchemaValidationFailure(DomainError):
    status_code = 422
    default_message = "事件不符合标准信封"


class LLMUnavailableError(DomainError):
    status_code = 503
    default_message = "LLM 服务不可用"


class ToolExecutionError(DomainError):
    status_code = 502
    default_message = "工具执行失败"


class NotificationError(DomainError):
    status_code = 502
    default_message = "通知发送失败"

    def __init__(
        self,
        message: str | None = None,
        *,
        retryable: bool = True,
        details: Any = None,
    ) -> None:
        self.retryable = retryable
        super().__init__(message, details=details)
