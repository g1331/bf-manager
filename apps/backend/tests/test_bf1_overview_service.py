"""BF1 全服统计聚合的纯函数单测

覆盖 build_overview 的官方/私服拆分、亚洲/欧洲/其他地区分桶、热门地图模式与模式分布排序，
不依赖 EA 网络与数据库。
"""

from __future__ import annotations

from app.schemas.bf1.server import ServerSummary
from app.services.bf1.overview_service import _region_key, build_overview


def _summary(
    *,
    region: str | None,
    official: bool,
    players: int,
    queue: int = 0,
    spectator: int = 0,
    mode: str = "征服",
    map_name: str = "剃刀边缘",
) -> ServerSummary:
    return ServerSummary(
        server_id=0,
        name="s",
        player_count=players,
        max_player_count=64,
        queue_count=queue,
        spectator_count=spectator,
        region=region,
        region_display_name=region,
        is_official=official,
        game_mode=mode,
        mode_display_name=mode,
        map_name=map_name,
        map_display_name=map_name,
    )


def test_region_key_buckets() -> None:
    assert _region_key("Asia") == "asia"
    assert _region_key("EU") == "eu"
    assert _region_key("OC") == "other"
    assert _region_key("NAm") == "other"
    assert _region_key(None) == "other"


def test_build_overview_splits_official_private_and_regions() -> None:
    summaries = [
        _summary(region="Asia", official=True, players=40, queue=2, spectator=1),
        _summary(region="Asia", official=False, players=30, queue=1),
        _summary(region="EU", official=True, players=20),
        _summary(region="OC", official=False, players=10),
    ]
    ov = build_overview(summaries, sample_pulls=5, raw_count=8)

    assert ov.available is True
    assert ov.sample_pulls == 5
    assert ov.raw_count == 8

    # 服务器数
    assert ov.servers.total == 4
    assert ov.servers.official == 2
    assert ov.servers.private == 2
    assert ov.servers.asia == 2
    assert ov.servers.eu == 1
    assert ov.servers.other == 1

    # 在线人数
    assert ov.players.total == 100
    assert ov.players.official == 60
    assert ov.players.private == 40
    assert ov.players.asia == 70
    assert ov.players.eu == 20
    assert ov.players.other == 10

    # 排队与观众
    assert ov.queues.total == 3
    assert ov.queues.asia == 3
    assert ov.spectators.total == 1
    assert ov.spectators.official == 1


def test_build_overview_top_map_modes_sorted_by_players() -> None:
    summaries = [
        _summary(region="Asia", official=True, players=10, mode="征服", map_name="A"),
        _summary(region="Asia", official=True, players=64, mode="行动模式", map_name="B"),
        _summary(region="Asia", official=True, players=20, mode="征服", map_name="A"),
    ]
    ov = build_overview(summaries, sample_pulls=1, raw_count=3)

    # "征服 · A" 两台共 30 人；"行动模式 · B" 一台 64 人 → 按人数降序，行动模式在前
    assert ov.top_map_modes[0].label == "行动模式 · B"
    assert ov.top_map_modes[0].players == 64
    assert ov.top_map_modes[0].servers == 1
    assert ov.top_map_modes[1].label == "征服 · A"
    assert ov.top_map_modes[1].players == 30
    assert ov.top_map_modes[1].servers == 2

    # 模式分布按服务器数降序：征服 2 台在前
    assert ov.mode_distribution[0].label == "征服"
    assert ov.mode_distribution[0].servers == 2
    assert ov.mode_distribution[1].label == "行动模式"
    assert ov.mode_distribution[1].servers == 1


def test_build_overview_empty() -> None:
    ov = build_overview([], sample_pulls=1, raw_count=0)
    assert ov.available is True
    assert ov.servers.total == 0
    assert ov.top_map_modes == []
    assert ov.mode_distribution == []
