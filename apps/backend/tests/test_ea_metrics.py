"""EA 调用计数：来源标记、进程内累加、写入 Redis 的键与字段，以及管理端的拆分汇总。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from app.core import ea_metrics
from app.services.metrics_service import _ea_breakdown


class _FakePipe:
    def __init__(self, store: dict[str, dict[str, int]]) -> None:
        self.store = store
        self.expires: dict[str, int] = {}

    def hincrby(self, key: str, field: str, n: int) -> None:
        h = self.store.setdefault(key, {})
        h[field] = h.get(field, 0) + n

    def expire(self, key: str, ttl: int) -> None:
        self.expires[key] = ttl

    async def execute(self) -> list[None]:
        return []


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, int]] = {}

    def pipeline(self) -> _FakePipe:
        return _FakePipe(self.store)


@pytest.fixture(autouse=True)
def _clean() -> None:
    ea_metrics._take()


async def test_counts_by_source_and_inherits_into_tasks() -> None:
    ea_metrics.set_source("tracker")
    ea_metrics.count("blaze", "Stats.getStats")
    ea_metrics.count_pids(64)
    with ea_metrics.ea_source("tracker_probe"):
        ea_metrics.count("blaze", "Stats.getStats")
    # 子任务创建时继承当时的来源，在子任务里改来源不影响外面

    async def child() -> None:
        ea_metrics.count("blaze", "Stats.getStats")
        ea_metrics.set_source("server_id")
        ea_metrics.count("gateway", "GameServer.getFullServerDetails")

    await asyncio.create_task(child())
    ea_metrics.count("blaze", "Stats.getStats")

    store = _FakeRedis()
    await ea_metrics.flush(store, datetime(2026, 10, 28, 9, 15, tzinfo=UTC))
    day = store.store["bfm:metrics:ea:day:20261028"]
    assert day == {
        "blaze|Stats.getStats|tracker": 3,
        "blaze|Stats.getStats|tracker_probe": 1,
        "gateway|GameServer.getFullServerDetails|server_id": 1,
    }
    assert store.store["bfm:metrics:ea:hour:2026102809"] == day
    assert store.store["bfm:metrics:ea:pids:day:20261028"] == {"tracker": 64}

    # 写完清零，再写一次不会重复累加
    await ea_metrics.flush(store, datetime(2026, 10, 28, 9, 15, tzinfo=UTC))
    assert store.store["bfm:metrics:ea:day:20261028"]["blaze|Stats.getStats|tracker"] == 3


async def test_flush_failure_drops_batch_quietly() -> None:
    class Broken:
        def pipeline(self) -> None:
            raise ConnectionError("redis down")

    ea_metrics.count("blaze", "Util.ping")
    await ea_metrics.flush(Broken())
    calls, _ = ea_metrics._take()
    assert not calls


def test_breakdown_groups_by_source_and_sorts() -> None:
    sources, methods = _ea_breakdown(
        {
            "blaze|Stats.getStats|tracker": "30",
            "blaze|GameManager.getGameListSnapshot|snapshot": "1",
            "gateway|Stats.detailedStatsByPersonaId|api:bf1/stats": "2",
            "blaze|Stats.getStats|api:bf1/stats": "6",
        },
        {"tracker": "1900", "api:bf1/stats": "6"},
    )
    assert [(s.source, s.calls, s.pids) for s in sources] == [
        ("tracker", 30, 1900),
        ("api:bf1/stats", 8, 6),
        ("snapshot", 1, 0),
    ]
    assert [(m.channel, m.method, m.source, m.count) for m in methods][:2] == [
        ("blaze", "Stats.getStats", "tracker", 30),
        ("blaze", "Stats.getStats", "api:bf1/stats", 6),
    ]


async def test_read_metrics_includes_ea_section(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import metrics_service

    now = datetime.now(UTC)
    today, hour = f"{now:%Y%m%d}", f"{now:%Y%m%d%H}"
    data: dict[str, object] = {
        "bfm:metrics:req:total": "10",
        f"bfm:metrics:req:day:{today}": "4",
        f"bfm:metrics:ea:day:{today}": {
            "blaze|Stats.getStats|tracker": "40",
            "gateway|RSP.getServerDetails|api:bf1/servers": "2",
        },
        f"bfm:metrics:ea:pids:day:{today}": {"tracker": "2500"},
        f"bfm:metrics:ea:hour:{hour}": {"blaze|Stats.getStats|tracker": "40"},
    }

    class Pipe:
        def __init__(self) -> None:
            self.ops: list[object] = []

        def get(self, k: str) -> None:
            self.ops.append(data.get(k))

        def mget(self, *ks: str) -> None:
            self.ops.append([data.get(k) for k in ks])

        def hgetall(self, k: str) -> None:
            self.ops.append(data.get(k) or {})

        def pfcount(self, *_ks: str) -> None:
            self.ops.append(0)

        async def execute(self) -> list[object]:
            return self.ops

    class Redis:
        def pipeline(self) -> Pipe:
            return Pipe()

    async def fake_redis() -> Redis:
        return Redis()

    monkeypatch.setattr(metrics_service, "get_redis", fake_redis)
    m = await metrics_service.read_metrics()
    assert m.available and m.requests_today == 4
    assert m.ea_calls_today == 42 and m.ea_calls_7d == 42
    assert m.daily[-1].ea_calls == 42
    assert [(s.source, s.calls, s.pids) for s in m.ea_sources] == [
        ("tracker", 40, 2500),
        ("api:bf1/servers", 2, 0),
    ]
    assert len(m.ea_hourly) == 24
    assert m.ea_hourly[-1].count == 40 and m.ea_hourly[0].count == 0
