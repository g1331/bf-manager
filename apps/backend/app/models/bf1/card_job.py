"""BF1 一键卡行动任务：一次卡行动或手动锚定一行"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Bf1CardJob(Base, TimestampMixin):
    __tablename__ = "bf1_card_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # card：抽图 + 锚定；anchor：只对当前图池锚定
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    game_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_name: Mapped[str] = mapped_column(
        String(128), default="", server_default="", nullable=False
    )
    # 发起的平台用户，匿名为空
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 服主 EA 账号；凭据只在任务协程内存里，不落库
    persona_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    persona_name: Mapped[str] = mapped_column(
        String(64), default="", server_default="", nullable=False
    )
    # 匿名查看进度用的令牌，只存 sha256
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # running / succeeded / failed / cancelled / interrupted
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # 开始前的服务器设置与轮换（card_engine.Snapshot），含服务器密码，加密存放
    snapshot_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 卡到的图池（地图代号，下标即 levelIndex）
    result_maps: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str] = mapped_column(String(256), default="", server_default="", nullable=False)
    # 执行记录，新的在前，最多 card_engine.EVENT_LIMIT 条
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
