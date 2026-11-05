"""BF6 对局估算：每人最近一次的生涯快照，以及两次快照之间的增量。

EA 不提供 BF6 逐场战报。被查过的玩家由后台定时重读生涯，场次或战斗时间变了就把差值记成一条估算；
复查间隔内打了几场会合并成一条。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Bf6StatSnapshot(Base):
    __tablename__ = "bf6_stat_snapshots"

    nucleus_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    # global 维度的 {统计名: 值}，zlib 压缩的 JSON
    stats: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # 开始记录的时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # stats 这份基线是什么时候读到的：之后结束的对局才会出现在下一条估算里
    polled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 最近一次尝试复查的时间（EA 没返回这个人也算），决定下次什么时候复查
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 最近一次生涯有变化的时间，决定复查间隔
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 最近一次有人打开战绩页的时间；太久没人看就不再复查
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Bf6MatchEstimate(Base):
    __tablename__ = "bf6_match_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    nucleus_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 这段里的对局在 started_after 之后、observed_at 之前结束
    started_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    matches: Mapped[int] = mapped_column(Integer, nullable=False)
    # 其余字段见 schemas.bf6.matches.Bf6MatchEstimate
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (Index("ix_bf6_match_estimates_player", "nucleus_id", "observed_at"),)
