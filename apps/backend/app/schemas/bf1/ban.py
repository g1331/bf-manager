"""BF1 玩家外部封禁状态 schema"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# 单一封禁来源的三态：clean 无记录、hit 命中（BFBAN 实锤 / BFEAC 已封禁）、
# unknown 查询失败或缺少凭据无法判定。前端 BanBadge 直接消费这三态。
BanSourceState = Literal["clean", "hit", "unknown"]


class BanStatus(BaseModel):
    """玩家在外部反作弊库（BFBAN / BFEAC）的封禁状态。

    作为玩家页的补充信息展示。两个来源各自独立取三态，任一来源查询失败只把
    该来源置为 unknown，不影响另一来源与主战绩。命中时若上游给出案件页地址，
    一并透出供前端跳转。
    """

    persona_id: int
    bfban: BanSourceState = "unknown"
    bfeac: BanSourceState = "unknown"
    bfban_url: str | None = None  # BFBAN 案件页（命中时可得）
    bfeac_url: str | None = None  # BFEAC 案件页（命中时可得）
