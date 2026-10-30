"""群组服务账号与绑服

- 服务账号：群主提交的 EA 凭据（remid + sid，或走 EA 账号密码登录），加密存在 group_ea_accounts。
  群里绑定的服用它执行服管操作，EA 那边看到的操作者就是这个账号。
- 绑服：群主把自己在 EA 上是服主或管理员的服挂到群上，并选一个服务账号执行。两个条件都要满足：
  绑定人本人是这台服的服主或管理员；选的服务账号是这台服的服主或管理员。
- 权限：服挂在群上（status=active）时，群里的人（群主和管理员）在这台服上都有管理员权限，
  和 tenko v3 一样，执行账号能做的，群里的人都能做。bound_via 只记录，不限权。
- 复核：每天一次，另外群主可以手动触发。绑定人不再是服主或管理员时这台服在群里失效；
  服务账号登录失败、不再是管理员时标出问题，并发邮件告诉群主。
- 服主视图：服主能看到挂着自己服的所有群，并能把服从群里移出。
"""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import EAApiError, NotFoundError
from app.core.config import get_settings
from app.core.security import get_cipher
from app.models import (
    EaBinding,
    Group,
    GroupEaAccount,
    GroupMember,
    GroupServer,
    Server,
    User,
)
from app.services.bf1.gateway_factory import get_bf1_client_for_group_account
from app.services.bf1.server_service import BF1ServerService, current_game_ids
from app.services.group_service import GroupError, _audit, _lock_group, require_member
from app.services.mail import templates
from app.services.mail.sender import get_mail_sender

GAME = "bf1"
# 服务账号连续登录失败这么多次标为失效
ACCOUNT_FAILURE_LIMIT = 3
# 一个群最多挂多少个服务账号、多少台服
ACCOUNT_LIMIT_PER_GROUP = 10
SERVER_LIMIT_PER_GROUP = 50
RECHECK_INTERVAL_SECONDS = 24 * 3600
RECHECK_FIRST_DELAY_SECONDS = 10 * 60

PROBLEM_NO_EXECUTOR = "没有指定服务账号"
PROBLEM_EXECUTOR_NOT_ADMIN = "服务账号已不是这台服的服主或管理员"
PROBLEM_EXECUTOR_INVALID = "服务账号登录失败，需要群主重新提交凭据"
REASON_BINDER_LOST = "绑定人已不是这台服的服主或管理员"
REASON_BINDER_GONE = "绑定人的账号已不存在"


def _now() -> datetime:
    return datetime.now(UTC)


# ===== 小工具 =====


async def _display_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    row = (
        await db.execute(
            select(User.username, EaBinding.display_name)
            .outerjoin(
                EaBinding,
                (EaBinding.user_id == User.id)
                & EaBinding.is_primary.is_(True)
                & EaBinding.is_frozen.is_(False),
            )
            .where(User.id == user_id)
        )
    ).first()
    if row is None:
        return None
    return row[1] or row[0]


async def _personas_of(db: AsyncSession, user_id: int) -> set[int]:
    rows = await db.scalars(
        select(EaBinding.persona_id).where(
            EaBinding.user_id == user_id, EaBinding.is_frozen.is_(False)
        )
    )
    return set(rows.all())


@dataclass(frozen=True)
class ServerIdentity:
    owner_pid: int | None
    admin_pids: frozenset[int]
    server_id: int
    name: str | None

    def manages(self, persona_ids: set[int] | int) -> str | None:
        """这些 persona 里有服主就是 owner，有管理员就是 admin，都没有返回 None"""
        pids = {persona_ids} if isinstance(persona_ids, int) else persona_ids
        if self.owner_pid is not None and self.owner_pid in pids:
            return "owner"
        if pids & self.admin_pids:
            return "admin"
        return None


async def fetch_identity(db: AsyncSession, game_id: int) -> ServerIdentity | None:
    """EA 上这台服的服主和管理员名单（走号池查，公开信息）；EA 不可用或不是私服返回 None"""
    try:
        info = await BF1ServerService(db).get_admin_identity(game_id)
    except EAApiError as e:
        logger.info("取服务器 {} 的管理名单失败: {}", game_id, e.message)
        return None
    if info is None:
        return None
    owner_pid, admin_pids, server_id, name = info
    if not server_id:
        return None
    return ServerIdentity(owner_pid, frozenset(admin_pids), int(server_id), name)


