"""EA 账号绑定表（凭据层，与身份层 User 分离）"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

# 绑定时证明 EA 账号归属的方式
# - email：EA 账号邮箱收到验证信
# - cookie：提交 remid / sid
# - password：EA 邮箱密码登录（EaLoginFlow）
# - legacy：旧版 remid 登录留下来的
VERIFIED_VIA = ("email", "cookie", "password", "legacy")


class EaBinding(Base, TimestampMixin):
    __tablename__ = "ea_bindings"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # 只对未冻结的行唯一（见 __table_args__）：解绑、改绑后的历史行不占着这个 EA 号
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    # EA 账号 id（SAL 的 pd）。邮箱反查时拿得到，其他方式可能为空
    ea_user_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    verified_via: Mapped[str | None] = mapped_column(String(16))

    # EA 凭据（AES-256-GCM 加密）。解绑时全部置 NULL。新绑定不再保存，只有老账号留着
    encrypted_remid: Mapped[str | None] = mapped_column(Text)
    encrypted_sid: Mapped[str | None] = mapped_column(Text)
    encrypted_session: Mapped[str | None] = mapped_column(Text)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="ea_bindings")

    __table_args__ = (
        # 一个 user 至多一条 primary binding。partial unique index 兜底，service 层提前校验。
        Index(
            "uq_ea_bindings_user_primary",
            "user_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
            sqlite_where=text("is_primary = 1"),
        ),
        # 一个 EA 号同时只能绑在一个账号上
        Index(
            "uq_ea_bindings_persona_active",
            "persona_id",
            unique=True,
            postgresql_where=text("is_frozen = false"),
            sqlite_where=text("is_frozen = 0"),
        ),
    )
