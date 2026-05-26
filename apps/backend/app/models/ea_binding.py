"""EA 账号绑定表（凭据层，与身份层 User 分离）"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class EaBinding(Base, TimestampMixin):
    __tablename__ = "ea_bindings"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    persona_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))

    # EA 凭据（AES-256-GCM 加密）。解绑时全部置 NULL。
    encrypted_remid: Mapped[str | None] = mapped_column(Text)
    encrypted_sid: Mapped[str | None] = mapped_column(Text)
    encrypted_session: Mapped[str | None] = mapped_column(Text)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="ea_bindings")

    # 一个 user 至多一条 primary binding。partial unique index 兜底，service 层提前校验。
    __table_args__ = (
        Index(
            "uq_ea_bindings_user_primary",
            "user_id",
            unique=True,
            postgresql_where="is_primary = true",
        ),
    )
