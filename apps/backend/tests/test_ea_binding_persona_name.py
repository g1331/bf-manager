"""绑定 EA 时取昵称：RSP.getPersonasByIds 把 persona 直接放在 result.<personaId> 下"""

from __future__ import annotations

from typing import Any

import pytest
from app.domain.ea.login.login_engine import LoginCookies
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.gateway_errors import EAGatewayError
from app.services.auth_service import AuthService
from app.services.bf1.gateway_result import persona_info
from app.services.ea_login_finalizer import EALoginFinalizer

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
    # EA 现在对所有人回空头像，空串不当成头像地址
    assert identity.avatar_url is None


async def test_password_login_bind_gets_display_name(fake_gateway):
    client = BF1GatewayClient(pid=0, remid="remid", sid="sid")
    persona_id, name, avatar, *_ = await EALoginFinalizer()._exchange_bf1_session(
        client, LoginCookies(remid="remid", sid="sid", gateway_session_id="g")
    )
    assert (persona_id, name, avatar) == (PID, "SomePlayer", None)
