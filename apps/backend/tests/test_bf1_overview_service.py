"""BF1 全服统计聚合的纯函数单测

覆盖 build_overview 的官方/私服拆分、亚洲/欧洲/其他地区分桶、热门地图模式与模式分布排序，
Blaze 快照推送的聚合与去重、快照收包，以及快照失败回退 searchServers，不依赖 EA 网络与数据库。
"""

from __future__ import annotations

import asyncio

import pytest
from app.api.errors import EAApiError
from app.schemas.bf1.overview import BF1Overview
from app.schemas.bf1.server import ServerSummary
from app.services.bf1 import blaze_service, overview_service, server_snapshot_cache
from app.services.bf1.overview_service import (
    _region_key,
    _snapshot_mode,
    build_overview,
    build_overview_from_snapshot,
)


def _summary(
    *,
    region: str | None,
    official: bool,
    players: int,
    queue: int = 0,
    spectator: int = 0,
    mode: str = "征服",
    map_name: str = "剃刀边缘",
    map_image_url: str | None = None,
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
        map_image_url=map_image_url,
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


def test_build_overview_top_map_modes_carry_map_image() -> None:
    summaries = [
        # 同组首台无图、次台有图：应取到组内首个非空图
        _summary(region="Asia", official=True, players=10, mode="征服", map_name="A"),
        _summary(
            region="Asia",
            official=True,
            players=20,
            mode="征服",
            map_name="A",
            map_image_url="https://cdn.example/a.jpg",
        ),
        # 全组无图：image 保持 None
        _summary(region="EU", official=True, players=5, mode="行动模式", map_name="B"),
    ]
    ov = build_overview(summaries, sample_pulls=1, raw_count=3)

    by_label = {m.label: m for m in ov.top_map_modes}
    assert by_label["征服 · A"].image == "https://cdn.example/a.jpg"
    assert by_label["行动模式 · B"].image is None


def test_build_overview_top_servers_by_players_then_queue() -> None:
    summaries = [
        _summary(region="EU", official=False, players=n, queue=q)
        for n, q in [(10, 0), (64, 2), (64, 8), (0, 0)] + [(1, 0)] * 10
    ]
    ov = build_overview(summaries, sample_pulls=1, raw_count=len(summaries))
    assert len(ov.top_servers) == 10
    assert [(s.player_count, s.queue_count) for s in ov.top_servers[:3]] == [
        (64, 8),
        (64, 2),
        (10, 0),
    ]


def test_build_overview_empty() -> None:
    ov = build_overview([], sample_pulls=1, raw_count=0)
    assert ov.available is True
    assert ov.servers.total == 0
    assert ov.top_map_modes == []
    assert ov.mode_distribution == []


# ---- Blaze 快照路径 ----


def _game(
    gid: int,
    *,
    servertype: str = "RANKED",
    region: str = "Asia",
    pcnt: list[int] | None = None,
    qcnt: int = 0,
    level: str = "MP_Amiens",
    mode_attrs: dict[str, str] | None = None,
) -> dict:
    attrs = {"servertype": servertype, "region": region, "level": level, "HNET": "secret"}
    attrs.update(mode_attrs if mode_attrs is not None else {"mode": "Conquest0"})
    return {"GID": gid, "PCNT": pcnt or [0, 0, 0, 0], "QCNT": qcnt, "ATTR": attrs}


def test_build_overview_from_snapshot_aggregates_and_dedupes() -> None:
    updates = [
        {"GAM": _game(1, servertype="OFFICIAL", region="Asia", pcnt=[60, 2, 1, 1], qcnt=3)},
        _game(2, region="EU", pcnt=[30, 0, 0, 0], qcnt=1),
        {"GAM": _game(3, region="NAm", pcnt=[5, 0, 2, 0])},
        # 同一 GID 的后续更新覆盖前者，不重复计数
        {"GAM": _game(2, region="EU", pcnt=[32, 0, 0, 0], qcnt=1)},
    ]
    ov = build_overview_from_snapshot(updates)

    assert ov.sample_pulls == 1
    assert ov.raw_count == 4
    assert ov.servers.total == 3
    assert (ov.servers.official, ov.servers.private) == (1, 2)
    assert (ov.servers.asia, ov.servers.eu, ov.servers.other) == (1, 1, 1)
    assert ov.players.total == 62 + 32 + 5
    assert ov.players.official == 62
    assert ov.players.eu == 32
    assert ov.spectators.total == 2 + 2
    assert ov.queues.total == 4
    assert ov.queues.official == 3

    # 标签与 searchServers 路径同口径：ModeDict / MapTeamDict 中文名 + 固化的地图封面
    top = ov.top_map_modes[0]
    assert top.label == "征服 · 亚眠"
    assert top.image is not None
    assert top.image.startswith("https://eaassets-a.akamaihd.net/battlelog/battlebinary/")
    assert ov.mode_distribution[0].label == "征服"


def test_snapshot_mode_normalizes_codes() -> None:
    assert _snapshot_mode({"mode": "Conquest"}) == "Conquest"
    assert _snapshot_mode({"gamemode": "BreakthroughLarge0"}) == "BreakthroughLarge"
    assert _snapshot_mode({"levellocation": "MP_Amiens_TugOfWar0"}) == "TugOfWar"
    assert _snapshot_mode({"mode": "ConquestLarge0"}) == "Conquest"
    assert _snapshot_mode({"level": "MP_Amiens", "servertype": "RANKED"}) is None


def test_build_overview_from_snapshot_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError) as exc:
        build_overview_from_snapshot([{"GAM": _game(1, mode_attrs={})}])
    # 诊断信息只含键名与模式 / 地图相关值，隐私字段的值不外泄
    assert "HNET" in str(exc.value)
    assert "secret" not in str(exc.value)


