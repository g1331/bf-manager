"""平台用户表（身份层，与 EA 凭据完全分离）"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ea_binding import EaBinding

# 账号状态：
# - legacy：旧版 remid 登录自动建的号，有 EA 绑定、没有邮箱和密码，等本人认领
# - pending_binding：用非 EA 邮箱注册、还没绑上 EA，只能做绑定相关操作
# - active：正常账号（本地管理员也是 active）
USER_STATUSES = ("legacy", "pending_binding", "active")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 身份
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    local_password_hash: Mapped[str | None] = mapped_column(String(255))
    # 只存验证过的邮箱。本地管理员和待认领的老账号没有邮箱
    email: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )

    # 平台角色
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 平台管理员在后台冻结时记下，解冻时清空
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frozen_reason: Mapped[str | None] = mapped_column(String(200))
    frozen_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_users_frozen_by_users")
    )
    # 本人申请注销后到这个时间点删除；冷静期内账号按冻结处理，用密码登录时可以撤销
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    # 会话版本：JWT 带 sv，和这里不一致就失效。改密码、登出所有设备、冻结时 +1
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ea_bindings: Mapped[list[EaBinding]] = relationship(
        "EaBinding",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # 邮箱不区分大小写唯一；没有邮箱的账号不参与
        Index(
            "uq_users_email_lower",
            func.lower(email),
            unique=True,
            postgresql_where=email.isnot(None),
            sqlite_where=email.isnot(None),
        ),
    )
