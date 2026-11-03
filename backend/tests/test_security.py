"""插件配置校验与密钥脱敏测试。"""

from __future__ import annotations

import pytest

from app.errors import ConfigurationError
from app.security import mask_config, validate_plugin_config

SCHEMA = {
    "api_url": {"type": "string", "required": False, "default": ""},
    "api_key": {"type": "string", "required": False, "default": "", "secret": True},
    "timeout_seconds": {"type": "number", "required": False, "default": 10, "min": 1, "max": 60},
}


def test_defaults_are_applied():
    assert validate_plugin_config(SCHEMA, {}) == {
        "api_url": "",
        "api_key": "",
        "timeout_seconds": 10,
    }


def test_unknown_field_is_rejected():
    with pytest.raises(ConfigurationError):
        validate_plugin_config(SCHEMA, {"unknown": "x"})


def test_wrong_type_is_rejected():
    with pytest.raises(ConfigurationError):
        validate_plugin_config(SCHEMA, {"timeout_seconds": "10"})
    with pytest.raises(ConfigurationError):
        validate_plugin_config(SCHEMA, {"timeout_seconds": True})


def test_range_is_enforced():
    with pytest.raises(ConfigurationError):
        validate_plugin_config(SCHEMA, {"timeout_seconds": 0})


def test_secret_is_masked():
    masked = mask_config(SCHEMA, {"api_url": "http://x", "api_key": "super-secret"})
    assert masked["api_key"] == "***"
    assert masked["api_url"] == "http://x"


def test_url_pattern_is_enforced():
    schema = {
        "api_url": {
            "type": "string",
            "default": "",
            "pattern": r"(^$|^https?://[^\s]+$)",
        }
    }
    assert validate_plugin_config(schema, {"api_url": ""})["api_url"] == ""
    assert (
        validate_plugin_config(schema, {"api_url": "http://127.0.0.1:18080"})["api_url"]
        == "http://127.0.0.1:18080"
    )
    with pytest.raises(ConfigurationError):
        validate_plugin_config(schema, {"api_url": "ftp://example.com"})
