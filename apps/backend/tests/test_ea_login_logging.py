"""PII redact patcher：确保敏感字段不进日志。

覆盖：

- ``logger.bind(email="...")`` extra 字段被脱敏
- ``logger.debug("remid=xxx sid=yyy access_token=zzz")`` message 字符串被脱敏
- BF1Gateway 的「Set-Cookie: remid=abc; sid=def; ...」串被脱敏
- 不脱敏的普通业务字段（如 ``persona_id``、``page=2``）保持原样
"""

from __future__ import annotations

import logging

import pytest
from app.core.logging import _pii_patcher, setup_logging
from loguru import logger


@pytest.fixture
def captured(monkeypatch):
    """捕获所有 loguru 日志（脱敏后）。

    sink format 显式渲染 ``{extra}``，让 ``logger.bind(...)`` 的字段也出现在断言
    可见的字符串里；否则默认 format 只输出 ``{message}``，extra 字段被 patcher
    脱敏与否都无法验证。
    """
    setup_logging()
    sink: list[str] = []

    def _capture(message):
        sink.append(message)

    handler_id = logger.add(
        _capture,
        level="DEBUG",
        format="{message} | extra={extra}",
    )
    yield sink
    logger.remove(handler_id)


def test_patcher_redacts_extra_email(captured):
    logger.bind(email="user@example.com", task_id="t1").info("hello")
    joined = "".join(captured)
    assert "user@example.com" not in joined
    # task_id 不在敏感集合，应保留
    assert "t1" in joined


def test_patcher_redacts_extra_password(captured):
    logger.bind(password="secret-pw-123").warning("oops")
    joined = "".join(captured)
    assert "secret-pw-123" not in joined


def test_patcher_redacts_remid_sid_in_message(captured):
    logger.info("login: remid=abc123 sid=def456 access_token=xyz789")
    joined = "".join(captured)
    assert "abc123" not in joined
    assert "def456" not in joined
    assert "xyz789" not in joined
    # key 名应当保留以便诊断
    assert "remid=[REDACTED]" in joined
    assert "sid=[REDACTED]" in joined
    assert "access_token=[REDACTED]" in joined


def test_patcher_redacts_set_cookie_header(captured):
    # 模拟 BF1Gateway 现有的 logger.debug(f"...Set-Cookie:{header['Set-Cookie']}")
    logger.debug("Set-Cookie: remid=raw-remid; sid=raw-sid; Path=/")
    joined = "".join(captured)
    assert "raw-remid" not in joined
    assert "raw-sid" not in joined


def test_patcher_keeps_business_fields(captured):
    logger.bind(persona_id=12345, page=2).info("query")
    joined = "".join(captured)
    assert "12345" in joined
    assert "page=2" in joined or "page" in joined


def test_patcher_redacts_authcode_and_gateway_session(captured):
    logger.info("got authcode=token-xyz and gatewaySessionId=session-uuid")
    joined = "".join(captured)
    assert "token-xyz" not in joined
    assert "session-uuid" not in joined


def test_pii_patcher_unit_handles_empty_message():
    """直接调用 patcher 确认空 message 不报错。"""
    record: dict = {"message": "", "extra": {}}
    _pii_patcher(record)
    assert record["message"] == ""


def test_pii_patcher_unit_redacts_known_extra_keys():
    record: dict = {
        "message": "ok",
        "extra": {"email": "a@b.com", "password": "x", "task_id": "ok"},
    }
    _pii_patcher(record)
    assert record["extra"]["email"] == "[REDACTED]"
    assert record["extra"]["password"] == "[REDACTED]"
    assert record["extra"]["task_id"] == "ok"


def test_patcher_does_not_break_standard_logging_bridge(captured):
    """InterceptHandler 把 stdlib logging 转发到 loguru，patcher 也应该作用其上。

    fixture 已经在 setup_logging() 之后挂好捕获 sink；不要在测试体内重复调用
    setup_logging()，否则会 ``logger.remove()`` 掉本测试的 sink。
    """
    stdlib_logger = logging.getLogger("test.bridge")
    stdlib_logger.warning("remid=stdlib-leak sid=other")
    joined = "".join(captured)
    assert "stdlib-leak" not in joined
