"""BF1 游戏特定实现"""

from app.domain.games.bf1.profile import BF1Profile
from app.domain.games.registry import GameRegistry

# 模块导入时自动注册
GameRegistry.register(BF1Profile)

__all__ = ["BF1Profile"]
