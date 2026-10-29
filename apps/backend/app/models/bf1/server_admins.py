"""BF1 服务器 VIP / Ban / Admin / Owner 与平台服管 VIP"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Bf1ServerVip(Base, TimestampMixin):
    """平台托管的计时 VIP。

    只登记经平台加的限时 VIP 和行动服待生效队列；EA 名单里没有记录的 VIP 视为永久、
    由别处管理，平台不会去动。
    - active：已在 EA 名单里，到 expires_at 下掉；
    - pending：行动服排队中，还没加进 EA 名单，remaining_seconds 是冻结的剩余时长
      （为空表示永久），checkvip 补进空位时才开始计时。
    """

    __tablename__ = "bf1_server_vips"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    remaining_seconds: Mapped[int | None] = mapped_column(BigInteger)
    # 排队顺序；续期不改它
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 最后一次授予或改期的人；到期自动下 V 时优先用他的绑定凭据
    granted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # 到期没能自动下掉时的退避与报错
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("server_pk", "persona_id", name="uq_bf1_vips_server_persona"),
    )


class Bf1ServerBan(Base, TimestampMixin):
    """服务器封禁列表"""

    __tablename__ = "bf1_server_bans"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))

    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("server_pk", "persona_id", name="uq_bf1_bans_server_persona"),
    )


class Bf1ServerAdmin(Base, TimestampMixin):
    __tablename__ = "bf1_server_admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("server_pk", "persona_id", name="uq_bf1_admins_server_persona"),
    )


class Bf1ServerOwner(Base, TimestampMixin):
    __tablename__ = "bf1_server_owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("server_pk", "persona_id", name="uq_bf1_owners_server_persona"),
    )


class Bf1ServerManagerVip(Base, TimestampMixin):
    """平台服管 VIP 体系（用户在平台上申请 / 续费的 VIP）"""

    __tablename__ = "bf1_server_manager_vips"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_pk: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    persona_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    granted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint(
            "server_pk",
            "persona_id",
            "valid_from",
            name="uq_bf1_manager_vips_server_persona_from",
        ),
    )
