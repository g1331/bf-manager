"""EA 账号池 schema：写入含明文凭据，读取仅暴露健康状态。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EAAccountCreate(BaseModel):
    """创建 EA 账号的请求体。

    remid 与 sid 为必填明文凭据，写入即加密；session 与 access_token 可选。
    所有明文仅用于写入加密存储，绝不会出现在任何响应里。
    """

    persona_id: int = Field(..., gt=0, description="EA persona id")
    display_name: str | None = Field(None, max_length=64)
    remid: str = Field(..., min_length=1, description="EA 登录 cookie remid（明文，写入即加密）")
    sid: str = Field(..., min_length=1, description="EA 登录 cookie sid（明文，写入即加密）")
    session: str | None = Field(None, description="运行期 session（明文，写入即加密）")
    access_token: str | None = Field(None, description="运行期 access_token（明文，写入即加密）")
    enabled: bool = Field(True, description="是否启用")


class EAAccountCredentialsUpdate(BaseModel):
    """仅更新凭据的请求体：不传的字段保持原值不变。"""

    remid: str | None = Field(None, min_length=1, description="EA 登录 cookie remid（明文）")
    sid: str | None = Field(None, min_length=1, description="EA 登录 cookie sid（明文）")
    session: str | None = Field(None, description="运行期 session（明文）")
    access_token: str | None = Field(None, description="运行期 access_token（明文）")


class EAAccountEnabledUpdate(BaseModel):
    """启用 / 停用请求体。"""

    enabled: bool


class EAAccountDisplayNameUpdate(BaseModel):
    """仅更新备注名的请求体：传 null 显式清空，传字符串覆盖原值。

    备注名不属于凭据，单独走子资源端点，避免与 /credentials 端点共享
    「凭据已修复 → 清零失败计数」之类的副作用。
    """

    display_name: str | None = Field(None, max_length=64, description="账号备注名，null 表示清空")


class EAAccountItem(BaseModel):
    """EA 账号读取模型：只暴露健康状态，绝不回显任何明文凭据。"""

    id: int
    persona_id: int
    display_name: str | None
    enabled: bool
    last_used_at: datetime | None
    failure_count: int
    has_session: bool
    has_access_token: bool
    created_at: datetime
    updated_at: datetime


class EAAccountVerifyResult(BaseModel):
    """连通性验证结果。"""

    success: bool
    persona_id: int
    message: str | None = None
