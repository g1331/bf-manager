"""EAAccountService 管理端 CRUD 与连通性验证测试"""

from __future__ import annotations

import pytest
from app.api.errors import NotFoundError, ValidationError
from app.core.security import get_cipher
from app.models import EAAccount
from app.schemas.ea_account import EAAccountCreate, EAAccountCredentialsUpdate
from app.services.ea_account_service import EAAccountService
from sqlalchemy import select


async def _seed(
    session,
    *,
    persona_id: int = 1001,
    enabled: bool = True,
    failure_count: int = 0,
    with_session: bool = False,
) -> EAAccount:
    cipher = get_cipher()
    account = EAAccount(
        persona_id=persona_id,
        display_name=f"acc_{persona_id}",
        encrypted_remid=cipher.encrypt("remid-value"),
        encrypted_sid=cipher.encrypt("sid-value"),
        encrypted_session=cipher.encrypt("sess-value") if with_session else None,
        encrypted_access_token=None,
        enabled=enabled,
        failure_count=failure_count,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def _reload(session, account_id: int) -> EAAccount:
    """强制从库重读：会话用了 expire_on_commit=False，直接 scalar 会拿到 identity map
    里未同步的旧实例，先 expire_all 再查才能反映已提交的真实落库值。"""
    session.expire_all()
    account = await session.scalar(select(EAAccount).where(EAAccount.id == account_id))
    assert account is not None
    return account


async def test_create_encrypts_and_hides_plaintext(test_session) -> None:
    service = EAAccountService(test_session)
    item = await service.create(
        EAAccountCreate(persona_id=2002, display_name="new", remid="r-plain", sid="s-plain")
    )
    # 读取模型只暴露健康状态，不含任何明文字段
    assert item.persona_id == 2002
    assert item.has_session is False
    assert item.has_access_token is False
    assert not hasattr(item, "remid")
    # 凭据确实被加密落库，可经 pick_available 解密回原值
    creds = await service.pick_available()
    assert creds.persona_id == 2002
    assert creds.remid == "r-plain"
    assert creds.sid == "s-plain"


async def test_create_rejects_duplicate_persona(test_session) -> None:
    await _seed(test_session, persona_id=1001)
    service = EAAccountService(test_session)
    with pytest.raises(ValidationError):
        await service.create(EAAccountCreate(persona_id=1001, remid="r", sid="s"))


async def test_list_all_returns_health_only(test_session) -> None:
    await _seed(test_session, persona_id=1001, with_session=True)
    await _seed(test_session, persona_id=1002)
    service = EAAccountService(test_session)
    items = await service.list_all()
    assert {i.persona_id for i in items} == {1001, 1002}
    by_pid = {i.persona_id: i for i in items}
    assert by_pid[1001].has_session is True
    assert by_pid[1002].has_session is False


async def test_update_credentials_partial_and_resets_failure(test_session) -> None:
    account = await _seed(test_session, failure_count=5)
    service = EAAccountService(test_session)
    item = await service.update_credentials(
        account.id, EAAccountCredentialsUpdate(sid="s-new", session="sess-new")
    )
    assert item.failure_count == 0
    assert item.has_session is True
    cipher = get_cipher()
    refreshed = await _reload(test_session, account.id)
    # 只更新了 sid 与 session，remid 保持原值
    assert cipher.decrypt(refreshed.encrypted_remid) == "remid-value"
    assert cipher.decrypt(refreshed.encrypted_sid) == "s-new"
    assert cipher.decrypt(refreshed.encrypted_session) == "sess-new"


async def test_set_enabled_reenable_resets_failure(test_session) -> None:
    account = await _seed(test_session, enabled=False, failure_count=10)
    service = EAAccountService(test_session)
    item = await service.set_enabled(account.id, True)
    assert item.enabled is True
    assert item.failure_count == 0


async def test_set_disabled_keeps_failure_count(test_session) -> None:
    account = await _seed(test_session, enabled=True, failure_count=3)
    service = EAAccountService(test_session)
    item = await service.set_enabled(account.id, False)
    assert item.enabled is False
    assert item.failure_count == 3


async def test_delete_removes_account(test_session) -> None:
    account = await _seed(test_session)
    service = EAAccountService(test_session)
    await service.delete(account.id)
    assert await service.list_all() == []


async def test_delete_missing_raises_not_found(test_session) -> None:
    service = EAAccountService(test_session)
    with pytest.raises(NotFoundError):
        await service.delete(9999)


class _FakeGatewayOk:
    def __init__(self, **kwargs) -> None:
        pass

    async def getServersByPersonaIds(self, ids):  # noqa: N802
        return {"result": {str(ids[0]): None}}

    async def _ensure_desktop_token(self) -> str:
        return "fake-access-token"


class _FakeGatewayFail:
    """session 链路就失败：直接返回错误串"""

    def __init__(self, **kwargs) -> None:
        pass

    async def getServersByPersonaIds(self, ids):  # noqa: N802
        return "login_required"

    async def _ensure_desktop_token(self) -> str | None:
        # 不会被走到，但避免后续重构时遗漏；保持 stub 完整
        return None


class _FakeGatewaySessionOnly:
    """session 通过、但 remid/sid 已失效换不出 access_token"""

    def __init__(self, **kwargs) -> None:
        pass

    async def getServersByPersonaIds(self, ids):  # noqa: N802
        return {"result": {str(ids[0]): None}}

    async def _ensure_desktop_token(self) -> str | None:
        return None


async def test_verify_success_marks_used(test_session, monkeypatch) -> None:
    account = await _seed(test_session, failure_count=3)
    monkeypatch.setattr("app.domain.games.bf1.gateway.BF1GatewayClient", _FakeGatewayOk)
    service = EAAccountService(test_session)
    result = await service.verify(account.id)
    assert result.success is True
    assert result.persona_id == account.persona_id
    refreshed = await _reload(test_session, account.id)
    assert refreshed.failure_count == 0
    assert refreshed.last_used_at is not None


async def test_verify_failure_marks_failure(test_session, monkeypatch) -> None:
    account = await _seed(test_session, failure_count=0)
    monkeypatch.setattr("app.domain.games.bf1.gateway.BF1GatewayClient", _FakeGatewayFail)
    service = EAAccountService(test_session)
    result = await service.verify(account.id)
    assert result.success is False
    assert "login_required" in (result.message or "")
    refreshed = await _reload(test_session, account.id)
    assert refreshed.failure_count == 1


async def test_verify_session_ok_but_access_token_fail(test_session, monkeypatch) -> None:
    """session 通而 remid/sid 已失效时 verify 必须判失败，避免「verify 通过、按
    昵称查询 502」的设计盲区。错误消息要明确指向 access_token 链路。"""
    account = await _seed(test_session, failure_count=0)
    monkeypatch.setattr("app.domain.games.bf1.gateway.BF1GatewayClient", _FakeGatewaySessionOnly)
    service = EAAccountService(test_session)
    result = await service.verify(account.id)
    assert result.success is False
    assert "access_token" in (result.message or "")
    refreshed = await _reload(test_session, account.id)
    assert refreshed.failure_count == 1


async def test_upsert_creates_when_absent(test_session) -> None:
    service = EAAccountService(test_session)
    item = await service.upsert(persona_id=3003, display_name="cli", remid="r1", sid="s1")
    assert item.persona_id == 3003
    creds = await service.pick_available()
    assert creds.remid == "r1"
    assert creds.sid == "s1"


async def test_upsert_create_requires_remid_sid(test_session) -> None:
    service = EAAccountService(test_session)
    with pytest.raises(ValidationError):
        await service.upsert(persona_id=3004, remid="only-remid")


async def test_upsert_updates_existing_and_resets_failure(test_session) -> None:
    account = await _seed(test_session, persona_id=3005, failure_count=7)
    service = EAAccountService(test_session)
    item = await service.upsert(persona_id=3005, sid="s-updated", display_name="renamed")
    assert item.failure_count == 0
    assert item.display_name == "renamed"
    cipher = get_cipher()
    refreshed = await _reload(test_session, account.id)
    # 只更新了 sid 与 display_name，remid 保持原值
    assert cipher.decrypt(refreshed.encrypted_remid) == "remid-value"
    assert cipher.decrypt(refreshed.encrypted_sid) == "s-updated"
