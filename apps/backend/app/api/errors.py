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
    ) -> None:
        super().__init__(
            status_code=status_code, detail={"code": code, "message": message, "details": details}
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
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, code, message, details)


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
