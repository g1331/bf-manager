"""游戏注册表（全局单例）"""

from __future__ import annotations

from typing import ClassVar

from app.domain.games.base import GameProfile


class GameRegistry:
    _games: ClassVar[dict[str, GameProfile]] = {}

    @classmethod
    def register(cls, profile: GameProfile) -> None:
        if not getattr(profile, "game_id", None):
            raise ValueError("GameProfile must define game_id")
        cls._games[profile.game_id] = profile

    @classmethod
    def get(cls, game_id: str) -> GameProfile:
        if game_id not in cls._games:
            raise KeyError(f"Game not registered: {game_id}")
        return cls._games[game_id]

    @classmethod
    def has(cls, game_id: str) -> bool:
        return game_id in cls._games

    @classmethod
    def all(cls) -> list[GameProfile]:
        return list(cls._games.values())

    @classmethod
    def enabled_ids(cls, enabled: list[str]) -> list[str]:
        """与配置交集，按注册顺序返回"""
        return [gid for gid in cls._games if gid in enabled]
