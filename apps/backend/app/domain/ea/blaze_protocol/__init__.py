"""Blaze 协议封装（跨游戏共享）

methods.py 当前包含的 Components / Commands 主要基于 BF1 协议反向工程得到，
底层 component ID（authentication、user session 等）在 BF 系列各代之间共享。
未来 BFV / BF2042 接入时，如果发现 component 定义有差异，再拆分为：
- methods_common.py（协议级共享常量）
- domain/games/<game_id>/blaze.py（游戏特定 method 覆盖）
"""

from app.domain.ea.blaze_protocol.protocol import Blaze, keepalive
from app.domain.ea.blaze_protocol.socket import BlazeServerREQ, BlazeSocket

__all__ = [
    "Blaze",
    "BlazeServerREQ",
    "BlazeSocket",
    "keepalive",
]
