"""群组：成员、角色、邀请链接

群组是服管的协作单位：群主给群添加服务账号（EA 凭据，执行服管操作用），再把服挂到群上，
群里的成员就能在这台服上做服管操作。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User

# 群内角色：群主 / 管理员两级（同 tenko v3 的服主 / 管理员）
GROUP_ROLES = ("owner", "admin")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan", passive_deletes=True
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    group: Mapped[Group] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class GroupInvite(Base):
    """群邀请链接 /invite#token=…。只存 token 的 sha256。

    链接自带注册资格（不用邀请码），所以默认只能用 1 次、最多 10 次，
    靠它注册的新账号计入发链接人的邀请码名额。
    """

    __tablename__ = "group_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GroupEaAccount(Base):
    """群组服务账号：群主提交的 EA 凭据（AES-GCM 加密），群里绑定的服用它执行服管操作。

    不并进 ea_accounts：号池挑号时不能挑到群的号。
    """

    __tablename__ = "group_ea_accounts"
    __table_args__ = (
        UniqueConstraint("group_id", "persona_id", name="uq_group_ea_accounts_group_persona"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))
    encrypted_remid: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_sid: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_session: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # ok / invalid：连续登录失败到阈值标 invalid，群主重新提交凭据后恢复
    status: Mapped[str] = mapped_column(
        String(16), default="ok", server_default="ok", nullable=False
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String(255))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GroupServer(Base):
    """挂在群上的服。同一台服可以挂在多个群里。

    status=active 时群成员在这台服上有管理员权限；绑定人不再是这台服的服主或管理员时
    复核会把它标成 revoked，权限随之失效。executor_problem 记执行账号的问题（没指定、
    已不是这台服的管理员），不影响权限，只是服管操作会失败。
    """

    __tablename__ = "group_servers"
    __table_args__ = (
        UniqueConstraint("group_id", "server_pk", name="uq_group_servers_group_server"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    bound_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # 绑定人当时在 EA 上的身份：owner / admin。只记录，不限制权限
    bound_via: Mapped[str] = mapped_column(String(16), nullable=False)
    executor_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("group_ea_accounts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(String(255))
    executor_problem: Mapped[str | None] = mapped_column(String(255))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
