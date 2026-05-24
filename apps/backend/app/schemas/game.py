"""游戏相关 schema"""

from __future__ import annotations

from pydantic import BaseModel


class GameInfo(BaseModel):
    game_id: str
    display_name: str
    supports_rsp_management: bool
    supports_vban: bool
    theme_token: str
