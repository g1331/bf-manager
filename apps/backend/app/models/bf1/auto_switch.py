"""BF1 行动服自动换图：每台服一份编排、开关与运行状态"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Bf1AutoSwitch(Base, TimestampMixin):
    __tablename__ = "bf1_auto_switches"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # {"items": [{"map": "MP_Verdun", "scope": "operation" | "map", "repeat": 1}], "loops": 0}
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # 引擎状态（auto_switch_engine.initial_state），开启时重置
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # 最近的执行记录，新的在前，最多 EVENT_LIMIT 条
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # 开启人：换图用他的绑定凭据（EA 要求 RSP 管理员），审计里操作者记为「自动换图」
    enabled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
