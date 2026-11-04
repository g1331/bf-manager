"""Blaze 生涯查询的分批与 Blaze 账号登记"""

from __future__ import annotations

import asyncio
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

        async def pick_available(self, *, avoid: Any = (), exclude: Any = ()) -> EACredentials:
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

        async def pick_available(self, *, avoid: Any = (), exclude: Any = ()) -> EACredentials:
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

        async def pick_available(self, *, avoid: Any = (), exclude: Any = ()) -> EACredentials:
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


class _Pool:
    """假的号池：按 1、2 号的顺序挑第一个不在 avoid 里的号（都在就挑 1 号）；第一次挑号可以暂停在
    查库那一步，用来摆出「查库期间别人也来挑号」的交错。"""

    def __init__(self) -> None:
        self.accounts = {
            pid: EACredentials(persona_id=pid, display_name=None, remid="r", sid="s")
            for pid in (1, 2)
        }
        self.calls: list[set[int]] = []
        self.first_paused = asyncio.Event()
        self.resume_first = asyncio.Event()
        self.fail: Exception | None = None

    def service(self) -> type:
        pool = self

        class _Service:
            def __init__(self, db: Any) -> None:
                pass

            async def pick_available(self, *, avoid: Any = (), exclude: Any = ()) -> EACredentials:
                avoid = set(avoid)
                pool.calls.append(avoid)
                if len(pool.calls) == 1:
                    pool.first_paused.set()
                    await pool.resume_first.wait()
                if pool.fail is not None:
                    raise pool.fail
                return next(
                    (c for pid, c in pool.accounts.items() if pid not in avoid), pool.accounts[1]
                )

            async def mark_used(self, persona_id: int) -> None:
                pass

            async def mark_failure(self, persona_id: int) -> None:
                pass

        return _Service


def _wire(monkeypatch, pool: _Pool) -> tuple[list[int], asyncio.Event, Any]:
    """接上假的号池、Gateway client 和 Blaze 登录；返回 (Gateway 用到的号, 放行 Gateway 的事件, 请求)"""
    from app.services.bf1 import gateway_factory

    used: list[int] = []
    done = asyncio.Event()

    class _Client:
        access_token = "t"
        credentials_rejected = session_rejected = False
        check_login = False
        http_session = None

        def __init__(self, *, pid: int, **kw: Any) -> None:
            used.append(pid)

    async def login_ok(self: Any, c: EACredentials) -> _Socket:
        await asyncio.sleep(0)
        return _Socket()

    monkeypatch.setattr(blaze_service, "EAAccountService", pool.service())
    monkeypatch.setattr(gateway_factory, "EAAccountService", pool.service())
    monkeypatch.setattr(gateway_factory, "BF1GatewayClient", _Client)
    monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_ok)

    async def gateway() -> None:
        # 拿着号直到放行，期间的登记和 Blaze 选号重叠
        async with gateway_factory.get_bf1_client(None):  # type: ignore[arg-type]
            await done.wait()

    return used, done, gateway


@pytest.mark.parametrize("blaze_first", [True, False])
async def test_blaze_and_gateways_picking_together_never_share_an_account(
    monkeypatch, blaze_first: bool
) -> None:
    """第一次挑号查库期间又来了 Blaze 或两个 Gateway 请求：挑号和登记同在一把锁里，最后 Blaze
    用的号没有任何 Gateway 请求拿着，也不用重挑。"""
    pool = _Pool()
    used, done, gateway = _wire(monkeypatch, pool)
    blaze_pool = _BlazeConnectionPool()
    try:
        first = asyncio.create_task(
            blaze_pool.get_socket(None) if blaze_first else gateway()  # type: ignore[arg-type]
        )
        await pool.first_paused.wait()
        others = [
            asyncio.create_task(c)
            for c in (
                (gateway(), gateway()) if blaze_first else (blaze_pool.get_socket(None), gateway())  # type: ignore[arg-type]
            )
        ]
        for _ in range(5):
            await asyncio.sleep(0)
        # 第一次挑号没回来之前，后来的人都在锁外等着，没有人能抢先挑号
        assert len(pool.calls) == 1
        pool.resume_first.set()
        while len(used) < 2 or ea_account_service.blaze_persona() is None:
            await asyncio.sleep(0)
        assert ea_account_service.blaze_persona() not in used
        assert ea_account_service.blaze_persona() not in ea_account_service.gateway_personas()
        assert len(pool.calls) == 3
        done.set()
        await asyncio.gather(first, *others)
        assert ea_account_service.gateway_personas() == set()
    finally:
        ea_account_service.set_blaze_persona(None)


async def test_blaze_pick_failure_or_cancelled_login_leaves_no_registration(monkeypatch) -> None:
    pool = _Pool()
    pool.resume_first.set()
    pool.fail = RuntimeError("db down")
    _wire(monkeypatch, pool)
    blaze_pool = _BlazeConnectionPool()
    try:
        with pytest.raises(RuntimeError):
            await blaze_pool.get_socket(None)  # type: ignore[arg-type]
        assert blaze_pool._creds is None and ea_account_service.blaze_persona() is None

        # 登录途中被取消：同样不留凭据和登记，下次重新挑号
        pool.fail = None
        started = asyncio.Event()

        async def login_hangs(self: Any, c: EACredentials) -> _Socket:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError

        monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_hangs)
        task = asyncio.create_task(blaze_pool.get_socket(None))  # type: ignore[arg-type]
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert blaze_pool._creds is None and ea_account_service.blaze_persona() is None
        calls = len(pool.calls)

        async def login_ok(self: Any, c: EACredentials) -> _Socket:
            return _Socket()

        monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_ok)
        await blaze_pool.get_socket(None)  # type: ignore[arg-type]
        assert len(pool.calls) == calls + 1
    finally:
        ea_account_service.set_blaze_persona(None)


async def test_pool_skips_reserved_account_and_releases_it(monkeypatch) -> None:
    accounts = {
        pid: EACredentials(persona_id=pid, display_name=None, remid="r", sid="s") for pid in (1, 2)
    }
    excluded: list[set[int]] = []

    class _Service:
        def __init__(self, db: Any) -> None:
            pass

        async def pick_available(self, *, avoid: Any = (), exclude: Any = ()) -> EACredentials:
            excluded.append(set(exclude))
            return next(c for pid, c in accounts.items() if pid not in exclude)

    async def login_ok(self: Any, c: EACredentials) -> _Socket:
        return _Socket()

    monkeypatch.setattr(blaze_service, "EAAccountService", _Service)
    monkeypatch.setattr(_BlazeConnectionPool, "_connect_and_login", login_ok)
    pool = _BlazeConnectionPool()
    try:
        await pool.get_socket(None)  # type: ignore[arg-type]
        assert ea_account_service.blaze_persona() == 1
        # 别的号被借走时不受影响
        await pool.release_account(2)
        assert ea_account_service.blaze_persona() == 1
        # 卡行动借走 1 号：立刻断开、放弃粘住的凭据，下次查询换 2 号
        assert ea_account_service.reserve_persona(1)
        assert not ea_account_service.reserve_persona(1)
        await pool.release_account(1)
        assert ea_account_service.blaze_persona() is None
        await pool.get_socket(None)  # type: ignore[arg-type]
        assert ea_account_service.blaze_persona() == 2
        assert excluded[-1] == {1}
    finally:
        ea_account_service.release_persona(1)
        await pool.close_all()
