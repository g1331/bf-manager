"""游戏特定层：每个支持的游戏在子目录中实现"""

# 通过显式导入触发各游戏 profile 注册
from app.domain.games import bf1  # noqa: F401
from app.domain.games.base import BlazeEndpoint, GameProfile
from app.domain.games.registry import GameRegistry

__all__ = ["BlazeEndpoint", "GameProfile", "GameRegistry"]
