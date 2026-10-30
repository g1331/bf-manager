"""平台管理员管理用户：列表、冻结、解冻。

冻结一个账号会同时：
- 登出他所有会话（token_version +1），之后登录、调用接口一律被拒；
- 吊销他全部有效的 API Key，缓存一并清掉，下一个请求就生效；
- 他挂到群上的服立即失效，群成员不能再借他的服管身份；
- 他发起的自动换图、计时 VIP 下 V 等后台任务按权限重算后停下（resolve_role 对冻结账号不给角色）。

解冻只恢复登录：吊销的 Key 不恢复；失效的挂服等下次复核（或群主点“立即检查”）按 EA 现状恢复。
平台管理员不能在后台被冻结，要先用命令行撤销管理员身份。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError, NotFoundError
from app.models import ApiKey, AuditLog, EaBinding, GroupServer, User
from app.services.account_service import primary_binding
from app.services.api_key_service import ApiKeyService
from app.services.group_server_service import REASON_BINDER_FROZEN
from app.services.group_service import _lock_group
from app.services.site_settings_service import AUDIT_GAME
from app.services.user_service import bump_token_version, lock_user

REASON_MAX = 200
_INT_MAX = 2**31 - 1
_BIGINT_MAX = 2**63 - 1


@dataclass
class UserRow:
    user: User
    active_keys: int
    frozen_by_name: str | None


def display_name(user: User) -> str:
    binding = primary_binding(user)
    return (binding.display_name if binding else None) or user.username


async def list_users(
    db: AsyncSession,
    *,
    q: str | None,
    only: str | None,
    page: int,
    page_size: int,
) -> tuple[list[UserRow], int]:
    stmt = select(User)
    if q:
        text = q.strip()
        like = f"%{text}%"
        conds = [
            User.username.ilike(like),
            User.email.ilike(like),
            User.id.in_(select(EaBinding.user_id).where(EaBinding.display_name.ilike(like))),
        ]
        if text.isdigit():
            # 超出列范围的数字传给 PG 会编码失败（persona ID 通常超出 INTEGER），只在范围内才比
            number = int(text)
            if number <= _BIGINT_MAX:
                conds.append(
                    User.id.in_(select(EaBinding.user_id).where(EaBinding.persona_id == number))
                )
            if number <= _INT_MAX:
                conds.append(User.id == number)
        stmt = stmt.where(or_(*conds))
    if only == "frozen":
        stmt = stmt.where(User.is_frozen.is_(True))
    elif only == "admin":
        stmt = stmt.where(User.role == "admin")

    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    users = list(
        (
            await db.scalars(
                stmt.options(selectinload(User.ea_bindings))
                .order_by(User.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    ids = [u.id for u in users]
    keys: dict[int, int] = {}
    if ids:
        keys = {
            uid: int(n)
            for uid, n in await db.execute(
                select(ApiKey.user_id, func.count())
                .where(ApiKey.user_id.in_(ids), ApiKey.revoked_at.is_(None))
                .group_by(ApiKey.user_id)
            )
        }
    by_ids = {u.frozen_by for u in users if u.frozen_by is not None}
    names: dict[int, str] = {}
    if by_ids:
        for admin in await db.scalars(
            select(User).options(selectinload(User.ea_bindings)).where(User.id.in_(by_ids))
        ):
            names[admin.id] = display_name(admin)
    rows = [
        UserRow(
            user=u,
            active_keys=keys.get(u.id, 0),
            frozen_by_name=names.get(u.frozen_by) if u.frozen_by is not None else None,
        )
        for u in users
    ]
    return rows, total


async def _audit(
    db: AsyncSession, actor: User, target: User, action: str, payload: dict, ip: str | None
) -> None:
    actor_binding = primary_binding(actor)
    target_binding = primary_binding(target)
    db.add(
        AuditLog(
            user_id=actor.id,
            acting_persona_id=actor_binding.persona_id if actor_binding else 0,
            game=AUDIT_GAME,
            action=action,
            target_persona_id=target_binding.persona_id if target_binding else None,
            payload={"target_user_id": target.id, "target_name": display_name(target), **payload},
            result="success",
            ip=ip,
        )
    )


async def freeze(
    db: AsyncSession, actor: User, user_id: int, reason: str, ip: str | None = None
) -> UserRow:
    reason = reason.strip()
    if not reason:
        raise AppError(422, "USER_FREEZE_REASON", "写一下冻结原因")
    if len(reason) > REASON_MAX:
        raise AppError(422, "USER_FREEZE_REASON", f"冻结原因最多 {REASON_MAX} 个字")
    if user_id == actor.id:
        raise AppError(409, "USER_FREEZE_SELF", "不能冻结自己")

    # 先锁目标涉及的群（按 id 顺序），再锁用户：和挂服、复核用同一把群锁，次序固定不会互等
    group_ids = sorted(
        set(
            await db.scalars(
                select(GroupServer.group_id).where(GroupServer.bound_by_user_id == user_id)
            )
        )
    )
    for gid in group_ids:
        await _lock_group(db, gid)
    target = await lock_user(db, user_id)
    if target is None:
        raise NotFoundError("用户")
    if target.role == "admin":
        raise AppError(409, "USER_FREEZE_ADMIN", "平台管理员不能在这里冻结，先用命令行撤销管理员")
    if target.is_frozen:
        raise AppError(409, "USER_ALREADY_FROZEN", "这个账号已经冻结了")

    now = datetime.now(UTC)
    target.is_frozen = True
    target.frozen_at = now
    target.frozen_reason = reason
    target.frozen_by = actor.id
    await bump_token_version(db, target)

    keys = list(
        (
            await db.scalars(
                select(ApiKey).where(ApiKey.user_id == target.id, ApiKey.revoked_at.is_(None))
            )
        ).all()
    )
    for key in keys:
        key.revoked_at = now

    bindings = list(
        (
            await db.scalars(
                select(GroupServer).where(
                    GroupServer.bound_by_user_id == target.id, GroupServer.status == "active"
                )
            )
        ).all()
    )
    for gs in bindings:
        gs.status = "revoked"
        gs.status_reason = REASON_BINDER_FROZEN

    await _audit(
        db,
        actor,
        target,
        "user_freeze",
        {"reason": reason, "revoked_keys": len(keys), "revoked_group_servers": len(bindings)},
        ip,
    )
    await db.commit()
    # 提交成功后再把缓存写成无效，提交失败时不误伤有效的 Key
    service = ApiKeyService(db)
    for key in keys:
        await service.deny_cache(key)
    return UserRow(user=target, active_keys=0, frozen_by_name=display_name(actor))


async def unfreeze(db: AsyncSession, actor: User, user_id: int, ip: str | None = None) -> UserRow:
    target = await lock_user(db, user_id)
    if target is None:
        raise NotFoundError("用户")
    if not target.is_frozen:
        raise AppError(409, "USER_NOT_FROZEN", "这个账号没有冻结")
    reason = target.frozen_reason
    target.is_frozen = False
    target.frozen_at = None
    target.frozen_reason = None
    target.frozen_by = None
    await _audit(db, actor, target, "user_unfreeze", {"frozen_reason": reason}, ip)
    await db.commit()
    active_keys = await db.scalar(
        select(func.count()).where(ApiKey.user_id == target.id, ApiKey.revoked_at.is_(None))
    )
    return UserRow(user=target, active_keys=int(active_keys or 0), frozen_by_name=None)
