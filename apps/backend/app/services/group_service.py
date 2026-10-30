"""群组：建群、成员与角色、邀请链接

角色等级沿用 ROLE_LEVEL：owner > admin > moderator > viewer。

- owner 可以有多个：改群名、删群、设任何人的角色、移出任何人；群里至少要留一个 owner。
- admin 只能管 moderator / viewer：在这两级之间调整、移出。
- 邀请链接上的角色必须低于发链接人的角色：owner 最高发 admin，admin 最高发 moderator。
  owner 只能由 owner 在成员列表里提升，不能通过链接给出。
- 不是群成员的人访问群接口一律 404，不暴露群是否存在。

改成员、进群前先锁住 groups 行：两个 owner 同时把对方降级、或多人同时用最后一次
邀请名额时，按顺序执行，「至少一个 owner」「人数上限」才守得住。
操作都写 audit_logs（game=group，带 group_id），和成员变更在同一个事务里提交。
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError, NotFoundError
from app.core.config import get_settings
from app.models import AuditLog, EaBinding, Group, GroupInvite, GroupMember, User
from app.services.authz_service import ROLE_LEVEL
from app.services.user_service import lock_user

AUDIT_GAME = "group"
INVITE_TTL_HOURS = (1, 24, 72, 168)


class GroupError(AppError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(status, code, message)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _level(role: str | None) -> int:
    return ROLE_LEVEL.get(role or "", 0)


async def _persona_of(db: AsyncSession, user_id: int | None) -> int:
    """主绑定的 persona；查库而不是读 user.ea_bindings，刚建的账号这个关系还没加载"""
    if user_id is None:
        return 0
    persona = await db.scalar(
        select(EaBinding.persona_id).where(
            EaBinding.user_id == user_id,
            EaBinding.is_primary.is_(True),
            EaBinding.is_frozen.is_(False),
        )
    )
    return int(persona or 0)


async def _audit(
    db: AsyncSession,
    *,
    actor: User | None,
    group_id: int,
    action: str,
    target: User | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    target_persona = await _persona_of(db, target.id) if target else 0
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            acting_persona_id=await _persona_of(db, actor.id if actor else None),
            game=AUDIT_GAME,
            group_id=group_id,
            action=action,
            target_persona_id=target_persona or None,
            payload={**(payload or {}), **({"target_user_id": target.id} if target else {})},
            result="success",
            ip=ip,
        )
    )


# ===== 读取 =====


async def _lock_group(db: AsyncSession, group_id: int) -> Group:
    group = await db.scalar(
        select(Group)
        .where(Group.id == group_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if group is None:
        raise NotFoundError("群组")
    return group


async def get_membership(db: AsyncSession, group_id: int, user_id: int) -> GroupMember | None:
    return await db.scalar(
        select(GroupMember)
        .where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .execution_options(populate_existing=True)
    )


async def require_member(
    db: AsyncSession, group_id: int, user: User, min_role: str = "viewer"
) -> GroupMember:
    """不是成员 → 404；角色不够 → 403"""
    member = await get_membership(db, group_id, user.id)
    if member is None:
        raise NotFoundError("群组")
    if _level(member.role) < _level(min_role):
        raise GroupError("GROUP_FORBIDDEN", "你在这个群里的角色不够", 403)
    return member


@dataclass(frozen=True)
class GroupSummary:
    group: Group
    role: str
    member_count: int


async def _member_counts(db: AsyncSession, group_ids: list[int]) -> dict[int, int]:
    if not group_ids:
        return {}
    rows = await db.execute(
        select(GroupMember.group_id, func.count())
        .where(GroupMember.group_id.in_(group_ids))
        .group_by(GroupMember.group_id)
    )
    return {gid: int(n) for gid, n in rows.all()}


async def list_my_groups(db: AsyncSession, user: User) -> list[GroupSummary]:
    rows = (
        await db.execute(
            select(Group, GroupMember.role)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user.id)
            .order_by(Group.created_at)
        )
    ).all()
    counts = await _member_counts(db, [g.id for g, _ in rows])
    return [GroupSummary(group=g, role=role, member_count=counts.get(g.id, 0)) for g, role in rows]


async def list_members(db: AsyncSession, group_id: int) -> list[GroupMember]:
    rows = await db.scalars(
        select(GroupMember)
        .options(selectinload(GroupMember.user).selectinload(User.ea_bindings))
        .where(GroupMember.group_id == group_id)
    )
    members = list(rows.all())
    members.sort(key=lambda m: (-_level(m.role), _aware(m.joined_at)))
    return members


# ===== 建群、改名、删群 =====


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not 1 <= len(name) <= 32:
        raise GroupError("GROUP_NAME_INVALID", "群名 1 到 32 个字")
    return name


async def create_group(db: AsyncSession, user: User, name: str, ip: str | None = None) -> Group:
    name = _clean_name(name)
    if user.role != "admin":
        # 锁住建群人再数：同一个人并发建群时排队，不会一起看到「还差一个」而超出上限
        await lock_user(db, user.id)
        if await _persona_of(db, user.id) == 0:
            raise GroupError("GROUP_NEED_BINDING", "绑定 EA 账号后才能建群", 403)
        owned = await db.scalar(
            select(func.count()).select_from(Group).where(Group.created_by == user.id)
        )
        if int(owned or 0) >= get_settings().group_owned_limit_per_user:
            raise GroupError(
                "GROUP_LIMIT", f"每人最多建 {get_settings().group_owned_limit_per_user} 个群"
            )
    group = Group(name=name, created_by=user.id)
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id, role="owner"))
    await _audit(
        db, actor=user, group_id=group.id, action="group_create", payload={"name": name}, ip=ip
    )
    await db.commit()
    await db.refresh(group)
    return group


async def rename_group(
    db: AsyncSession, group_id: int, user: User, name: str, ip: str | None = None
) -> Group:
    # 先锁群再查身份：等锁期间被降级、移出的人，拿到锁后读到的是新身份
    group = await _lock_group(db, group_id)
    await require_member(db, group_id, user, "owner")
    old, group.name = group.name, _clean_name(name)
    await _audit(
        db,
        actor=user,
        group_id=group_id,
        action="group_rename",
        payload={"from": old, "to": group.name},
        ip=ip,
    )
    await db.commit()
    return group


async def delete_group(db: AsyncSession, group_id: int, user: User, ip: str | None = None) -> None:
    group = await _lock_group(db, group_id)
    await require_member(db, group_id, user, "owner")
    await _audit(
        db,
        actor=user,
        group_id=group_id,
        action="group_delete",
        payload={"name": group.name},
        ip=ip,
    )
    await db.delete(group)
    await db.commit()


# ===== 成员 =====


async def _owner_count(db: AsyncSession, group_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id, GroupMember.role == "owner")
        )
        or 0
    )


def _can_manage(actor_role: str, target_role: str, new_role: str | None = None) -> bool:
    """actor 能否改动 target（new_role 为空表示移出）"""
    if actor_role == "owner":
        return True
    if actor_role == "admin":
        low = ("moderator", "viewer")
        return target_role in low and (new_role is None or new_role in low)
    return False


async def _load_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.scalar(
        select(User).options(selectinload(User.ea_bindings)).where(User.id == user_id)
    )


async def set_member_role(
    db: AsyncSession,
    group_id: int,
    actor: User,
    target_user_id: int,
    new_role: str,
    ip: str | None = None,
) -> None:
    if new_role not in ROLE_LEVEL:
        raise GroupError("GROUP_ROLE_INVALID", "角色无效")
    await _lock_group(db, group_id)
    me = await require_member(db, group_id, actor)
    target = await get_membership(db, group_id, target_user_id)
    if target is None:
        raise NotFoundError("成员")
    if target.role == new_role:
        return
    if not _can_manage(me.role, target.role, new_role):
        raise GroupError("GROUP_FORBIDDEN", "你不能这样调整这个成员的角色", 403)
    if target.role == "owner" and await _owner_count(db, group_id) <= 1:
        raise GroupError("GROUP_LAST_OWNER", "群里至少要留一个群主，先把别人设成群主")
    old = target.role
    target.role = new_role
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_member_role",
        target=await _load_user(db, target_user_id),
        payload={"from": old, "to": new_role},
        ip=ip,
    )
    await db.commit()


async def remove_member(
    db: AsyncSession, group_id: int, actor: User, target_user_id: int, ip: str | None = None
) -> None:
    """移出别人；自己退群走 leave_group"""
    if target_user_id == actor.id:
        await leave_group(db, group_id, actor, ip=ip)
        return
    await _lock_group(db, group_id)
    me = await require_member(db, group_id, actor)
    target = await get_membership(db, group_id, target_user_id)
    if target is None:
        raise NotFoundError("成员")
    if not _can_manage(me.role, target.role):
        raise GroupError("GROUP_FORBIDDEN", "你不能移出这个成员", 403)
    if target.role == "owner" and await _owner_count(db, group_id) <= 1:
        raise GroupError("GROUP_LAST_OWNER", "群里至少要留一个群主")
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_member_remove",
        target=await _load_user(db, target_user_id),
        payload={"role": target.role},
        ip=ip,
    )
    await db.delete(target)
    await db.commit()


async def leave_group(db: AsyncSession, group_id: int, user: User, ip: str | None = None) -> None:
    await _lock_group(db, group_id)
    me = await require_member(db, group_id, user)
    if me.role == "owner" and await _owner_count(db, group_id) <= 1:
        raise GroupError("GROUP_LAST_OWNER", "你是群里唯一的群主：先把别人设成群主，或者直接删除群")
    await _audit(
        db, actor=user, group_id=group_id, action="group_leave", payload={"role": me.role}, ip=ip
    )
    await db.delete(me)
    await db.commit()


# ===== 邀请链接 =====


def invite_is_live(invite: GroupInvite, now: datetime | None = None) -> bool:
    now = now or _now()
    return (
        invite.revoked_at is None
        and _aware(invite.expires_at) > now
        and invite.uses < invite.max_uses
    )


async def create_invite(
    db: AsyncSession,
    group_id: int,
    actor: User,
    *,
    role: str,
    max_uses: int,
    ttl_hours: int,
    ip: str | None = None,
) -> tuple[GroupInvite, str]:
    """返回 (邀请行, 明文 token)。明文只在这一次返回给前端，库里只存哈希。"""
    settings = get_settings()
    await _lock_group(db, group_id)
    me = await require_member(db, group_id, actor, "admin")
    if role not in ROLE_LEVEL or role == "owner" or _level(role) >= _level(me.role):
        raise GroupError("GROUP_ROLE_INVALID", "链接上的角色要低于你自己的角色")
    if not 1 <= max_uses <= settings.group_invite_max_uses:
        raise GroupError("GROUP_INVITE_USES", f"每条链接最多用 {settings.group_invite_max_uses} 次")
    if ttl_hours not in INVITE_TTL_HOURS:
        raise GroupError("GROUP_INVITE_TTL", "有效期无效")
    live = [i for i in await _invites(db, group_id) if invite_is_live(i)]
    if len(live) >= settings.group_invite_active_limit:
        raise GroupError(
            "GROUP_INVITE_LIMIT",
            f"有效的邀请链接最多 {settings.group_invite_active_limit} 条，先作废一些",
        )
    token = secrets.token_urlsafe(24)
    invite = GroupInvite(
        group_id=group_id,
        token_hash=hash_invite_token(token),
        role=role,
        created_by=actor.id,
        max_uses=max_uses,
        uses=0,
        expires_at=_now() + timedelta(hours=ttl_hours),
    )
    db.add(invite)
    await db.flush()
    await _audit(
        db,
        actor=actor,
        group_id=group_id,
        action="group_invite_create",
        payload={
            "invite_id": invite.id,
            "role": role,
            "max_uses": max_uses,
            "ttl_hours": ttl_hours,
        },
        ip=ip,
    )
    await db.commit()
    await db.refresh(invite)
    return invite, token


async def _invites(db: AsyncSession, group_id: int) -> list[GroupInvite]:
    rows = await db.scalars(
        select(GroupInvite)
        .where(GroupInvite.group_id == group_id)
        .order_by(GroupInvite.created_at.desc())
    )
    return list(rows.all())


async def list_live_invites(db: AsyncSession, group_id: int, actor: User) -> list[GroupInvite]:
    await require_member(db, group_id, actor, "admin")
    now = _now()
    return [i for i in await _invites(db, group_id) if invite_is_live(i, now)]


async def revoke_invite(
    db: AsyncSession, group_id: int, invite_id: int, actor: User, ip: str | None = None
) -> None:
    await _lock_group(db, group_id)
    me = await require_member(db, group_id, actor, "admin")
    invite = await db.get(GroupInvite, invite_id)
    if invite is None or invite.group_id != group_id:
        raise NotFoundError("邀请链接")
    if me.role != "owner" and invite.created_by != actor.id:
        raise GroupError("GROUP_FORBIDDEN", "只能作废自己发的链接", 403)
    if invite.revoked_at is None:
        invite.revoked_at = _now()
        await _audit(
            db,
            actor=actor,
            group_id=group_id,
            action="group_invite_revoke",
            payload={"invite_id": invite.id},
            ip=ip,
        )
        await db.commit()


async def find_invite(db: AsyncSession, token: str) -> GroupInvite:
    """按明文 token 找仍然有效的邀请；找不到、过期、用完、作废一律同一个错误"""
    invite = await db.scalar(
        select(GroupInvite).where(GroupInvite.token_hash == hash_invite_token(token))
    )
    if invite is None or not invite_is_live(invite):
        raise GroupError("GROUP_INVITE_INVALID", "邀请链接无效、已过期或已经用完", 404)
    return invite


@dataclass(frozen=True)
class JoinResult:
    group_id: int
    role: str
    already_member: bool


async def _consume_invite_use(db: AsyncSession, invite_id: int) -> bool:
    used = await db.scalar(
        update(GroupInvite)
        .where(
            GroupInvite.id == invite_id,
            GroupInvite.revoked_at.is_(None),
            GroupInvite.expires_at > _now(),
            GroupInvite.uses < GroupInvite.max_uses,
        )
        .values(uses=GroupInvite.uses + 1)
        .returning(GroupInvite.id)
        .execution_options(synchronize_session=False)
    )
    return used is not None


async def join_with_invite(
    db: AsyncSession, invite: GroupInvite, user: User, ip: str | None = None, *, commit: bool = True
) -> JoinResult:
    """用邀请进群。已经在群里的不消耗名额、不改角色。

    commit=False 时只 flush，交给调用方的事务（注册完成时和建号一起提交）。
    """
    await _lock_group(db, invite.group_id)
    existing = await get_membership(db, invite.group_id, user.id)
    if existing is not None:
        return JoinResult(group_id=invite.group_id, role=existing.role, already_member=True)
    count = int(
        await db.scalar(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == invite.group_id)
        )
        or 0
    )
    if count >= get_settings().group_member_limit:
        raise GroupError("GROUP_FULL", "这个群人数已满")
    if not await _consume_invite_use(db, invite.id):
        raise GroupError("GROUP_INVITE_INVALID", "邀请链接无效、已过期或已经用完", 404)
    db.add(
        GroupMember(
            group_id=invite.group_id,
            user_id=user.id,
            role=invite.role,
            invited_by=invite.created_by,
        )
    )
    await _audit(
        db,
        actor=user,
        group_id=invite.group_id,
        action="group_member_join",
        payload={"invite_id": invite.id, "role": invite.role, "invited_by": invite.created_by},
        ip=ip,
    )
    if commit:
        await db.commit()
    else:
        await db.flush()
    return JoinResult(group_id=invite.group_id, role=invite.role, already_member=False)


# ===== 群组记录 =====


async def list_audit(
    db: AsyncSession, group_id: int, actor: User, *, page: int, page_size: int
) -> tuple[list[AuditLog], int]:
    await require_member(db, group_id, actor, "admin")
    base = select(AuditLog).where(AuditLog.group_id == group_id)
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = await db.scalars(
        base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.all()), total
