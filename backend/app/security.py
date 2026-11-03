"""插件配置校验与密钥脱敏。

文档 3.1/3.4 要求插件通过 config_schema 配置;文档未定义具体字段【已确认 Q15】。
文档未定义权限/脱敏规范【已确认 Q13】,本模块只在响应与日志层面做最小必要保护:
- 对 schema 中 secret=true 的字段,响应统一返回 "***";
- 配置项严格按 schema 校验,拒绝未声明字段与类型错误。
"""

from __future__ import annotations

import re
from typing import Any

from .errors import ConfigurationError

_SECRET_MASK = "***"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_type(field: str, field_schema: dict[str, Any], value: Any) -> None:
    expected = field_schema.get("type", "string")
    if expected == "string":
        if not isinstance(value, str):
            raise ConfigurationError(f"配置项 {field} 必须是字符串")
        if "min_length" in field_schema and len(value) < int(field_schema["min_length"]):
            raise ConfigurationError(f"配置项 {field} 长度不足")
        if "max_length" in field_schema and len(value) > int(field_schema["max_length"]):
            raise ConfigurationError(f"配置项 {field} 长度超出限制")
        pattern = field_schema.get("pattern")
        if pattern and not re.fullmatch(pattern, value):
            raise ConfigurationError(f"配置项 {field} 格式不合法")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigurationError(f"配置项 {field} 必须是整数")
    elif expected == "number":
        if not _is_number(value):
            raise ConfigurationError(f"配置项 {field} 必须是数字")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ConfigurationError(f"配置项 {field} 必须是布尔值")
    else:
        raise ConfigurationError(f"配置项 {field} 的 schema 类型不受支持")

    if "enum" in field_schema and value not in field_schema["enum"]:
        raise ConfigurationError(f"配置项 {field} 不在允许范围内")
    if expected in ("integer", "number"):
        if "min" in field_schema and value < field_schema["min"]:
            raise ConfigurationError(f"配置项 {field} 小于最小值")
        if "max" in field_schema and value > field_schema["max"]:
            raise ConfigurationError(f"配置项 {field} 大于最大值")


def validate_plugin_config(
    schema: dict[str, dict[str, Any]], config: dict[str, Any] | None
) -> dict[str, Any]:
    """按插件声明的 config_schema 规范化配置。

    未声明字段一律拒绝,避免静默忽略错误配置。
    """

    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ConfigurationError("配置必须是 JSON 对象")

    unknown = set(config) - set(schema)
    if unknown:
        raise ConfigurationError(f"存在未声明配置项: {', '.join(sorted(unknown))}")

    normalized: dict[str, Any] = {}
    for field, field_schema in schema.items():
        required = bool(field_schema.get("required", False))
        if field not in config:
            if "default" in field_schema:
                normalized[field] = field_schema["default"]
            elif required:
                raise ConfigurationError(f"缺少必填配置项 {field}")
            continue
        value = config[field]
        _check_type(field, field_schema, value)
        normalized[field] = value
    return normalized


def config_defaults(schema: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        field: field_schema["default"]
        for field, field_schema in schema.items()
        if "default" in field_schema
    }


def mask_config(
    schema: dict[str, dict[str, Any]], config: dict[str, Any] | None
) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for field, value in (config or {}).items():
        field_schema = schema.get(field, {})
        if field_schema.get("secret") and value not in (None, ""):
            masked[field] = _SECRET_MASK
        else:
            masked[field] = value
    return masked
