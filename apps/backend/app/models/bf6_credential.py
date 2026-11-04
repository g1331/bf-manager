"""BF6 查询凭据：全站只有一行（id=1），管理员在后台填写。

refresh token 每刷新一次就轮换，旧值立刻作废，所以必须存库并在刷新时加行锁，
API 进程和后台任务不能同时刷。access token 也存库，重启后不用重新刷新。
敏感字段用 ``ea_cred_encryption_key`` 加密，接口只回过期时间和状态，不回原值。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

BF6_CREDENTIAL_ID = 1


class Bf6Credential(Base, TimestampMixin):
    __tablename__ = "bf6_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    encrypted_client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 最近一次失败的原因（不含任何凭据），成功刷新后清空
    last_error: Mapped[str | None] = mapped_column(String(255))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # 每写入一次新 token 加一。写库失败后补写时核对它，过期的 token 不能盖掉后来写进去的
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
