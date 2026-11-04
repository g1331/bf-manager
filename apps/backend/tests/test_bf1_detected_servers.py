"""按收录的私服名单识别「我的服务器」和卡行动可选的服"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.api.errors import ValidationError
from app.models import EaBinding, Server, ServerMembership, User
from app.schemas.bf1.card import CardCredentials
from app.schemas.bf1.server import ServerExtras, ServerMember, ServerOwner
from app.services.bf1 import card_service, rsp_list_service
from app.services.bf1.card_service import CardService
from app.services.bf1.rsp_list_service import store_lists
from app.services.membership_service import MembershipService
from sqlalchemy import select

ME, POOL_A, POOL_B = 101, 201, 202


def _extras(sid: int, *, owner: int, admins=()) -> ServerExtras:
    return ServerExtras(
        server_id=sid,
        owner=ServerOwner(persona_id=owner, display_name=f"p{owner}"),
        admins=[ServerMember(persona_id=p, display_name=f"p{p}") for p in admins],
    )


@pytest.fixture
async def seeded(test_session, monkeypatch):
    async def _no_snapshot():
        return None

    monkeypatch.setattr(rsp_list_service, "read_server_snapshot", _no_snapshot)
    user = User(username="me", role="user", status="active")
    test_session.add(user)
    await test_session.flush()
    test_session.add(EaBinding(user_id=user.id, persona_id=ME, display_name="me", is_primary=True))
    # 1：我是服主、号池 A 是管理员；2：号池 B 是管理员，我没身份；3：我是管理员
    await store_lists(test_session, 1, 1001, "一服", _extras(1, owner=ME, admins=[POOL_A]))
    await store_lists(test_session, 2, 1002, "二服", _extras(2, owner=9, admins=[POOL_B]))
    await store_lists(test_session, 3, 1003, "三服", _extras(3, owner=9, admins=[ME]))
    await test_session.commit()
    return user


async def test_my_servers_include_detected(test_session, seeded) -> None:
    items = await MembershipService(test_session).list_mine(user_id=seeded.id, game="bf1")
    assert sorted((i.server_id, i.game_id, i.role) for i in items) == [
        (1, 1001, "owner"),
        (3, 1003, "admin"),
    ]
    # 建了档，列表项有 server_pk
    pks = set(await test_session.scalars(select(Server.id).where(Server.server_id.in_([1, 3]))))
    assert {i.server_pk for i in items} == pks

    # 已识别落库的不重复列
    test_session.add(ServerMembership(user_id=seeded.id, server_pk=min(pks), role="owner"))
    await test_session.commit()
    items = await MembershipService(test_session).list_mine(user_id=seeded.id, game="bf1")
    assert len(items) == 2


async def test_card_servers_for_pool_filters_by_site_role(
    test_session, seeded, monkeypatch
) -> None:
    class _Accounts:
        def __init__(self, db: Any) -> None:
            pass

        async def enabled_personas(self) -> list[int]:
            return [POOL_A, POOL_B]

    monkeypatch.setattr(card_service, "EAAccountService", _Accounts)
    user = await test_session.scalar(select(User).where(User.id == seeded.id))
    await test_session.refresh(user, ["ea_bindings"])
    req = CardCredentials(use_pool=True)

    got = await CardService(test_session).account_servers(req, user)
    # 号池能管一服、二服；我只在一服有身份
    assert [(s.server_id, s.persona_id, s.role) for s in got.servers] == [(1, POOL_A, "admin")]
    assert got.persona_id is None and got.tracked_servers == 3

    # 人工授予二服管理员后也列出来
    server = Server(game="bf1", server_id=2, game_id=1002, name="二服")
    test_session.add(server)
    await test_session.flush()
    test_session.add(ServerMembership(user_id=user.id, server_pk=server.id, role="admin"))
    await test_session.commit()
    got = await CardService(test_session).account_servers(req, user)
    assert [s.server_id for s in got.servers] == [1, 2]

    # 平台管理员不限
    admin = SimpleNamespace(role="admin", id=999)
    got = await CardService(test_session).account_servers(req, admin)  # type: ignore[arg-type]
    assert [s.server_id for s in got.servers] == [1, 2]

    with pytest.raises(ValidationError, match="登录后"):
        await CardService(test_session).account_servers(req, None)


async def test_card_servers_for_manual_credentials_logs_in(
    test_session, seeded, monkeypatch
) -> None:
    async def _login(creds):
        return SimpleNamespace(pid=ME, check_login=True, http_session=None)

    monkeypatch.setattr(card_service, "_login", _login)
    got = await CardService(test_session).account_servers(CardCredentials(remid="r", sid="s"), None)
    assert got.persona_id == ME
    assert [(s.server_id, s.role) for s in got.servers] == [(1, "owner"), (3, "admin")]
