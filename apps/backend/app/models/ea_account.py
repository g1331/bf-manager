"""平台维护的 EA 账号池（用于代查询，跨游戏共享）"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EAAccount(Base, TimestampMixin):
    __tablename__ = "ea_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    persona_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(64))

    # AES-256-GCM 加密
    encrypted_remid: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_sid: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_session: Mapped[str | None] = mapped_column(Text)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 限流计数（简易实现，未来可换 Redis）
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # 累计被取用次数：每次成功取用（mark_used）自增 1，供运维观察账号负载分布
    use_count: Mapped[int] = mapped_column(default=0, nullable=False)
