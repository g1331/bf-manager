"""BF1 战绩页「收藏」分页：勋章、狗牌的解锁情况和当前佩戴的狗牌"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CollectionMedal(BaseModel):
    code: str = Field(description="勋章代号（如 m05、mxp107），与图鉴 medals 一致")
    unlocked: bool = Field(description="是否已获得，先看这个")
    stages_done: int = Field(
        description="已完成的阶段数，只在未解锁时有意义：解锁后 EA 会把阶段进度清零，可能为 0"
    )
    stages_total: int


class CollectionDogtag(BaseModel):
    id: str = Field(description="狗牌 unlockId（如 df082），与图鉴 dogtags 一致")
    unlocked: bool
    acquired: float | None = Field(default=None, description="未解锁时的进度，没有进度的为 null")
    needed: float | None = None


class PlayerCollection(BaseModel):
    persona_id: int
    medals: list[CollectionMedal]
    dogtags: list[CollectionDogtag]
    equipped: list[str] = Field(description="当前佩戴的狗牌 id：基本、高级各一块，读不到为空")
