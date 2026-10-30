"""注销账号：本人申请、冷静期内撤销、到期删除，以及平台管理员直接删除已冻结的账号。

本人申请：核对密码，账号立即按冻结处理（登出全部会话、吊销 Key、挂的服失效、服务器上没有角色），
记下计划删除时间。冷静期内用邮箱和密码登录会被告知，可以撤销；撤销只恢复登录，Key 不恢复。
到期由每小时的账号清理任务删除。

删除时：
- 他是某个群唯一的群主、群里还有别人：群主交给最早入群的管理员，没有管理员就交给最早入群的成员；
  群里只有他自己：解散这个群；
- 他挂的服置为失效；审计日志里他那几条的 IP 清掉，记录本身保留（服主要知道谁做过什么）；
- 删掉 EA 绑定、API Key、群成员、服管授权、验证链接和用户行，邮箱和 EA 账号可以重新注册。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import AppError, NotFoundError, UnauthorizedError
from app.core.config import get_settings
from app.core.passwords import verify_password, verify_password_timing_safe
from app.models import (
    ApiKey,
    AuditLog,
    EaBinding,
    EmailVerification,
    Group,
    GroupMember,
    GroupServer,
    ServerMembership,
    User,
)
from app.services.account_service import AccountError, primary_binding
from app.services.api_key_service import ApiKeyService
from app.services.group_server_service import REASON_BINDER_GONE
from app.services.group_service import _audit as group_audit
from app.services.mail import get_mail_sender, templates
from app.services.mail.templates import RequestMeta
from app.services.site_settings_service import AUDIT_GAME
from app.services.user_admin_service import display_name, lock_down, lock_with_groups
from app.services.user_service import lock_user

CONFIRM_TEXT = "注销"
PURGE_INTERVAL_SECONDS = 3600
REASON_SELF_DELETE = "本人申请注销"
REASON_BINDER_DELETING = "挂服人已申请注销账号"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _site(path: str) -> str:
    return get_settings().public_site_url.rstrip("/") + path


def _audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    payload: dict,
    ip: str | None,
    persona_id: int = 0,
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            acting_persona_id=persona_id,
            game=AUDIT_GAME,
            action=action,
            payload=payload,
            result="success",
            ip=ip,
        )
    )


async def sole_owner_groups(db: AsyncSession, user_id: int) -> list[str]:
    """他是唯一群主、群里还有别人的群名：申请注销前要先交出群主或解散"""
    owned = list(
        await db.scalars(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user_id, GroupMember.role == "owner"
            )
        )
    )
    names: list[str] = []
    for gid in owned:
        others = await db.execute(
            select(GroupMember.role, func.count())
            .where(GroupMember.group_id == gid, GroupMember.user_id != user_id)
            .group_by(GroupMember.role)
        )
        counts = dict(others.tuples().all())
        if counts and not counts.get("owner"):
            name = await db.scalar(select(Group.name).where(Group.id == gid))
            names.append(name or f"#{gid}")
    return names


# ===== 本人申请、撤销 =====


async def request_deletion(
    db: AsyncSession, user: User, password: str, confirm: str, ip: str | None = None
) -> datetime:
    if confirm.strip() != CONFIRM_TEXT:
        raise AccountError("ACCOUNT_DELETE_CONFIRM", f"请输入「{CONFIRM_TEXT}」确认")
    if user.role == "admin":
        raise AccountError(
            "ACCOUNT_DELETE_ADMIN", "平台管理员不能自助注销，先用命令行撤销管理员身份", 409
        )
    if user.local_password_hash is None:
        raise AccountError("PASSWORD_NOT_SET", "这个账号还没有设置密码，请先设置登录邮箱")

    # 所在的群也要锁：唯一群主的检查不能和并发的改角色、退群交错
    locked = await lock_with_groups(db, user.id, member_groups=True)
    if locked is None:
        raise UnauthorizedError()
    if not verify_password(password, locked.local_password_hash):
        raise AccountError("PASSWORD_WRONG", "密码不正确")
    if locked.is_frozen:
        raise AccountError("ACCOUNT_FROZEN", "账号已被冻结", 403)
    blockers = await sole_owner_groups(db, locked.id)
    if blockers:
        names = "、".join(f"「{n}」" for n in blockers)
        raise AccountError(
            "ACCOUNT_DELETE_SOLE_OWNER",
            f"你是群{names}唯一的群主，先把群主交给别人，或者解散群，再申请注销",
            409,
        )

    keys, bindings = await lock_down(
        db,
        locked,
        by=locked.id,
        reason=REASON_SELF_DELETE,
        binding_reason=REASON_BINDER_DELETING,
    )
    delete_at = _now() + timedelta(days=get_settings().account_deletion_cooldown_days)
    locked.deletion_scheduled_at = delete_at
    binding = primary_binding(locked)
    _audit(
        db,
        actor_id=locked.id,
        action="account_delete_request",
        payload={
            "delete_at": delete_at.isoformat(),
            "revoked_keys": len(keys),
            "revoked_group_servers": bindings,
        },
        ip=ip,
        persona_id=binding.persona_id if binding else 0,
    )
    await db.commit()
    service = ApiKeyService(db)
    for key in keys:
        await service.deny_cache(key)
    return delete_at


async def cancel_deletion(
    db: AsyncSession, email: str, password: str, ip: str | None = None
) -> User:
    """冷静期内撤销注销：核对邮箱和密码，解除冻结并登录。Key 不恢复，挂服等复核按 EA 现状恢复"""
    user_id = await db.scalar(select(User.id).where(func.lower(User.email) == email))
    # 锁住再核对密码：和重置密码并发时，要用重置后的密码
    locked = await lock_user(db, user_id) if user_id is not None else None
    password_ok = verify_password_timing_safe(
        password, locked.local_password_hash if locked else None
    )
    if locked is None or not password_ok or not locked.is_active:
        raise UnauthorizedError("邮箱或密码错误")
    if locked.deletion_scheduled_at is None:
        raise AccountError("ACCOUNT_NOT_DELETING", "这个账号没有在注销中，直接登录即可", 409)
    locked.is_frozen = False
    locked.frozen_at = None
    locked.frozen_reason = None
    locked.frozen_by = None
    locked.deletion_scheduled_at = None
    locked.last_login_at = _now()
    binding = primary_binding(locked)
    _audit(
        db,
        actor_id=locked.id,
        action="account_delete_cancel",
        payload={},
        ip=ip,
        persona_id=binding.persona_id if binding else 0,
    )
    await db.commit()
    return locked


async def send_deletion_scheduled(email: str, delete_at: datetime, ip: str | None) -> None:
    try:
        await get_mail_sender().send(
            templates.account_deletion_scheduled(
                to=email,
                delete_at=delete_at,
                login_url=_site("/login"),
                meta=RequestMeta.now(ip),
            )
        )
    except Exception as e:
        logger.warning("注销申请通知发送失败: {!r}", e)


# ===== 删除 =====


@dataclass(frozen=True)
class PurgeResult:
    email: str | None
    groups_transferred: int
    groups_dissolved: int


async def _hand_over_groups(db: AsyncSession, user: User) -> tuple[int, set[int]]:
    """他是唯一群主的群：有别人就把群主交出去，没人就解散。调用方已锁住这些群"""
    transferred = 0
    dissolved: set[int] = set()
    owned = list(
        await db.scalars(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user.id, GroupMember.role == "owner"
            )
        )
    )
    for gid in owned:
        others = list(
            (
                await db.scalars(
                    select(GroupMember)
                    .where(GroupMember.group_id == gid, GroupMember.user_id != user.id)
                    .order_by(GroupMember.joined_at, GroupMember.id)
                )
            ).all()
        )
        if any(m.role == "owner" for m in others):
            continue
        if not others:
            group = await db.get(Group, gid)
            if group is not None:
                await group_audit(
                    db,
                    actor=None,
                    group_id=gid,
                    action="group_delete",
                    payload={"name": group.name, "reason": "群主注销账号，群里没有其他成员"},
                )
                await db.delete(group)
                dissolved.add(gid)
            continue
        heir = next((m for m in others if m.role == "admin"), others[0])
        await group_audit(
            db,
            actor=None,
            group_id=gid,
            action="group_owner_inherit",
            payload={"from": heir.role},
            target=await db.get(User, heir.user_id),
        )
        heir.role = "owner"
        transferred += 1
    return transferred, dissolved


async def _purge_locked(
    db: AsyncSession, user: User, *, actor: User | None, ip: str | None
) -> PurgeResult:
    """删除已锁住的账号并提交。actor 为空是冷静期到期自动删除"""
    user_id = user.id
    email = user.email
    name = display_name(user)
    transferred, dissolved = await _hand_over_groups(db, user)
    # 他还在的群各记一笔，群里看得到人是怎么没的
    for gid in await db.scalars(select(GroupMember.group_id).where(GroupMember.user_id == user_id)):
        if gid in dissolved:
            continue
        await group_audit(
            db,
            actor=None,
            group_id=gid,
            action="group_member_account_deleted",
            payload={"name": name},
        )

    await db.execute(
        update(GroupServer)
        .where(GroupServer.bound_by_user_id == user_id)
        .values(status="revoked", status_reason=REASON_BINDER_GONE, bound_by_user_id=None)
    )
    # 审计记录保留，清掉他的 IP
    await db.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(ip=None))
    keys = list(await db.scalars(select(ApiKey).where(ApiKey.user_id == user_id)))
    # 外键是 ON DELETE CASCADE，这里显式删一遍，不依赖数据库是否开着外键约束
    for model in (ApiKey, EaBinding, GroupMember, ServerMembership):
        await db.execute(delete(model).where(model.user_id == user_id))
    conds = [EmailVerification.user_id == user_id]
    if email:
        conds.append(EmailVerification.email == email.lower())
    await db.execute(delete(EmailVerification).where(or_(*conds)))
    db.expunge(user)
    await db.execute(delete(User).where(User.id == user_id))

    actor_binding = primary_binding(actor) if actor else None
    _audit(
        db,
        actor_id=actor.id if actor else None,
        action="account_delete",
        payload={
            "target_user_id": user_id,
            "by": "admin" if actor else "self",
            "groups_transferred": transferred,
            "groups_dissolved": len(dissolved),
        },
        ip=ip,
        persona_id=actor_binding.persona_id if actor_binding else 0,
    )
    await db.commit()
    service = ApiKeyService(db)
    for key in keys:
        await service.deny_cache(key)
    return PurgeResult(email=email, groups_transferred=transferred, groups_dissolved=len(dissolved))


async def admin_delete(db: AsyncSession, actor: User, user_id: int, ip: str | None = None) -> None:
    """平台管理员删除账号：只能删已冻结的（冻结后看过情况再删），不能删管理员和自己"""
    if user_id == actor.id:
        raise AppError(409, "USER_DELETE_SELF", "不能删除自己")
    target = await lock_with_groups(db, user_id, member_groups=True)
    if target is None:
        raise NotFoundError("用户")
    if target.role == "admin":
        raise AppError(409, "USER_DELETE_ADMIN", "平台管理员不能在这里删除，先用命令行撤销管理员")
    if not target.is_frozen:
        raise AppError(409, "USER_DELETE_NOT_FROZEN", "先冻结这个账号，确认无误后再删除")
    await _purge_locked(db, target, actor=actor, ip=ip)


async def _purge_if_due(db: AsyncSession, user_id: int) -> PurgeResult | None:
    user = await lock_with_groups(db, user_id, member_groups=True)
    # 锁住后再看一次：可能刚刚撤销了注销
    if (
        user is None
        or user.deletion_scheduled_at is None
        or _aware(user.deletion_scheduled_at) > _now()
    ):
        await db.rollback()
        return None
    return await _purge_locked(db, user, actor=None, ip=None)


async def purge_due(db: AsyncSession) -> int:
    """删除冷静期已过的账号，每个账号单独提交，一个失败不影响其他"""
    ids = list(
        await db.scalars(
            select(User.id).where(
                User.deletion_scheduled_at.is_not(None), User.deletion_scheduled_at <= _now()
            )
        )
    )
    done = 0
    for uid in ids:
        try:
            result = await _purge_if_due(db, uid)
        except Exception as e:
            await db.rollback()
            logger.warning("删除到期注销账号 {} 失败: {!r}", uid, e)
            continue
        if result is None:
            continue
        done += 1
        if result.email:
            try:
                await get_mail_sender().send(
                    templates.account_deleted(to=result.email, meta=RequestMeta.now(None))
                )
            except Exception as e:
                logger.warning("账号删除通知发送失败: {!r}", e)
    if done:
        logger.info("删除到期注销账号 {} 个", done)
    return done


async def account_deletion_poller(session_factory: async_sessionmaker[AsyncSession]) -> None:
    while True:
        try:
            async with session_factory() as db:
                await purge_due(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("删除到期注销账号出错: {!r}", e)
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
