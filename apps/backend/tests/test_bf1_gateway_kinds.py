"""gateway 失败按种类处理：分类属性、HTTP 状态码映射，以及几处据此改变行为的调用方"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from app.api.errors import EAApiError, EARejectedError, NotFoundError, ValidationError
from app.domain.games.bf1 import client_provider as provider_module
from app.domain.games.bf1.client_provider import (
    ExecutorUnavailableError,
    GroupFirstBF1ClientProvider,
)
from app.domain.games.bf1.gateway_errors import (
    ALREADY_VIP,
    EAGatewayError,
    gateway_failure,
    is_already_vip,
)
from app.models.bf1 import Bf1AutoSwitch
from app.services.bf1 import auto_switch_engine as engine
from app.services.bf1 import auto_switch_service
from app.services.bf1 import server_service as server_service_module
from app.services.bf1.gateway_result import expect_ok
from app.services.bf1.server_admin_service import BF1ServerAdminService
from app.services.bf1.server_service import BF1ServerService
from sqlalchemy import select

NO_PERMISSION = "Internal Error: org.apache.thrift.TApplicationException"


def _ea(text: str, code: int | None = -32603, message: str | None = None) -> EAGatewayError:
    return EAGatewayError(text, kind="ea", code=code, ea_message=message)


# ----------------------------------------------------------------------------- 分类


@pytest.mark.parametrize(
    ("err", "retryable", "rejected"),
    [
        (EAGatewayError("网络超时!", kind="network"), True, False),
        (EAGatewayError("EA API返回格式错误", kind="bad_response"), True, False),
        (EAGatewayError("EA Desktop token 已失效", kind="auth"), True, False),
        (EAGatewayError("EA API请求时发生未知错误", kind="internal"), False, False),
        (_ea("连接超时", code=-32504), True, False),
        (_ea("Session无效", code=-32501), True, False),
        (
            _ea(
                "EA服务器超时",
                message="Internal Error: se.dice.operations.commons.rx.time.TimeoutNamedException",
            ),
            True,
            False,
        ),
        (_ea("玩家不存在", code=-32856), False, True),
        (_ea("无法处置管理员", code=-32857), False, True),
        (_ea("玩家已经是VIP了", message=ALREADY_VIP), False, True),
        (_ea("服务器BAN位已满", message="RspErrServerBanMax()"), False, True),
        (_ea("账号无权限", message=NO_PERMISSION), False, True),
        (_ea("地图编号无效", message="InvalidLevelIndexException"), False, True),
        # 没列入已知拒绝的 EA 错误：后端内部异常、没见过的错误，不能证明请求本身有问题
        (
            _ea("EA后端未知错误", message="Internal Error: java.lang.NullPointerException"),
            True,
            False,
        ),
        (_ea("Weird()", code=-1, message="Weird()"), True, False),
    ],
)
def test_classification(err: EAGatewayError, retryable: bool, rejected: bool) -> None:
    assert err.retryable is retryable
    assert err.rejected is rejected


def test_ea_unavailable_is_narrower_than_retryable() -> None:
    assert EAGatewayError("网络超时!", kind="network").ea_unavailable
    assert _ea("连接超时", code=-32504).ea_unavailable
    npe = _ea("EA后端未知错误", message="Internal Error: java.lang.NullPointerException")
    assert npe.retryable and not npe.ea_unavailable
    assert not _ea("玩家不存在", code=-32856).ea_unavailable


async def test_ea_backend_exception_from_error_handle_is_retryable_503() -> None:
    """走真实的 error_handle：-32603 + NullPointerException 不能变成 422"""
    from app.domain.games.bf1.gateway import BF1GatewayClient

    client = BF1GatewayClient(pid=7)
    client.check_login = True
    res = await client.error_handle(
        {"error": {"code": -32603, "message": "Internal Error: java.lang.NullPointerException"}}
    )
    await client.http_session.close()
    with pytest.raises(EAApiError) as info:
        expect_ok(res, code="X")
    assert not isinstance(info.value, EARejectedError)
    assert info.value.status_code == 503 and info.value.retryable is True


def test_not_found_and_no_permission() -> None:
    assert _ea("找不到服务器", code=-34501).not_found
    assert _ea("战队不存在", code=-35150).not_found
    assert not _ea("无法处置管理员", code=-32857).not_found
    assert _ea("账号无权限", message=NO_PERMISSION).no_permission
    assert _ea("无权限", code=-35160).no_permission
    assert not EAGatewayError("网络超时!", kind="network").no_permission


def test_gateway_failure_shapes() -> None:
    assert gateway_failure({"result": None}) is None
    err = EAGatewayError("网络超时!", kind="network")
    assert gateway_failure(err) is err
    legacy = gateway_failure("老代码返回的字符串")
    assert legacy is not None and legacy.kind == "internal" and legacy == "老代码返回的字符串"
    odd = gateway_failure(None)
    assert odd is not None and odd.kind == "bad_response"
    assert is_already_vip(_ea("玩家已经是VIP了", message=ALREADY_VIP))
    assert not is_already_vip({"result": "success"})


# ----------------------------------------------------------------------------- HTTP 映射


def test_expect_ok_passes_data_through() -> None:
    data = {"result": {"x": 1}}
    assert expect_ok(data, code="X") is data


def test_rejection_maps_to_422_with_ea_details() -> None:
    with pytest.raises(EARejectedError) as info:
        expect_ok(_ea("玩家不存在", code=-32856), code="EA_KICK_FAILED")
    err = info.value
    assert err.status_code == 422 and err.code == "EA_KICK_FAILED"
    assert err.message == "玩家不存在"
    assert err.details == {"kind": "ea", "ea_code": -32856, "ea_message": None}
    assert isinstance(err, EAApiError) and err.retryable is False


def test_not_found_maps_to_404_only_when_asked() -> None:
    err = _ea("找不到服务器", code=-34501)
    with pytest.raises(NotFoundError):
        expect_ok(err, code="X", not_found="服务器")
    with pytest.raises(EARejectedError):
        expect_ok(err, code="X")


@pytest.mark.parametrize("kind", ["network", "bad_response", "auth"])
def test_transient_maps_to_retryable_503(kind: str) -> None:
    with pytest.raises(EAApiError) as info:
        expect_ok(EAGatewayError("网络超时!", kind=kind), code="X", action="查询服务器详情")  # type: ignore[arg-type]
    err = info.value
    assert err.status_code == 503 and err.retryable is True
    assert err.message == "查询服务器详情失败：网络超时!"


def test_internal_maps_to_non_retryable_503() -> None:
    with pytest.raises(EAApiError) as info:
        expect_ok("老代码返回的字符串", code="X")
    assert info.value.status_code == 503 and info.value.retryable is False


# ----------------------------------------------------------------------------- 服管


class _Provider:
    def __init__(self, client: Any) -> None:
        self.client = client

    @asynccontextmanager
    async def acquire(self):
        yield self.client


class _KickClient:
    def __init__(self, res: Any) -> None:
        self.res = res
        self.calls = 0

    async def kickPlayer(self, gameId, personaId, reason):  # noqa: N802, N803
        self.calls += 1
        return self.res


async def test_admin_rejection_is_422_and_audited(admin_client, test_session) -> None:
    from app.models import AuditLog

    _, admin = admin_client
    client = _KickClient(_ea("无法处置管理员", code=-32857))
    service = BF1ServerAdminService(
        test_session, user=admin, game_id=123, client_provider=_Provider(client)
    )
    with pytest.raises(EARejectedError) as info:
        await service.kick_player(999, "afk")
    assert info.value.status_code == 422
    log = await test_session.scalar(select(AuditLog).where(AuditLog.action == "kick_player"))
    assert log is not None and log.result == "failure" and log.error_code == "EA_KICK_FAILED"


async def test_kick_reason_over_32_bytes_is_rejected_before_ea(admin_client, test_session) -> None:
    _, admin = admin_client
    client = _KickClient({"result": "ok"})
    service = BF1ServerAdminService(
        test_session, user=admin, game_id=123, client_provider=_Provider(client)
    )
    with pytest.raises(ValidationError):
        await service.kick_player(999, "违" * 11)  # 33 字节
    assert client.calls == 0
    assert await service.kick_player(999, "违" * 10) == {"result": "ok"}


# ----------------------------------------------------------------------------- 服务器扩展信息


class _DetailClient:
    def __init__(self, res: Any) -> None:
        self.res = res

    async def getFullServerDetails(self, gameId):  # noqa: N802, N803
        return self.res


def _patch_pool(monkeypatch, client: Any) -> None:
    @asynccontextmanager
    async def fake(db):
        yield client

    monkeypatch.setattr(server_service_module, "get_bf1_client", fake)


async def test_get_extras_raises_on_transient_error(test_session, monkeypatch) -> None:
    """暂时性故障要抛出来：调用方会把 None 当成「这台服没有名单」缓存下来"""
    _patch_pool(monkeypatch, _DetailClient(EAGatewayError("网络超时!", kind="network")))
    with pytest.raises(EAApiError) as info:
        await BF1ServerService(test_session).get_extras(1)
    assert info.value.retryable is True


async def test_get_extras_returns_none_when_ea_rejects(test_session, monkeypatch) -> None:
    _patch_pool(monkeypatch, _DetailClient(_ea("找不到服务器", code=-34501)))
    assert await BF1ServerService(test_session).get_extras(1) is None


# ----------------------------------------------------------------------------- 执行账号探测


async def test_probe_failure_reports_ea_unavailable_not_missing_admin(
    admin_client, test_session, monkeypatch
) -> None:
    """服务账号探测时 EA 超时：分不清是不是管理员，不能报「没有能执行服管操作的账号」"""
    _, admin = admin_client

    class Account:
        persona_id = 77

    class Client:
        access_token = "t"

        async def getFullServerDetails(self, gameId):  # noqa: N802, N803
            return EAGatewayError("网络超时!", kind="network")

    @asynccontextmanager
    async def enter(db, account):
        yield Client()

    async def accounts(db, user, *, game_id, server_pk=None):
        return [Account()]

    async def record(*args, **kwargs):
        return None

    monkeypatch.setattr(provider_module, "get_bf1_client_for_group_account", enter)
    monkeypatch.setattr(provider_module.group_server_service, "executor_accounts_for", accounts)
    monkeypatch.setattr(provider_module.group_server_service, "record_account_result", record)

    provider = GroupFirstBF1ClientProvider(test_session, user=admin, game_id=1)
    with pytest.raises(EAApiError) as info:
        async with provider.acquire():
            pass
    assert not isinstance(info.value, ExecutorUnavailableError)
    assert info.value.retryable is True and info.value.code == "EA_EXECUTOR_PROBE_FAILED"

    # 探测明确说不是管理员：照旧报没有可用账号
    async def not_admin(self, gameId):  # noqa: N803
        return {"result": {"rspInfo": None}}

    monkeypatch.setattr(Client, "getFullServerDetails", not_admin)
    with pytest.raises(ExecutorUnavailableError):
        async with provider.acquire():
            pass


# ----------------------------------------------------------------------------- 自动换图


async def _switch_row(db, user_id: int) -> Bf1AutoSwitch:
    row = Bf1AutoSwitch(
        game_id=55,
        enabled=True,
        plan={"items": [], "loops": 1},
        state={},
        events=[],
        enabled_by_user_id=user_id,
    )
    db.add(row)
    await db.commit()
    return row


def _patch_step(monkeypatch, err: EAApiError) -> None:
    async def rotation(db, game_id, *, force=False):
        return ["MP_Amiens", "MP_Scar"]

    async def manual(db, game_id):
        return False

    def decide(plan, rotation, state, obs, now, *, manual_recent=False):
        st = {
            **engine.initial_state(),
            "pending": {"target": "MP_Scar", "at": now, "retried": False},
        }
        return engine.Decision(state=st, choose=engine.Choose(1, "MP_Scar"))

    async def choose(db, row, c):
        raise err

    monkeypatch.setattr(auto_switch_service, "_rotation", rotation)
    monkeypatch.setattr(auto_switch_service, "_manual_recent", manual)
    monkeypatch.setattr(auto_switch_service.engine, "decide", decide)
    monkeypatch.setattr(auto_switch_service, "_choose", choose)


INFO = {"map": "MP_Amiens", "progress": "0", "state": "running"}


async def test_auto_switch_keeps_running_after_transient_failure(
    admin_client, test_session, monkeypatch
) -> None:
    """EA 暂时不可用：不停，留着待确认状态，确认期过了引擎自己重试一次"""
    _, admin = admin_client
    row = await _switch_row(test_session, admin.id)
    _patch_step(monkeypatch, EAApiError(code="X", message="网络超时!", retryable=True))

    await auto_switch_service._step(test_session, row, INFO)

    assert row.enabled is True
    assert row.state["pending"]["target"] == "MP_Scar"
    assert row.events[0]["kind"] == "retry"


async def test_auto_switch_stops_when_ea_rejects(admin_client, test_session, monkeypatch) -> None:
    _, admin = admin_client
    row = await _switch_row(test_session, admin.id)
    _patch_step(monkeypatch, EARejectedError(code="X", message="账号无权限"))

    await auto_switch_service._step(test_session, row, INFO)

    assert row.enabled is False
    assert row.events[0]["kind"] == "error"


# ----------------------------------------------------------------------------- 注册时邮箱反查


class _SalClient:
    def __init__(self, res: Any) -> None:
        self.res = res

    async def getPersonasByName(self, name):  # noqa: N802
        return self.res


def _patch_email_pool(monkeypatch, res: Any) -> None:
    from app.services import account_service

    @asynccontextmanager
    async def fake(db):
        yield _SalClient(res)

    monkeypatch.setattr(account_service, "get_bf1_client", fake)


async def test_email_lookup_reports_ea_outage(test_session, monkeypatch) -> None:
    """EA 抖动时不能回「不是 EA 账号邮箱」"""
    from app.services.account_service import lookup_ea_by_email

    _patch_email_pool(monkeypatch, EAGatewayError("网络超时!", kind="network"))
    with pytest.raises(EAApiError) as info:
        await lookup_ea_by_email(test_session, "a@example.com")
    assert info.value.retryable is True


async def test_email_lookup_without_match_returns_none(test_session, monkeypatch) -> None:
    from app.services.account_service import lookup_ea_by_email

    _patch_email_pool(monkeypatch, {"personas": []})
    assert await lookup_ea_by_email(test_session, "a@example.com") is None


# ----------------------------------------------------------------------------- EA Desktop 凭据失效


class _OAuthResponse:
    def __init__(self, status: int, headers: dict[str, str], body: str = "") -> None:
        self.status = status
        self.headers = headers
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _OAuthSession:
    def __init__(self, response: _OAuthResponse) -> None:
        self.response = response

    def get(self, **kwargs):
        return self.response


@pytest.mark.parametrize(
    "response",
    [
        _OAuthResponse(302, {"Location": "https://pc.ea.com#error=login_required"}),
        _OAuthResponse(200, {}, '{"error": "login_required", "error_description": "x"}'),
    ],
)
async def test_desktop_login_required_marks_credentials_rejected(response) -> None:
    """经典链路的登录态还缓存着、Desktop 链路被 EA 作废：要记成凭据失效，号池才会累计失败"""
    from app.domain.games.bf1.gateway import BF1GatewayClient

    client = BF1GatewayClient(pid=7, remid="r", sid="s")
    await client.http_session.close()
    client.http_session = _OAuthSession(response)  # type: ignore[assignment]

    res = await client.getPersonasByName("someone")

    assert client.credentials_rejected is True
    with pytest.raises(EAApiError) as info:
        expect_ok(res, code="EA_PERSONA_SEARCH_FAILED")
    assert info.value.retryable is True


async def test_desktop_server_error_is_not_credential_rejection() -> None:
    from app.domain.games.bf1.gateway import BF1GatewayClient

    client = BF1GatewayClient(pid=7, remid="r", sid="s")
    await client.http_session.close()
    client.http_session = _OAuthSession(_OAuthResponse(500, {}, "oops"))  # type: ignore[assignment]

    await client.getPersonasByName("someone")
    assert client.credentials_rejected is False
