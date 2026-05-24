"""跨游戏审计日志（共享）"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    acting_persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)

    game: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    server_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_persona_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # success / failure
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