async def _upsert_server(db: AsyncSession, game_id: int, identity: ServerIdentity) -> Server:
    server = await db.scalar(
        select(Server).where(Server.game == GAME, Server.server_id == identity.server_id)
    )
    if server is None:
        server = Server(
            game=GAME, server_id=identity.server_id, game_id=game_id, name=identity.name
        )
        db.add(server)
        await db.flush()
    else:
        server.game_id = game_id
        if identity.name:
            server.name = identity.name
    return server


# ===== 服务账号 =====


async def list_accounts(db: AsyncSession, group_id: int, actor: User) -> list[GroupEaAccount]:
    await require_member(db, group_id, actor, "admin")
    rows = await db.scalars(
        select(GroupEaAccount)
        .where(GroupEaAccount.group_id == group_id)
        .order_by(GroupEaAccount.is_default.desc(), GroupEaAccount.id)
    )
    return list(rows.all())


async def _account(db: AsyncSession, group_id: int, account_id: int) -> GroupEaAccount:
    account = await db.get(GroupEaAccount, account_id, populate_existing=True)
    if account is None or account.group_id != group_id:
        raise NotFoundError("服务账号")
    return account


async def save_account(
    db: AsyncSession,
    group_id: int,
    actor: User,
    *,
    persona_id: int,
    display_name: str | None,
    remid: str,
    sid: str,
    session: str | None = None,
    ip: str | None = None,
) -> GroupEaAccount:
    """凭据已经在 EA 上验证过（登录成功、拿到了 persona）。同一个 EA 号再提交就是更新凭据"""
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    cipher = get_cipher()
    account = await db.scalar(
        select(GroupEaAccount).where(
            GroupEaAccount.group_id == group_id, GroupEaAccount.persona_id == persona_id
        )
    )
    existing = list(
        (await db.scalars(select(GroupEaAccount).where(GroupEaAccount.group_id == group_id))).all()
    )
    if account is None:
        if len(existing) >= ACCOUNT_LIMIT_PER_GROUP:
            raise GroupError(
                "GROUP_ACCOUNT_LIMIT", f"一个群最多添加 {ACCOUNT_LIMIT_PER_GROUP} 个服务账号"
            )
        account = GroupEaAccount(
            group_id=group_id,
            persona_id=persona_id,
            created_by=actor.id,
            is_default=not existing,
            encrypted_remid="",
            encrypted_sid="",
        )
        db.add(account)
        action = "group_account_add"
    else:
        action = "group_account_update"
    account.display_name = display_name or account.display_name
    account.encrypted_remid = cipher.encrypt(remid)
    account.encrypted_sid = cipher.encrypt(sid)
    account.encrypted_session = cipher.encrypt(session) if session else None
    account.status = "ok"
    account.failure_count = 0
    account.last_error = None
    account.last_verified_at = _now()
    await db.flush()
    # 凭据换好了，之前因为它登录失败而标出的问题先清掉，下次复核再按 EA 现状判断
    for gs in await db.scalars(
        select(GroupServer).where(
            GroupServer.executor_account_id == account.id,
            GroupServer.executor_problem == PROBLEM_EXECUTOR_INVALID,
        )
    ):
        gs.executor_problem = None
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action=action,
        payload={"persona_id": persona_id, "display_name": account.display_name},
        ip=ip,
    )
    await db.commit()
    return account


async def set_default_account(
    db: AsyncSession, group_id: int, account_id: int, actor: User, ip: str | None = None
) -> None:
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    target = await _account(db, group_id, account_id)
    for account in await db.scalars(
        select(GroupEaAccount).where(GroupEaAccount.group_id == group_id)
    ):
        account.is_default = account.id == target.id
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_account_default",
        payload={"persona_id": target.persona_id, "display_name": target.display_name},
        ip=ip,
    )
    await db.commit()


async def remove_account(
    db: AsyncSession, group_id: int, account_id: int, actor: User, ip: str | None = None
) -> None:
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    account = await _account(db, group_id, account_id)
    for gs in await db.scalars(
        select(GroupServer).where(GroupServer.executor_account_id == account.id)
    ):
        gs.executor_account_id = None
        gs.executor_problem = PROBLEM_NO_EXECUTOR
    if account.is_default:
        nxt = await db.scalar(
            select(GroupEaAccount)
            .where(GroupEaAccount.group_id == group_id, GroupEaAccount.id != account.id)
            .order_by(GroupEaAccount.id)
        )
        if nxt is not None:
            nxt.is_default = True
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_account_remove",
        payload={"persona_id": account.persona_id, "display_name": account.display_name},
        ip=ip,
    )
    await db.delete(account)
    await db.commit()


