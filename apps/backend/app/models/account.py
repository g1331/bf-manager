"""账号相关的一次性凭据：邮件验证链接、邀请码"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 验证链接的用途
# - register：注册（EA 邮箱注册或其他邮箱注册），打开后设置密码
# - claim：EA 号挂在老账号上，打开后给老账号设置邮箱和密码
# - reset：找回密码
# - set_email：已登录的老账号补邮箱
VERIFICATION_KINDS = ("register", "claim", "reset", "set_email")


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # 小写后的邮箱，信就发到这里
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # 链接里的 token 只存 sha256，明文只出现在邮件里
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # claim / reset / set_email 指向已有账号；register 为空
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # persona_id / ea_user_id / display_name / invite_code_id，不含密码
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    request_ip: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
