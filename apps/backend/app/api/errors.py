"""统一异常与错误响应"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    """业务异常：使用统一错误码"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": details},
            headers=headers,
        )
        self.code = code
        self.message = message
        self.details = details


class UnauthorizedError(AppError):
    def __init__(self, message: str = "未登录或会话已过期") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", message)


class ForbiddenError(AppError):
    def __init__(self, message: str = "无权访问此资源") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "FORBIDDEN", message)


class NotFoundError(AppError):
    def __init__(self, resource: str = "资源") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"{resource}不存在")


class EAApiError(AppError):
    """EA 上游调用失败。

    状态码用 503 而非语义上更贴切的 502：生产外层的 Cloudflare 会把源站的 502/504
    响应整体替换为自家 HTML 错误页（Origin Error Page Passthru 仅企业版可用），
    JSON 错误体到不了浏览器，前端只能展示空白报错；503 可原样穿透。
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_503_SERVICE_UNAVAILABLE, code, message, details)


class TooManyRequestsError(AppError):
    """请求过于频繁；retry_after 秒后可重试，同时写进 Retry-After 响应头。"""

    def __init__(self, message: str, retry_after: int) -> None:
        retry_after = max(int(retry_after), 1)
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "TOO_MANY_REQUESTS",
            message,
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


class EABusyError(AppError):
    """公共查询的 EA 预算本分钟已用完。

    沿用 503（见 EAApiError 关于 Cloudflare 的说明），同时带 Retry-After，前端据此提示等待。
    """

    def __init__(self, retry_after: int) -> None:
        retry_after = max(int(retry_after), 1)
        super().__init__(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "EA_BUSY",
            f"当前查询人数较多，本站查询账号有限，请 {retry_after} 秒后再试",
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


class ValidationError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", message, details)


class EaBindingRequiredError(AppError):
    """前置条件不满足：当前用户无可用 EA binding，无法执行需要 EA 凭据的操作"""

    def __init__(
        self,
        message: str = "此操作需要绑定一个可用的 EA 账号，请前往账号设置完成绑定或重新登录",
    ) -> None:
        super().__init__(status.HTTP_412_PRECONDITION_FAILED, "EA_BINDING_REQUIRED", message)


# ===== EA 邮箱密码登录任务（domain/ea/login）专属错误 =====
# 错误码统一以 `EA_LOGIN_TASK_` 开头，便于前端按前缀匹配文案。


class EALoginTaskError(AppError):
    """EA 登录任务族基类。子类负责给出具体 status_code、code、message。"""


class EALoginTaskNotFoundError(EALoginTaskError):
    def __init__(self, message: str = "登录任务不存在或已过期") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "EA_LOGIN_TASK_NOT_FOUND", message)


class EALoginTaskConflictError(EALoginTaskError):
    """与当前任务状态不匹配的操作。例如未到 2FA 阶段就提交验证码。"""

    def __init__(self, message: str = "当前任务状态不允许此操作") -> None:
        super().__init__(status.HTTP_409_CONFLICT, "EA_LOGIN_TASK_INVALID_STATE", message)


class EALoginTaskInvalidInputError(EALoginTaskError):
    """用户提交了形式上合法但内容被 EA 拒绝的输入（如验证码错误、2FA 方式不在列表中）。"""

    def __init__(
        self,
        message: str = "提交的内容被 EA 拒绝",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status.HTTP_400_BAD_REQUEST, "EA_LOGIN_TASK_INVALID_INPUT", message, details
        )


class EALoginTaskUnavailableError(EALoginTaskError):
    """任务依赖的运行时资源不可用（如 Redis 整体故障且无降级路径）。"""

    def __init__(self, message: str = "登录任务服务暂不可用，请稍后重试") -> None:
        super().__init__(status.HTTP_503_SERVICE_UNAVAILABLE, "EA_LOGIN_TASK_UNAVAILABLE", message)