# ===== 绑服 =====


@dataclass(frozen=True)
class GroupServerView:
    row: GroupServer
    server: Server
    bound_by_name: str | None
    executor: GroupEaAccount | None


async def _views(db: AsyncSession, rows: list[tuple[GroupServer, Server]]) -> list[GroupServerView]:
    account_ids = {gs.executor_account_id for gs, _ in rows if gs.executor_account_id}
    accounts = (
        {
            a.id: a
            for a in await db.scalars(
                select(GroupEaAccount).where(GroupEaAccount.id.in_(account_ids))
            )
        }
        if account_ids
        else {}
    )
    out = []
    for gs, server in rows:
        out.append(
            GroupServerView(
                row=gs,
                server=server,
                bound_by_name=await _display_name(db, gs.bound_by_user_id),
                executor=accounts.get(gs.executor_account_id or 0),
            )
        )
    return out


async def list_servers(db: AsyncSession, group_id: int, actor: User) -> list[GroupServerView]:
    await require_member(db, group_id, actor, "admin")
    rows = (
        await db.execute(
            select(GroupServer, Server)
            .join(Server, Server.id == GroupServer.server_pk)
            .where(GroupServer.group_id == group_id)
            .order_by(GroupServer.created_at, GroupServer.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    return await _views(db, [(gs, s) for gs, s in rows])


async def _pick_executor(
    db: AsyncSession, group_id: int, account_id: int | None, identity: ServerIdentity
) -> GroupEaAccount:
    """选执行账号：指定了就校验它；没指定按默认账号优先，挑第一个是这台服服主或管理员的"""
    if account_id is not None:
        account = await _account(db, group_id, account_id)
        if identity.manages(account.persona_id) is None:
            raise GroupError(
                "GROUP_EXECUTOR_NOT_ADMIN",
                f"服务账号 {account.display_name or account.persona_id} 不是这台服的服主或管理员，"
                "先在游戏里把它加成管理员",
            )
        return account
    accounts = await db.scalars(
        select(GroupEaAccount)
        .where(GroupEaAccount.group_id == group_id)
        .order_by(GroupEaAccount.is_default.desc(), GroupEaAccount.id)
    )
    candidates = list(accounts.all())
    if not candidates:
        raise GroupError("GROUP_NO_ACCOUNT", "群里还没有服务账号，先添加一个")
    for account in candidates:
        if identity.manages(account.persona_id) is not None:
            return account
    raise GroupError(
        "GROUP_EXECUTOR_NOT_ADMIN",
        "群里的服务账号都不是这台服的服主或管理员，先在游戏里把其中一个加成管理员",
    )


async def bind_server(
    db: AsyncSession,
    group_id: int,
    actor: User,
    *,
    game_id: int,
    account_id: int | None = None,
    ip: str | None = None,
) -> GroupServerView:
    await require_member(db, group_id, actor, "owner")
    # 先查 EA（慢、走号池），再锁群写库
    identity = await fetch_identity(db, game_id)
    if identity is None:
        raise GroupError(
            "GROUP_SERVER_UNAVAILABLE", "查不到这台服的管理名单：服务器不在线，或者不是私服", 409
        )
    via = identity.manages(await _personas_of(db, actor.id))
    if via is None:
        raise GroupError(
            "GROUP_SERVER_NOT_YOURS",
            "你绑定的 EA 账号不是这台服的服主或管理员，不能把它挂到群上",
            403,
        )
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    executor = await _pick_executor(db, group_id, account_id, identity)
    server = await _upsert_server(db, game_id, identity)
    gs = await db.scalar(
        select(GroupServer).where(
            GroupServer.group_id == group_id, GroupServer.server_pk == server.id
        )
    )
    if gs is None:
        count = len(
            (await db.scalars(select(GroupServer.id).where(GroupServer.group_id == group_id))).all()
        )
        if count >= SERVER_LIMIT_PER_GROUP:
            raise GroupError("GROUP_SERVER_LIMIT", f"一个群最多挂 {SERVER_LIMIT_PER_GROUP} 台服")
        gs = GroupServer(group_id=group_id, server_pk=server.id, bound_via=via)
        db.add(gs)
        action = "group_server_bind"
    else:
        action = "group_server_rebind"
    gs.bound_by_user_id = actor.id
    gs.bound_via = via
    gs.executor_account_id = executor.id
    gs.status = "active"
    gs.status_reason = None
    gs.executor_problem = None
    gs.last_verified_at = _now()
    await db.flush()
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action=action,
        payload={
            "server_id": server.server_id,
            "game_id": game_id,
            "server_name": server.name,
            "bound_via": via,
            "executor_persona_id": executor.persona_id,
        },
        ip=ip,
    )
    await db.commit()
    return (await _views(db, [(gs, server)]))[0]


async def _group_server(db: AsyncSession, group_id: int, gs_id: int) -> tuple[GroupServer, Server]:
    row = (
        await db.execute(
            select(GroupServer, Server)
            .join(Server, Server.id == GroupServer.server_pk)
            .where(GroupServer.id == gs_id, GroupServer.group_id == group_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None:
        raise NotFoundError("服务器")
    return row[0], row[1]


async def set_server_executor(
    db: AsyncSession,
    group_id: int,
    gs_id: int,
    account_id: int,
    actor: User,
    ip: str | None = None,
) -> GroupServerView:
    await require_member(db, group_id, actor, "owner")
    gs, server = await _group_server(db, group_id, gs_id)
    if not server.game_id:
        raise GroupError("GROUP_SERVER_UNAVAILABLE", "这台服还没有在线记录，稍后再试", 409)
    identity = await fetch_identity(db, server.game_id)
    if identity is None:
        raise GroupError(
            "GROUP_SERVER_UNAVAILABLE", "查不到这台服的管理名单：服务器可能不在线，稍后再试", 409
        )
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    gs, server = await _group_server(db, group_id, gs_id)
    executor = await _pick_executor(db, group_id, account_id, identity)
    gs.executor_account_id = executor.id
    gs.executor_problem = None
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_server_executor",
        payload={
            "server_id": server.server_id,
            "server_name": server.name,
            "executor_persona_id": executor.persona_id,
            "executor_name": executor.display_name,
        },
        ip=ip,
    )
    await db.commit()
    return (await _views(db, [(gs, server)]))[0]


async def unbind_server(
    db: AsyncSession, group_id: int, gs_id: int, actor: User, ip: str | None = None
) -> None:
    await _lock_group(db, group_id)
    await require_member(db, group_id, actor, "owner")
    gs, server = await _group_server(db, group_id, gs_id)
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_server_unbind",
        payload={"server_id": server.server_id, "server_name": server.name},
        ip=ip,
    )
    await db.delete(gs)
    await db.commit()


# ===== 服主视图 =====


@dataclass(frozen=True)
class ServerGroupView:
    group_id: int
    group_name: str
    bound_by_name: str | None
    bound_via: str
    status: str
    created_at: datetime


async def _server_for_game(db: AsyncSession, game_id: int) -> Server | None:
    return await db.scalar(
        select(Server)
        .where(Server.game == GAME, Server.game_id == game_id)
        .order_by(Server.updated_at.desc())
    )


async def list_groups_for_server(db: AsyncSession, game_id: int) -> list[ServerGroupView]:
    """调用方已确认是这台服的服主（或平台管理员）"""
    server = await _server_for_game(db, game_id)
    if server is None:
        return []
    rows = (
        await db.execute(
            select(GroupServer, Group)
            .join(Group, Group.id == GroupServer.group_id)
            .where(GroupServer.server_pk == server.id)
            .order_by(GroupServer.created_at)
        )
    ).all()
    return [
        ServerGroupView(
            group_id=group.id,
            group_name=group.name,
            bound_by_name=await _display_name(db, gs.bound_by_user_id),
            bound_via=gs.bound_via,
            status=gs.status,
            created_at=gs.created_at,
        )
        for gs, group in rows
    ]


async def remove_group_from_server(
    db: AsyncSession, game_id: int, group_id: int, actor: User, ip: str | None = None
) -> None:
    """服主把自己的服从某个群里移出。调用方已确认是这台服的服主（或平台管理员）"""
    server = await _server_for_game(db, game_id)
    if server is None:
        raise NotFoundError("绑定")
    await _lock_group(db, group_id)
    gs = await db.scalar(
        select(GroupServer).where(
            GroupServer.group_id == group_id, GroupServer.server_pk == server.id
        )
    )
    if gs is None:
        raise NotFoundError("绑定")
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_server_removed_by_owner",
        payload={"server_id": server.server_id, "server_name": server.name},
        ip=ip,
    )
    await db.delete(gs)
    await db.commit()


# ===== 权限与执行账号 =====


def _counts_for_groups(user: User) -> bool:
    """还没绑 EA（或主绑定解绑了）的账号，群成员身份保留，但不参与权限计算"""
    return user.role == "admin" or getattr(user, "status", "active") == "active"


async def group_role_for_server(db: AsyncSession, user: User, server_pk: int) -> str | None:
    """用户经由群组在这台服上的角色：挂着这台服的群里有他就是 admin"""
    if not _counts_for_groups(user):
        return None
    hit = await db.scalar(
        select(GroupServer.id)
        .join(GroupMember, GroupMember.group_id == GroupServer.group_id)
        .where(
            GroupServer.server_pk == server_pk,
            GroupServer.status == "active",
            GroupMember.user_id == user.id,
        )
        .limit(1)
    )
    return "admin" if hit is not None else None


async def executor_accounts_for(
    db: AsyncSession, user: User, *, game_id: int, server_pk: int | None = None
) -> list[GroupEaAccount]:
    """用户能借用的服务账号：他所在、且挂着这台服的群给这台服指定的执行账号。正常的排前面"""
    if not _counts_for_groups(user):
        return []
    if server_pk is not None:
        server_pks = [server_pk]
    else:
        server_pks = list(
            (
                await db.scalars(
                    select(Server.id).where(Server.game == GAME, Server.game_id == game_id)
                )
            ).all()
        )
    if not server_pks:
        return []
    rows = await db.scalars(
        select(GroupEaAccount)
        .join(GroupServer, GroupServer.executor_account_id == GroupEaAccount.id)
        .join(
            GroupMember,
            (GroupMember.group_id == GroupServer.group_id) & (GroupMember.user_id == user.id),
        )
        .where(GroupServer.server_pk.in_(server_pks), GroupServer.status == "active")
        .order_by((GroupEaAccount.status == "ok").desc(), GroupServer.id)
    )
    seen: set[int] = set()
    out = []
    for account in rows.all():
        if account.id not in seen:
            seen.add(account.id)
            out.append(account)
    return out


async def record_account_result(
    db: AsyncSession, account: GroupEaAccount, ok: bool, error: str | None = None
) -> None:
    """服务账号一次登录的结果：成功清零失败计数，连续失败到阈值标失效。只 flush"""
    if ok:
        account.failure_count = 0
        account.last_error = None
        if account.status != "ok":
            account.status = "ok"
    else:
        account.failure_count += 1
        account.last_error = (error or "登录失败")[:255]
        if account.failure_count >= ACCOUNT_FAILURE_LIMIT:
            account.status = "invalid"
    await db.flush()


# ===== 复核 =====


@dataclass
class _GroupReport:
    group: Group
    lines: list[str]


async def _check_account(db: AsyncSession, account: GroupEaAccount) -> bool:
    """用凭据登录一次，看还能不能用"""
    try:
        async with get_bf1_client_for_group_account(db, account) as client:
            ok = bool(client.access_token)
    except Exception as e:
        logger.info("服务账号 {} 登录异常: {!r}", account.persona_id, e)
        ok = False
    await record_account_result(db, account, ok)
    account.last_verified_at = _now()
    return ok


async def _binder_status(
    db: AsyncSession, gs: GroupServer, identity: ServerIdentity
) -> tuple[str, str | None]:
    binder = await db.get(User, gs.bound_by_user_id) if gs.bound_by_user_id is not None else None
    if binder is None:
        return "revoked", REASON_BINDER_GONE
    if identity.manages(await _personas_of(db, binder.id)) is None:
        return "revoked", REASON_BINDER_LOST
    return "active", None


async def _executor_problem(
    db: AsyncSession, gs: GroupServer, identity: ServerIdentity
) -> str | None:
    executor = (
        await db.get(GroupEaAccount, gs.executor_account_id)
        if gs.executor_account_id is not None
        else None
    )
    if executor is None:
        return PROBLEM_NO_EXECUTOR
    if executor.status == "invalid":
        return PROBLEM_EXECUTOR_INVALID
    if identity.manages(executor.persona_id) is None:
        return PROBLEM_EXECUTOR_NOT_ADMIN
    return None


async def _recheck_rows(
    db: AsyncSession, rows: list[tuple[GroupServer, Server]]
) -> dict[int, list[str]]:
    """逐台服对照 EA 名单，返回每个群新出现的问题（之前就有的不重复报）"""
    problems: dict[int, list[str]] = {}
    game_ids = await current_game_ids(db, [s for _, s in rows])
    identities: dict[int, ServerIdentity | None] = {}
    for gs, server in rows:
        game_id = game_ids.get(server.id)
        if game_id is None:
            continue
        if server.id not in identities:
            identities[server.id] = await fetch_identity(db, game_id)
        identity = identities[server.id]
        if identity is None:
            # EA 查不到（服务器不在线等），不动现状，下次再看
            continue
        if server.game_id != game_id:
            server.game_id = game_id
        name = server.name or str(server.server_id)
        new: list[str] = []

        status, reason = await _binder_status(db, gs, identity)
        if status == "revoked" and gs.status != "revoked":
            new.append(f"「{name}」：{reason}，群成员在这台服上的权限已经失效")
        gs.status, gs.status_reason = status, reason
        problem = await _executor_problem(db, gs, identity)
        if problem is not None and problem != gs.executor_problem:
            new.append(f"「{name}」：{problem}")
        gs.executor_problem = problem
        gs.last_verified_at = _now()
        if new:
            problems.setdefault(gs.group_id, []).extend(new)
    return problems


async def _recheck_groups(db: AsyncSession, group_ids: list[int]) -> dict[int, list[str]]:
    problems: dict[int, list[str]] = {}
    accounts = list(
        (
            await db.scalars(select(GroupEaAccount).where(GroupEaAccount.group_id.in_(group_ids)))
        ).all()
    )
    for account in accounts:
        was = account.status
        await _check_account(db, account)
        if was == "ok" and account.status == "invalid":
            problems.setdefault(account.group_id, []).append(
                f"服务账号 {account.display_name or account.persona_id} 连续登录失败，"
                "需要重新提交凭据"
            )
    rows = (
        await db.execute(
            select(GroupServer, Server)
            .join(Server, Server.id == GroupServer.server_pk)
            .where(GroupServer.group_id.in_(group_ids))
        )
    ).all()
    for gid, lines in (await _recheck_rows(db, [(gs, s) for gs, s in rows])).items():
        problems.setdefault(gid, []).extend(lines)
    return problems


async def recheck_group(db: AsyncSession, group_id: int, actor: User) -> list[GroupServerView]:
    """群主手动复核：结果直接显示在页面上，不另发邮件"""
    await require_member(db, group_id, actor, "owner")
    await _recheck_groups(db, [group_id])
    await db.commit()
    return await list_servers(db, group_id, actor)


async def _notify(db: AsyncSession, group_id: int, lines: list[str]) -> None:
    group = await db.get(Group, group_id)
    if group is None:
        return
    owners = await db.scalars(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.role == "owner",
            User.email.is_not(None),
        )
    )
    url = f"{get_settings().public_site_url.rstrip('/')}/me/groups/{group_id}"
    for owner in owners:
        message = templates.group_problems(
            to=owner.email or "",
            group_name=group.name,
            lines=[html.escape(line) for line in lines],
            url=url,
        )
        try:
            await get_mail_sender().send(message)
        except Exception as e:
            logger.warning("群 {} 的复核通知发送失败: {!r}", group_id, e)


async def recheck_all(db: AsyncSession) -> None:
    group_ids = list(
        (
            await db.scalars(
                select(GroupServer.group_id)
                .distinct()
                .union(select(GroupEaAccount.group_id).distinct())
            )
        ).all()
    )
    for gid in group_ids:
        try:
            problems = await _recheck_groups(db, [gid])
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning("群 {} 复核失败: {!r}", gid, e)
            continue
        lines = problems.get(gid)
        if lines:
            await _notify(db, gid, lines)


async def group_server_poller(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await asyncio.sleep(RECHECK_FIRST_DELAY_SECONDS)
    while True:
        try:
            async with session_factory() as db:
                await recheck_all(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("群组绑服复核出错: {!r}", e)
        await asyncio.sleep(RECHECK_INTERVAL_SECONDS)


def account_view(account: GroupEaAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "persona_id": account.persona_id,
        "display_name": account.display_name,
        "is_default": account.is_default,
        "status": account.status,
        "last_error": account.last_error,
        "last_verified_at": account.last_verified_at,
        "created_at": account.created_at,
    }
