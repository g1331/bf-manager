"""EA 登录任务的 Pydantic 入参 / 出参模型。

设计要点：
- 所有「敏感字段」（email / password / 2FA code）使用 ``SecretStr``，保证 model
  默认 ``repr`` / 日志输出全为 ``'**********'``。
- 响应模型绝不携带 remid / sid / access_token 等明文凭据。
- ``EALoginTaskResponse`` 的 ``version`` 字段是长轮询协议的核心：客户端把上次拿到的
  ``version`` 通过 ``?since_version=N`` 回传，服务端 hold 住直到 ``current > N`` 才
  返回，超时则原样回退。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field, SecretStr


class EALoginTaskStatus(StrEnum):
    """任务公开状态机。

    状态流转：

    1. ``PENDING``：任务已创建，登录引擎仍在 EA 多步请求中。
    2. ``AWAITING_2FA_METHOD``：EA 提供了多种 2FA 方式，等待调用方选一种。
    3. ``AWAITING_2FA_CODE``：EA 已经下发验证码，等待调用方提交。
    4. ``FINALIZING``：拿到 remid/sid，正在调用 ``BF1GatewayClient.login`` 拉取
       session / persona 详情，并落库加密回填。该状态通常持续数百毫秒。
    5. ``SUCCEEDED`` / ``FAILED`` / ``CANCELLED``：终态，任务进入 TTL 倒计时。

    引擎内部还有 ``AWAITING_PASSWORD`` 等子步，但不对外暴露，避免前端依赖 EA 流程
    的实现细节。
    """

    PENDING = "pending"
    AWAITING_2FA_METHOD = "awaiting_2fa_method"
    AWAITING_2FA_CODE = "awaiting_2fa_code"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 终态集合，task_manager 用于判断是否应停止驱动 + 启动 TTL 倒计时。
TERMINAL_STATUSES = frozenset(
    {EALoginTaskStatus.SUCCEEDED, EALoginTaskStatus.FAILED, EALoginTaskStatus.CANCELLED}
)


class EALoginTaskCreateRequest(BaseModel):
    """启动一次 EA 邮箱密码登录任务的请求体。

    ``email`` 与 ``password`` 仅在内存中流转：``SecretStr`` 的 ``__repr__`` 与
    ``model_dump`` 默认输出 ``'**********'``，需要明文时显式调用 ``get_secret_value()``。
    """

    email: EmailStr = Field(..., description="EA 账号邮箱")
    password: SecretStr = Field(..., description="EA 账号密码（仅内存中流转）")


class EALoginTaskSelectMethodRequest(BaseModel):
    """选择 2FA 方式的请求体。

    EA 实际下发的 2FA method 不仅有 EMAIL / APP / SMS，还会出现 SECOND_EMAIL（备用邮箱）、
    BACKUP_CODE、TRUSTED_DEVICE 等账号配置相关的扩展值。前端按钮直接渲染
    ``task.available_methods``，故请求侧也对称放宽为 ``str``；具体合法值由
    ``task_manager.submit_method`` 用 ``method ∈ state.available_methods`` 做白名单校验，
    避免任意字符串被透传给 EA。
    """

    method: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="EA 返回的可选方式之一，必须在 task.available_methods 中",
    )


class EALoginTaskSubmitCodeRequest(BaseModel):
    """提交 2FA 验证码的请求体。"""

    code: SecretStr = Field(..., description="EA 发送的一次性验证码（仅内存中流转）")


class EALoginTaskResultData(BaseModel):
    """登录成功后的回填摘要。绝不包含任何明文凭据。"""

    persona_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    # ``binding_id`` 仅对普通用户路径有意义；admin 路径写入 ea_accounts，对应
    # ``account_id``。两者互斥，前端按当前 actor 自行区分。
    binding_id: int | None = None
    account_id: int | None = None


class EALoginTaskResponse(BaseModel):
    """任务状态查询响应：长轮询与一次性查询共用。"""

    task_id: str
    status: EALoginTaskStatus
    # 单调递增；每次任务状态有变化都自增 1。前端用作长轮询的 ``since_version``。
    version: int
    available_methods: list[str] = Field(default_factory=list)
    selected_method: str | None = None
    # 2FA EMAIL 方式下的脱敏目标地址（如 ``a***@e***``），仅供展示，不进日志。
    masked_destination: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: EALoginTaskResultData | None = None
    created_at: datetime
    updated_at: datetime


class EALoginTaskCreateResponse(BaseModel):
    """创建任务的响应：仅返回 task_id 与初始版本，详情由 GET 端点拉取。"""

    task_id: str
    version: int = 0
    status: EALoginTaskStatus = EALoginTaskStatus.PENDING


__all__ = [
    "TERMINAL_STATUSES",
    "EALoginTaskCreateRequest",
    "EALoginTaskCreateResponse",
    "EALoginTaskResponse",
    "EALoginTaskResultData",
    "EALoginTaskSelectMethodRequest",
    "EALoginTaskStatus",
    "EALoginTaskSubmitCodeRequest",
]
