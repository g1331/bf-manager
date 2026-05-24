"""游戏元信息服务"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain.games.registry import GameRegistry
from app.schemas.game import GameInfo


def list_enabled_games() -> list[GameInfo]:
    settings = get_settings()
    enabled = set(settings.games)
    result: list[GameInfo] = []
    for p in GameRegistry.all():
        if p.game_id not in enabled:
            continue
        result.append(
            GameInfo(
                game_id=p.game_id,
                display_name=p.display_name,
                supports_rsp_management=p.supports_rsp_management,
                supports_vban=p.supports_vban,
                theme_token=p.theme_token,
            )
        )
    return result
