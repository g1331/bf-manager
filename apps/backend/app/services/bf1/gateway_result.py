"""把 gateway 的返回值变成「数据或 HTTP 错误」

gateway 失败时返回 EAGatewayError（见 gateway_errors），这里按失败种类定状态码：

- EA 明确拒绝 → 422 EARejectedError；配了 ``not_found`` 且是查无此物 → 404
- 网络、EA 超时、会话失效、格式不对 → 503 EAApiError，retryable=True
- 本地代码出错 → 503 EAApiError，同时记 error 日志
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.api.errors import AppError, EAApiError, EARejectedError, NotFoundError
from app.domain.games.bf1.gateway_errors import EAGatewayError, gateway_failure


def error_details(err: EAGatewayError) -> dict[str, Any]:
    return {"kind": err.kind, "ea_code": err.code, "ea_message": err.ea_message}


def to_ea_error(err: EAGatewayError, *, code: str, action: str | None = None) -> EAApiError:
    """action 是失败文案的前缀（如「查询服务器详情」），不给就直接用 gateway 的文案"""
    text = str(err)[:256]
    message = f"{action}失败：{text}" if action else text
    if err.rejected:
        return EARejectedError(code=code, message=message, details=error_details(err))
    if err.kind == "internal":
        logger.error("BF1 gateway 本地出错 code={}: {!r}", code, err)
    return EAApiError(
        code=code, message=message, details=error_details(err), retryable=err.retryable
    )


def to_app_error(
    err: EAGatewayError, *, code: str, action: str | None = None, not_found: str | None = None
) -> AppError:
    """同 to_ea_error；给了 not_found（资源名）时，EA 回「查无此物」转成 404"""
    if not_found and err.not_found:
        return NotFoundError(resource=not_found)
    return to_ea_error(err, code=code, action=action)


def expect_ok(
    res: Any, *, code: str, action: str | None = None, not_found: str | None = None
) -> dict[str, Any]:
    """成功返回 EA 的 JSON，失败按种类抛 AppError"""
    err = gateway_failure(res)
    if err is None:
        return res
    raise to_app_error(err, code=code, action=action, not_found=not_found)