def test_build_overview_from_snapshot_rejects_empty() -> None:
    with pytest.raises(ValueError):
        build_overview_from_snapshot([])


async def test_fetch_overview_prefers_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_snapshot(_db: object) -> list[dict]:
        return [{"GAM": _game(1, pcnt=[10, 0, 0, 0])}]

    async def no_search(_db: object) -> BF1Overview:
        raise AssertionError("快照成功时不应走 searchServers")

    monkeypatch.setattr(overview_service, "fetch_game_list_snapshot", fake_snapshot)
    monkeypatch.setattr(overview_service, "_fetch_overview_by_search", no_search)
    ov, summaries, source = await overview_service.fetch_overview(object())  # type: ignore[arg-type]
    assert ov.players.total == 10
    assert ov.sample_pulls == 1
    assert [s.game_id for s in summaries] == [1]
    assert source == "snapshot"


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timeout"), ConnectionError("kicked"), ValueError("bad mode")],
)
async def test_fetch_overview_falls_back_to_search(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    async def failing_snapshot(_db: object) -> list[dict]:
        raise failure

    fallback = BF1Overview(available=True, sample_pulls=50, raw_count=9000)

    async def fake_search(_db: object) -> tuple[BF1Overview, list]:
        return fallback, []

    monkeypatch.setattr(overview_service, "fetch_game_list_snapshot", failing_snapshot)
    monkeypatch.setattr(overview_service, "_fetch_overview_by_search", fake_search)
    assert await overview_service.fetch_overview(object()) == (fallback, [], "search")  # type: ignore[arg-type]


def test_snapshot_summary_fills_list_fields() -> None:
    game = _game(7, servertype="RANKED", region="EU", pcnt=[40, 1, 2, 0], qcnt=5)
    game["GNAM"] = "[ABC] 测试服"
    game["CAP"] = [64, 0, 4, 0]
    game["PSAS"] = "nrt"
    game["ATTR"].update(
        {
            "description1": "欢迎",
            "description2": "来玩",
            "description3": "",
            "country": "JP",
            "tickRate": "60",
        }
    )
    s = overview_service._snapshot_summary(game)

    assert (s.game_id, s.name, s.max_player_count) == (7, "[ABC] 测试服", 64)
    assert (s.player_count, s.queue_count, s.spectator_count) == (41, 5, 2)
    assert s.is_ranked and not s.is_official
    assert s.region_display_name is not None
    assert s.description == "欢迎来玩"
    assert s.ping_site == "nrt"
    assert (s.country, s.tick_rate) == ("JP", 60)
    # 隐私字段不会出现在摘要里
    assert "secret" not in s.model_dump_json()


async def test_refresh_writes_server_snapshot_and_spawns_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summaries = overview_service.snapshot_summaries([{"GAM": _game(1, pcnt=[10, 0, 0, 0])}])
    ov = overview_service.build_overview(summaries, sample_pulls=1, raw_count=1)

    async def fake_fetch(_db: object) -> tuple:
        return ov, summaries, "snapshot"

    class _Cache:
        def __init__(self) -> None:
            self.data: dict = {}

        async def set(self, key: str, value: object, ttl: int | None = None) -> None:
            self.data[key] = (value, ttl)

        async def list_append(self, *_a: object, **_k: object) -> None:
            return None

    cache = _Cache()

    async def fake_get_cache() -> _Cache:
        return cache

    spawned: list = []
    monkeypatch.setattr(overview_service, "fetch_overview", fake_fetch)
    monkeypatch.setattr(overview_service, "get_cache", fake_get_cache)
    monkeypatch.setattr(server_snapshot_cache, "get_cache", fake_get_cache)
    monkeypatch.setattr(overview_service, "_spawn_record_player_counts", spawned.append)
    await overview_service.refresh_overview_cache(object())  # type: ignore[arg-type]

    value, ttl = cache.data[server_snapshot_cache.SERVER_SNAPSHOT_CACHE_KEY]
    assert ttl == overview_service.OVERVIEW_CACHE_TTL
    assert value["source"] == "snapshot"
    assert [i["game_id"] for i in value["items"]] == [1]
    assert spawned == [summaries]


class _FakeSocket:
    """模拟 Blaze 连接：send 时先回 Result，再按批推送 NotifyGameListUpdate。"""

    def __init__(self, pushes: list[dict], reply_type: str = "Result") -> None:
        self.callback = None
        self.pushes = pushes
        self.reply_type = reply_type
        self.sent: list[dict] = []

    async def send(self, packet: dict, timeout: float = 60) -> dict:
        self.sent.append(packet)
        reply = {"method": packet["method"], "type": self.reply_type, "data": {"ERRC": 0x40040000}}
        if self.callback:
            self.callback(reply)  # 回调也会收到应答，须被过滤
            # 其它请求的推送也要被过滤
            self.callback({"method": "UserSessions.UserAdded", "type": "Message", "data": {}})

        async def deliver() -> None:
            for push in self.pushes:
                await asyncio.sleep(0)
                if self.callback:
                    self.callback(push)

        asyncio.get_running_loop().create_task(deliver())
        return reply


def _push(updt: list[dict], *, done: bool) -> dict:
    return {
        "method": "GameManager.NotifyGameListUpdate",
        "type": "Message",
        "data": {"UPDT": updt, "DONE": int(done)},
    }


async def test_fetch_game_list_snapshot_collects_pushes(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = _FakeSocket(
        [_push([{"GAM": _game(1)}], done=False), _push([{"GAM": _game(2)}], done=True)]
    )

    async def fake_get_socket(_db: object) -> _FakeSocket:
        return socket

    monkeypatch.setattr(blaze_service._pool, "get_socket", fake_get_socket)
    updates = await blaze_service.fetch_game_list_snapshot(object())  # type: ignore[arg-type]

    assert [u["GAM"]["GID"] for u in updates] == [1, 2]
    assert socket.sent[0]["method"] == "GameManager.getGameListSnapshot"
    assert socket.callback is None  # 回调已还原


async def test_fetch_game_list_snapshot_raises_on_error_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = _FakeSocket([], reply_type="Error")

    async def fake_get_socket(_db: object) -> _FakeSocket:
        return socket

    monkeypatch.setattr(blaze_service._pool, "get_socket", fake_get_socket)
    with pytest.raises(EAApiError, match="0x40040000"):
        await blaze_service.fetch_game_list_snapshot(object())  # type: ignore[arg-type]
    assert socket.callback is None
