"""服管执行账号：群服务账号和发起者凭据都没有时，借号池里是这台服管理员的账号"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.errors import EAApiError
from app.domain.games.bf1 import client_provider as cp
from app.services import ea_account_service

GAME_ID = 777
OWNER, ADMIN, OTHER = 11, 22, 33


@pytest.fixture
def env(monkeypatch):
    state: dict[str, Any] = {
        "enabled": [OTHER, ADMIN, OWNER],
        "identity": (OWNER, [ADMIN], 9001, "srv"),
        "identity_calls": 0,
        "opened": [],
        "login_ok": {OWNER: True, ADMIN: True, OTHER: True},
    }

    async def _no_group_accounts(*_a: Any, **_k: Any) -> list[Any]:
        return []

    class _Bindings:
        def __init__(self, db: Any) -> None:
            pass

        async def get_primary_for_user(self, user_id: int) -> None:
            return None

    class _Accounts:
        def __init__(self, db: Any) -> None:
            pass

        async def enabled_personas(self) -> list[int]:
            return list(state["enabled"])

    class _Servers:
        def __init__(self, db: Any) -> None:
            pass

        async def get_admin_identity(self, game_id: int) -> Any:
            state["identity_calls"] += 1
            if isinstance(state["identity"], Exception):
                raise state["identity"]
            return state["identity"]

    @asynccontextmanager
    async def _pool_client(db: Any, persona_id: int):
        state["opened"].append(persona_id)
        token = "t" if state["login_ok"][persona_id] else None
        yield SimpleNamespace(pid=persona_id, access_token=token)

    monkeypatch.setattr(cp.group_server_service, "executor_accounts_for", _no_group_accounts)
    monkeypatch.setattr(cp, "EaBindingService", _Bindings)
    monkeypatch.setattr(cp, "EAAccountService", _Accounts)
    monkeypatch.setattr(cp, "BF1ServerService", _Servers)
    monkeypatch.setattr(cp, "get_bf1_client_for_pool_account", _pool_client)
    cp._admin_ids_cache.clear()
    yield state
    cp._admin_ids_cache.clear()
    ea_account_service.set_blaze_persona(None)
    for pid in (OWNER, ADMIN, OTHER):
        ea_account_service.release_persona(pid)


def _provider() -> cp.GroupFirstBF1ClientProvider:
    user = SimpleNamespace(id=1, ea_bindings=[])
    return cp.GroupFirstBF1ClientProvider(None, user=user, game_id=GAME_ID)  # type: ignore[arg-type]


async def test_uses_pool_account_that_manages_the_server(env) -> None:
    provider = _provider()
    async with provider.acquire() as client:
        # 不是本服管理员的 OTHER 不碰；按号池顺序先用 ADMIN
        assert client.pid == ADMIN
    assert env["opened"] == [ADMIN]
    assert provider.credential_source == "pool_admin"
    assert provider.executor_persona_id == ADMIN


async def test_blaze_account_goes_last_and_login_failure_falls_through(env) -> None:
    ea_account_service.set_blaze_persona(ADMIN)
    env["login_ok"][OWNER] = False
    provider = _provider()
    async with provider.acquire() as client:
        assert client.pid == ADMIN
    # Blaze 在用的 ADMIN 排在后面；OWNER 登录失败才轮到它
    assert env["opened"] == [OWNER, ADMIN]


async def test_reserved_account_is_skipped(env) -> None:
    assert ea_account_service.reserve_persona(ADMIN)
    async with _provider().acquire() as client:
        assert client.pid == OWNER


async def test_no_pool_admin_reports_no_executor(env) -> None:
    env["identity"] = (99, [98], 9001, "srv")
    with pytest.raises(cp.ExecutorUnavailableError):
        async with _provider().acquire():
            pass
    assert env["opened"] == []


async def test_admin_list_is_cached_between_calls(env) -> None:
    for _ in range(3):
        async with _provider().acquire():
            pass
    assert env["identity_calls"] == 1
    assert await cp.pool_admin_personas(None, GAME_ID, fresh=True) == [ADMIN, OWNER]  # type: ignore[arg-type]
    assert env["identity_calls"] == 2


async def test_empty_pool_skips_admin_lookup(env) -> None:
    env["enabled"] = []
    with pytest.raises(cp.ExecutorUnavailableError):
        async with _provider().acquire():
            pass
    assert env["identity_calls"] == 0


async def test_transient_ea_failure_is_reported_as_such(env) -> None:
    env["identity"] = EAApiError(code="EA_SERVER_DETAIL_FAILED", message="超时", retryable=True)
    with pytest.raises(EAApiError) as info:
        async with _provider().acquire():
            pass
    assert info.value.code == "EA_SERVER_DETAIL_FAILED"
    # 暂时性故障不缓存，下次重新查
    assert GAME_ID not in cp._admin_ids_cache
