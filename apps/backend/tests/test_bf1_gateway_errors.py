"""gateway 失败返回值：仍是 str（兼容老调用方），另带错误种类和 EA 原始错误"""

from __future__ import annotations

import copy
import pickle
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.gateway_errors import ALREADY_VIP, EAGatewayError


def test_error_behaves_like_its_text() -> None:
    err = EAGatewayError("网络超时!", kind="network")
    assert isinstance(err, str)
    assert not isinstance(err, dict)
    assert err == "网络超时!"
    assert f"EA 查询失败: {err}" == "EA 查询失败: 网络超时!"
    assert err.kind == "network"
    assert err.code is None


@pytest.mark.parametrize(
    "clone", [copy.copy, copy.deepcopy, lambda e: pickle.loads(pickle.dumps(e))]
)
def test_error_survives_copy_and_pickle(clone: Any) -> None:
    err = EAGatewayError("玩家已经是VIP了", kind="ea", code=-32603, ea_message=ALREADY_VIP)
    again = clone(err)
    assert again == err
    assert (again.kind, again.code, again.ea_message) == ("ea", -32603, ALREADY_VIP)


def _client() -> BF1GatewayClient:
    client = BF1GatewayClient(pid=7)
    client.check_login = True
    return client


async def test_known_ea_message_keeps_original_text_and_message() -> None:
    res = await _client().error_handle({"error": {"code": -32603, "message": ALREADY_VIP}})
    assert isinstance(res, EAGatewayError)
    assert res == "玩家已经是VIP了"
    assert (res.kind, res.code, res.ea_message) == ("ea", -32603, ALREADY_VIP)


async def test_known_ea_code() -> None:
    res = await _client().error_handle({"error": {"code": -32856, "message": None}})
    assert isinstance(res, EAGatewayError)
    assert res == "玩家不存在"
    assert (res.kind, res.code, res.ea_message) == ("ea", -32856, None)


async def test_unknown_ea_error() -> None:
    res = await _client().error_handle({"error": {"code": -1, "message": "Weird()"}})
    assert isinstance(res, EAGatewayError)
    assert res == "Weird()"
    assert (res.code, res.ea_message) == (-1, "Weird()")


async def test_success_passes_through() -> None:
    data = {"result": {"ok": True}}
    assert await _client().error_handle(data) is data


def _session_raising(exc: BaseException) -> Any:
    @asynccontextmanager
    async def _post(**kwargs: Any):  # type: ignore[no-untyped-def]
        raise exc
        yield  # pragma: no cover

    return SimpleNamespace(post=_post)


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (TimeoutError(), "network"),
        (aiohttp.ClientConnectionError("down"), "network"),
        (ValueError("bug"), "internal"),
    ],
)
async def test_post_jsonrpc_classifies_failures(
    exc: BaseException, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client()

    async def _header() -> dict[str, str]:
        return {}

    monkeypatch.setattr(client, "get_api_header", _header)
    client.http_session = _session_raising(exc)
    res = await client._post_jsonrpc({"method": "X"})
    assert isinstance(res, EAGatewayError)
    assert res.kind == kind


SESSION_INVALID = {"error": {"code": -32501, "message": "Invalid Params: no valid session"}}


async def test_replay_still_invalid_marks_session_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次 -32501 → 重登成功 → 重放仍 -32501：记为被拒，并让登录态失效"""
    client = BF1GatewayClient(pid=7, remid="r", sid="s")
    client.check_login = True
    posts: list[str] = []
    logins: list[str] = []

    async def _post(body: dict[str, Any]) -> dict[str, Any]:
        posts.append(body["method"])
        return SESSION_INVALID

    async def _login(remid: str, sid: str) -> str:
        logins.append(remid)
        client.check_login = True
        client.session_rejected = False
        return "session"

    monkeypatch.setattr(client, "_post_jsonrpc", _post)
    monkeypatch.setattr(client, "login", _login)
    res = await client.api_call({"method": "X"})
    assert isinstance(res, EAGatewayError)
    assert res.code == -32501
    assert posts == ["X", "X"]
    assert logins == ["r"]  # 只在 api_call 里重登一次，error_handle 不再重登
    assert client.session_rejected is True
    assert client.check_login is False


async def test_replay_success_is_not_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BF1GatewayClient(pid=7, remid="r", sid="s")
    client.check_login = True
    responses = [SESSION_INVALID, {"result": {"ok": True}}]

    async def _post(body: dict[str, Any]) -> dict[str, Any]:
        return responses.pop(0)

    async def _login(remid: str, sid: str) -> str:
        client.check_login = True
        return "session"

    monkeypatch.setattr(client, "_post_jsonrpc", _post)
    monkeypatch.setattr(client, "login", _login)
    assert await client.api_call({"method": "X"}) == {"result": {"ok": True}}
    assert client.session_rejected is False


class _Resp:
    def __init__(self, text: str, headers: dict[str, str] | None = None) -> None:
        self._text = text
        self.headers = headers or {}

    async def text(self) -> str:
        return self._text


async def test_login_required_marks_credentials_rejected() -> None:
    client = BF1GatewayClient(pid=7)

    async def _get(**kwargs: Any) -> _Resp:
        return _Resp('{"error":"login_required"}')

    client.http_session = SimpleNamespace(get=_get)
    await client.login("r", "s")
    assert client.credentials_rejected is True


async def test_authcode_failure_is_not_a_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """拿到 access_token 后 authcode 一步失败：没建起 gateway 会话，但不算 EA 拒绝了账号"""
    client = BF1GatewayClient(pid=7)

    async def _get(**kwargs: Any) -> _Resp:
        return _Resp('{"access_token":"t","expires_in":3600}', {"Set-Cookie": "sid=new; Path=/"})

    class _NoNetwork:
        def __init__(self, **kwargs: Any) -> None:
            raise ConnectionError("network disabled in unit test")

    client.http_session = SimpleNamespace(get=_get)
    monkeypatch.setattr("app.domain.games.bf1.gateway.httpx.AsyncClient", _NoNetwork)
    assert await client.login("r", "s") is None
    assert client.check_login is False
    assert client.credentials_rejected is False
    assert client.session_rejected is False
