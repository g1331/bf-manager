"""平台用户表（身份层，与 EA 凭据完全分离）"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ea_binding import EaBinding


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 身份
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    local_password_hash: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))

    # 平台角色
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ea_bindings: Mapped[list[EaBinding]] = relationship(
        "EaBinding",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
