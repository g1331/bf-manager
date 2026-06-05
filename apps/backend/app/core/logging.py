"""统一日志配置：基于 loguru，含全局 PII redact patcher。

PII redact 设计目标
==================

不存在「调用方记得手动脱敏」这种约定都能 100% 兑现的情况。所以本模块在 loguru
``configure(patcher=...)`` 注入一个全局函数，在每条日志被送往任何 sink 之前先：

1. 用正则扫描 ``record["message"]``，对形如 ``remid=xxx`` / ``sid:yyy`` /
   ``access_token=zzz`` 的片段把 value 替换成 ``[REDACTED]``，保留 key 名以便追踪。
2. 扫描 ``record["extra"]`` 字典，按 key 名（如 ``email``、``password``、``code``）
   把整个值替换成 ``[REDACTED]``，覆盖 ``logger.bind(...)`` 误传敏感字段的场景。

这只是「兜底」，不替代调用方该做的脱敏：日志里就不应该出现 password 原文。但有
EA 邮箱密码登录链路、BF1Gateway 这类历史代码会打印 ``remid``/``sid``/
``access_token``，patcher 是它们的保险网。
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings

# ``logger.bind(key=value)`` 中按 key 名脱敏的字段集合（大小写不敏感比对）。
_SENSITIVE_EXTRA_KEYS = frozenset(
    {
        "email",
        "password",
        "code",
        "onetimecode",
        "one_time_code",
        "remid",
        "sid",
        "access_token",
        "authcode",
        "gateway_session_id",
        "gatewaysessionid",
        "cookie",
        "set_cookie",
        "session_id",
        "raw_password",
    }
)

# message 字符串内的 ``key=value`` / ``key: value`` 模式。``key`` 必须命中已知敏感
# 名，避免误伤普通业务字段（例如 ``page=2``）。
# ``[^\s;,'"&\)]+`` 故意排除常见分隔符，使 cookie 串里的多个 KV 都能被独立替换。
_SENSITIVE_KV_PATTERN = re.compile(
    r"(?i)\b(?P<key>remid|sid|access_token|authcode|oneTimeCode|"
    r"set-cookie|cookie|gatewaySessionId)"
    r"\s*[=:]\s*[\"']?(?P<val>[^\s;,'\"&\)]+)"
)


def _redact_text(text: str) -> str:
    """对字符串做敏感字段值替换，保留 key 名便于追踪。"""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group('key')}=[REDACTED]"

    return _SENSITIVE_KV_PATTERN.sub(_replace, text)


def _pii_patcher(record: dict[str, Any]) -> None:
    """全局 loguru patcher。

    被 ``logger.configure(patcher=...)`` 注册后，对每一条 log record 在到达 sink 之前
    调用。修改 ``record["message"]`` 与 ``record["extra"]`` 原地生效。
    """
    msg = record.get("message")
    if isinstance(msg, str):
        record["message"] = _redact_text(msg)

    extra = record.get("extra")
    if extra:
        for key in list(extra.keys()):
            if key.lower() in _SENSITIVE_EXTRA_KEYS:
                extra[key] = "[REDACTED]"


class InterceptHandler(logging.Handler):
    """将标准 logging 转发到 loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    # 在 add() 之前注册 patcher，避免出现「先有日志、后装 patcher」的窗口期。
    logger.configure(patcher=_pii_patcher)
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        backtrace=settings.debug,
        diagnose=settings.debug,
    )

    # 接管 uvicorn / fastapi / sqlalchemy 日志
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False


__all__ = ["InterceptHandler", "setup_logging"]
