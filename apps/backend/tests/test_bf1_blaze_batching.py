"""Blaze 生涯查询的分批与 Blaze 账号登记"""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.ea.account_pool import EACredentials
from app.services import ea_account_service
from app.services.bf1 import blaze_service
from app.services.bf1.blaze_service import (
    LIGHT_STATS_BATCH_SIZE,
    LIGHT_STATS_MAX_NAMES,
    STATS_BATCH_SIZE,
    _BlazeConnectionPool,
    fetch_stats,
    stats_batch_size,
)


class _Socket:
    connect = True
    authenticated = True

    def __init__(self) -> None:
        self.packets: list[dict[str, Any]] = []

    async def send(self, packet: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.packets.append(packet)
        data = packet["data"]
        names = data["NAME 41"]
        rows = [{"EID": pid, "STAT": [str(pid % 7)] * len(names)} for pid in data["EID  40"]]
        return {"type": "Result", "data": {"KSSV": {"No_Scope_Defined": {"STAT": rows}}}}


def test_batch_size_by_name_count() -> None:
    assert stats_batch_size(3) == LIGHT_STATS_BATCH_SIZE
    assert stats_batch_size(LIGHT_STATS_MAX_NAMES) == LIGHT_STATS_BATCH_SIZE
    assert stats_batch_size(LIGHT_STATS_MAX_NAMES + 1) == STATS_BATCH_SIZE
    assert stats_batch_size(550) == STATS_BATCH_SIZE


async def test_fetch_stats_batches_each_category_by_its_size(monkeypatch) -> None:
    socket = _Socket()

    async def get_socket(db: Any) -> _Socket:
        return socket

    monkeypatch.setattr(blaze_service._pool, "get_socket", get_socket)
    pids = list(range(1, 1101))
    heavy = [f"h{i}" for i in range(40)]
    light = ["c___roo_g", "c_mwin__roo_g", "c_mlos__roo_g"]
    out = await fetch_stats(None, pids, {"heavy": heavy, "light": light})  # type: ignore[arg-type]

    sizes: dict[str, list[int]] = {}
    for packet in socket.packets:
        sizes.setdefault(packet["data"]["CAT  1"], []).append(len(packet["data"]["EID  40"]))
    assert sizes == {"heavy": [512, 512, 76], "light": [1024, 76]}
    # 两个类别的结果按人合并，一个不少
    assert len(out) == len(pids)
    assert set(out[7]) == {*heavy, *light}


async def test_pool_registers_blaze_account_and_clears_it(monkeypatch) -> None:
    creds = EACredentials(persona_id=4242, display_name="b", remid="r", sid="s")

    class _Service:
        def __init__(self, db: Any) -> None:
            pass

        async def pick_available(self, *, avoid: Any = ()) -> EACredentials:
            avoided.append(set(avoid))
            return creds

    seen: list[int | None] = []
    avoided: list[set[int]] = []

    async def login_ok(self: Any, c: EACredentials) -> _Socket:
        seen.append(ea_account_service.blaze_persona())
        return _Socket()

    monkeypatch.setattr(blaze_service, "EAAccountService", _Service)
    monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_ok)
    pool = _BlazeConnectionPool()
    try:
        # Gateway 正拿着 99 号：Blaze 选号时避开它
        with ea_account_service.gateway_using(99):
            await pool.get_socket(None)  # type: ignore[arg-type]
        assert avoided == [{99}]
        assert ea_account_service.gateway_personas() == set()
        # 登录前就已登记，Gateway 从登录那一刻起避开这个号
        assert seen == [4242]
        assert ea_account_service.blaze_persona() == 4242
        await pool.close_all()
        assert ea_account_service.blaze_persona() is None

        async def login_fail(self: Any, c: EACredentials) -> _Socket:
            raise RuntimeError("login failed")

        monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_fail)
        with pytest.raises(RuntimeError):
            await pool.get_socket(None)  # type: ignore[arg-type]
        assert ea_account_service.blaze_persona() is None
    finally:
        ea_account_service.set_blaze_persona(None)


async def test_gateway_client_avoids_current_blaze_account(monkeypatch) -> None:
    from app.services.bf1 import gateway_factory

    asked: list[int | None] = []

    class _StopError(Exception):
        pass

    class _Service:
        def __init__(self, db: Any) -> None:
            pass

        async def pick_available(self, *, avoid: Any = ()) -> EACredentials:
            asked.append(tuple(avoid))
            raise _StopError

    monkeypatch.setattr(gateway_factory, "EAAccountService", _Service)
    ea_account_service.set_blaze_persona(777)
    try:
        with pytest.raises(_StopError):
            async with gateway_factory.get_bf1_client(None):  # type: ignore[arg-type]
                pass
    finally:
        ea_account_service.set_blaze_persona(None)
    assert asked == [(777,)]


async def test_gateway_client_registers_account_while_held(monkeypatch) -> None:
    from app.services.bf1 import gateway_factory

    creds = EACredentials(persona_id=55, display_name="g", remid="r", sid="s")

    class _Service:
        def __init__(self, db: Any) -> None:
            pass

        async def pick_available(self, *, avoid: Any = ()) -> EACredentials:
            return creds

        async def mark_used(self, persona_id: int) -> None:
            pass

        async def mark_failure(self, persona_id: int) -> None:
            pass

    class _Client:
        access_token = "t"
        credentials_rejected = session_rejected = False
        check_login = False
        http_session = None

        def __init__(self, **kw: Any) -> None:
            pass

    monkeypatch.setattr(gateway_factory, "EAAccountService", _Service)
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _Client)
    async with gateway_factory.get_bf1_client(None):  # type: ignore[arg-type]
        assert ea_account_service.gateway_personas() == {55}
    assert ea_account_service.gateway_personas() == set()
    with pytest.raises(RuntimeError):
        async with gateway_factory.get_bf1_client(None):  # type: ignore[arg-type]
            raise RuntimeError("boom")
    assert ea_account_service.gateway_personas() == set()
