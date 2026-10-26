"""BF1 私服名单时间线：每人每服每天一行，进出与换队压成事件串追加在行内"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1ServerPlayerDay(Base):
    __tablename__ = "bf1_server_player_days"
    # 迁移里把 fillfactor 设成 80：每分钟几百次追加，留页内余量让更新走 HOT，不随更新膨胀

    # 主键也是唯一的索引：差分写入与按服按天读取都走它
    game_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)  # UTC 日期
    pid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 每个事件 4 个 base64 字符，编解码见 server_roster_service
    events: Mapped[str] = mapped_column(Text, nullable=False)


class Bf1PlayerName(Base):
    """名单里的 personaId → 名字。只在进服和跨天时刷新，不在每一行里重复存名字。"""

    __tablename__ = "bf1_player_names"

    pid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
