"""BF1 对局：由生涯差分算出的每局战绩"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    LargeBinary,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf1Round(Base):
    """一局：哪个实例、什么图、起止时间、胜方，以及参与者 pid（排序差值 varint，见 round_stats）"""

    __tablename__ = "bf1_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    map_name: Mapped[str | None] = mapped_column(String(64))
    game_mode: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # 开局时就在跟踪；为假时是服务重启或刚发现这台服时接手的局，起始时间与开局前退出的人不全
    observed_start: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 看到了结算；为假时是服务器关掉或断档，没打完
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    winner: Mapped[int | None] = mapped_column(SmallInteger)  # 1 / 2，判不出为空
    player_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pids: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (Index("ix_bf1_rounds_game_ended", "game_id", "ended_at"),)


class Bf1PlayerRoundDay(Base):
    """每人每天（按结束时间的 UTC 日期）一行，这一天各局的战绩条目首尾相接追加在 data 里"""

    __tablename__ = "bf1_player_round_days"

    pid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class Bf1CareerSnapshot(Base):
    """每人最近一次读到的完整生涯：核心向量（varint）和武器载具快照（round_weapons.pack）

    跟踪器进服时先查核心，和这里存的一样就沿用武器载具，不用再读 5 个武器类别。保留 14 天。
    """

    __tablename__ = "bf1_career_snapshots"

    pid: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    core: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    weapons: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
