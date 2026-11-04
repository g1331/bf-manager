"""绑定 EA 时取昵称、EA 账号 ID 和头像。

RSP.getPersonasByIds 把 persona 直接放在 result.<personaId> 下，头像恒为空；头像改按 EA 账号 ID
走 SAL 的 playerByPd 查。
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from app.api.errors import EAApiError
from app.domain.ea.login.login_engine import LoginCookies
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.gateway_errors import EAGatewayError
from app.models import EaBinding, User
from app.services import ea_avatar, ea_login_finalizer
from app.services.auth_service import AuthService
from app.services.bf1.gateway_result import persona_info
from app.services.ea_login_finalizer import EALoginFinalizer
from sqlalchemy import select

PID = 1004198901469

# EA 实际的返回结构（字段与线上一致，值是假的）
EA_PERSONAS = {
    "jsonrpc": "2.0",
    "id": "x",
    "result": {
        str(PID): {
            "platform": "pc",
            "nucleusId": "1008047106256",
            "personaId": str(PID),
            "platformId": "1008047106256",
            "displayName": "SomePlayer",
            "avatar": "",
            "accountId": "0",
        }
    },
}


def test_persona_info_reads_result_keyed_by_persona_id():
    info = persona_info(EA_PERSONAS, PID)
    assert info is not None and info["displayName"] == "SomePlayer"
    assert persona_info(EA_PERSONAS, 1) is None
    assert persona_info(EAGatewayError("x", kind="network"), PID) is None


@pytest.fixture
def fake_gateway(monkeypatch):
    async def login(self: BF1GatewayClient, remid: str, sid: str) -> str:
        self.pid = PID
        self.check_login = True
        self.session = "sess"
        return "sess"

    async def get_personas(self: BF1GatewayClient, ids: list[Any]) -> dict[str, Any]:
        assert [int(i) for i in ids] == [PID]
        return EA_PERSONAS

    monkeypatch.setattr(BF1GatewayClient, "login", login)
    monkeypatch.setattr(BF1GatewayClient, "getPersonasByIds", get_personas)


async def test_cookie_bind_gets_display_name(test_session, fake_gateway):
    identity = await AuthService(test_session).verify_ea_cookie("remid", "sid")
    assert identity.persona_id == PID
    assert identity.display_name == "SomePlayer"
    assert identity.ea_user_id == 1008047106256
    # EA 现在对所有人回空头像，空串不当成头像地址
    assert identity.avatar_url is None


async def test_password_login_bind_gets_display_name(fake_gateway):
    client = BF1GatewayClient(pid=0, remid="remid", sid="sid")
    persona_id, name, avatar, *_, ea_user_id = await EALoginFinalizer()._exchange_bf1_session(
        client, LoginCookies(remid="remid", sid="sid", gateway_session_id="g")
    )
    assert (persona_id, name, avatar, ea_user_id) == (PID, "SomePlayer", None, 1008047106256)


AVATAR = "https://eaavatarservice.akamaized.net/production/avatar/prod/userAvatar/1/208x208.PNG"


async def test_player_by_pd_parses_sal(monkeypatch):
    sent: list[dict[str, Any]] = []

    async def sal(self, payload, *, op, action):
        sent.append(payload)
        return {
            "data": {
                "playerByPd": {
                    "pd": "1008047106256",
                    "psd": str(PID),
                    "displayName": "SomePlayer",
                    "avatar": {"medium": {"path": AVATAR}},
                }
            }
        }

    monkeypatch.setattr(BF1GatewayClient, "_sal_post", sal)
    res = await BF1GatewayClient(pid=0).getPlayerByPd(1008047106256)
    assert res == {
        "pd": 1008047106256,
        "personaId": PID,
        "displayName": "SomePlayer",
        "avatar": AVATAR,
    }
    assert "playerByPd(pd: 1008047106256)" in sent[0]["query"]


async def test_player_by_pd_graphql_error_is_failure(monkeypatch):
    async def sal(self, payload, *, op, action):
        return {"data": {"playerByPd": None}, "errors": [{"message": "not found"}]}

    monkeypatch.setattr(BF1GatewayClient, "_sal_post", sal)
    res = await BF1GatewayClient(pid=0).getPlayerByPd(1)
    assert isinstance(res, EAGatewayError) and res.kind == "ea"


class _FakeClient:
    def __init__(self, res: Any) -> None:
        self.res = res
        self.asked: list[int] = []

    async def getPlayerByPd(self, pd: int) -> Any:  # noqa: N802 - 仿 gateway 方法名
        self.asked.append(pd)
        return self.res


def _pool(monkeypatch, client: _FakeClient) -> None:
    @contextlib.asynccontextmanager
    async def get_client(_db):
        yield client

    monkeypatch.setattr(ea_avatar, "get_bf1_client", get_client)


async def test_fetch_ea_avatar(monkeypatch):
    client = _FakeClient({"pd": 1, "personaId": PID, "displayName": "x", "avatar": AVATAR})
    _pool(monkeypatch, client)
    assert await ea_avatar.fetch_ea_avatar(None, 1) == AVATAR
    # 没有 EA 账号 ID 就不查
    assert await ea_avatar.fetch_ea_avatar(None, None) is None
    assert client.asked == [1]


async def test_fetch_ea_avatar_failure_does_not_raise(monkeypatch):
    _pool(monkeypatch, _FakeClient(EAGatewayError("x", kind="network")))
    assert await ea_avatar.fetch_ea_avatar(None, 1) is None

    @contextlib.asynccontextmanager
    async def no_pool(_db):
        raise EAApiError(code="EA_NO_ACCOUNT", message="号池没有可用账号")
        yield

    monkeypatch.setattr(ea_avatar, "get_bf1_client", no_pool)
    assert await ea_avatar.fetch_ea_avatar(None, 1) is None


@pytest.mark.parametrize(
    "body",
    [
        [1],
        {"data": [1], "errors": None},
        {"data": {"playerByPd": "x"}},
        {"data": {"playerByPd": {"pd": "1", "psd": "2", "avatar": {"medium": "unexpected"}}}},
        {"data": {"playerByPd": {"pd": "1", "psd": "not-a-number", "avatar": None}}},
        {"data": {"playerByPd": {"pd": "1", "psd": "2", "avatar": {"medium": {"path": 3}}}}},
    ],
)
async def test_player_by_pd_malformed_is_bad_response(monkeypatch, body):
    async def sal(self, payload, *, op, action):
        return body

    monkeypatch.setattr(BF1GatewayClient, "_sal_post", sal)
    res = await BF1GatewayClient(pid=0).getPlayerByPd(1)
    assert isinstance(res, EAGatewayError) and res.kind == "bad_response"


async def test_player_by_pd_null_is_not_found(monkeypatch):
    async def sal(self, payload, *, op, action):
        return {"data": {"playerByPd": None}}

    monkeypatch.setattr(BF1GatewayClient, "_sal_post", sal)
    res = await BF1GatewayClient(pid=0).getPlayerByPd(1)
    assert isinstance(res, EAGatewayError) and res.kind == "ea"


async def test_password_bind_task_returns_stored_avatar(test_session, monkeypatch):
    """EA 不回头像时补查到的头像既存进绑定，也出现在登录任务的结果里"""
    user = User(id=7, username="u7", role="user", status="pending_binding")
    test_session.add(user)
    await test_session.commit()

    async def exchange(self, client, cookies):
        return (PID, "SomePlayer", None, "sess", "remid", "sid", None, 1008047106256)

    asked: list[int | None] = []

    async def fake_avatar(_db, ea_user_id):
        asked.append(ea_user_id)
        return AVATAR

    monkeypatch.setattr(EALoginFinalizer, "_exchange_bf1_session", exchange)
    monkeypatch.setattr(ea_login_finalizer, "fetch_ea_avatar", fake_avatar)
    result = await EALoginFinalizer()._run(
        test_session, "user", 7, LoginCookies(remid="r", sid="s", gateway_session_id="g"), None
    )
    assert result.avatar_url == AVATAR
    binding = await test_session.scalar(select(EaBinding).where(EaBinding.persona_id == PID))
    assert (binding.avatar_url, binding.ea_user_id) == (AVATAR, 1008047106256)
    assert asked == [1008047106256]
