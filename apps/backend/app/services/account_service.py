"""账号：注册、认领旧账号、找回密码、补邮箱、改密码、邀请码。

设计见 bf-manager-notes/用户系统方案.md 第 3 节和第 8 节，要点：

- 注册信、找回密码信都在后台任务里查库、查 EA、发信，接口不管结果一律返回同样的话，
  耗时也一样，不能拿来探测某个邮箱有没有 EA 号、有没有注册。
- 验证链接打开时（GET）不消耗 token，只有提交密码（POST）时才原子地消耗；密码只在这一步设置，
  不跟着验证信走，避免“别人替你填好密码、你点了链接账号就归他”。
- 一个 EA 号同时只能绑在一个账号上；挂在旧账号（status=legacy）上的，按认领处理。
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError, NotFoundError, UnauthorizedError, ValidationError
from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.passwords import hash_password, verify_password, verify_password_timing_safe
from app.models import EaBinding, EmailVerification, InviteCode, User
from app.services.bf1.gateway_factory import get_bf1_client
from app.services.mail import MailMessage, get_mail_sender, templates
from app.services.mail.templates import RequestMeta
from app.services.user_service import bump_token_version, lock_user

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """sqlite 读回来的时间没有时区，统一当 UTC 处理"""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationError(f"密码至少 {PASSWORD_MIN_LENGTH} 位")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationError(f"密码最多 {PASSWORD_MAX_LENGTH} 位")


def _site(path: str) -> str:
    return get_settings().public_site_url.rstrip("/") + path


class AccountError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(status_code, code, message)


# ===== EA 邮箱反查 =====


@dataclass(frozen=True)
class EaEmailMatch:
    persona_id: int
    ea_user_id: int | None
    display_name: str


async def lookup_ea_by_email(db: AsyncSession, email: str) -> EaEmailMatch | None:
    """用 EA 的 SAL SearchPlayer 按邮箱反查 EA 账号，必须恰好命中一个。

    只走 SAL，不能用 player_service.search_by_name：那里查不到精确同名时会把查询词转发给
    gametools，邮箱会泄露给第三方。
    """
    async with get_bf1_client(db) as client:
        res = await client.getPersonasByName(email)
    if not isinstance(res, dict):
        logger.warning("EA 邮箱反查失败: {}", res)
        return None
    items = [p for p in res.get("personas") or [] if p.get("personaId")]
    if len(items) != 1:
        return None
    p = items[0]
    return EaEmailMatch(
        persona_id=int(p["personaId"]),
        ea_user_id=int(p["pidId"]) if p.get("pidId") else None,
        display_name=str(p.get("displayName") or ""),
    )


# ===== 发信频率 =====


async def _invite_mail_allowed(invite_id: int) -> bool:
    try:
        r = await get_redis()
        key = f"bfm:mail:invite:{_now():%Y%m%d}:{invite_id}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 86400)
        return count <= get_settings().account_mail_per_invite_per_day
    except Exception as e:
        logger.warning("邀请码发信计数失败，放行: {!r}", e)
        return True


async def _mail_allowed(email: str) -> bool:
    """同一邮箱冷却 + 每日上限。超了就静默不发，接口照常返回，不暴露任何信息。"""
    settings = get_settings()
    digest = _hash_token(email)[:24]
    try:
        r = await get_redis()
        if not await r.set(
            f"bfm:mail:cd:{digest}", "1", nx=True, ex=settings.account_mail_cooldown_seconds
        ):
            logger.info("账号邮件冷却中，跳过 mail={}", digest[:8])
            return False
        day_key = f"bfm:mail:day:{_now():%Y%m%d}:{digest}"
        count = await r.incr(day_key)
        if count == 1:
            await r.expire(day_key, 86400)
        if count > settings.account_mail_per_email_per_day:
            logger.info("账号邮件超出每日上限，跳过 mail={}", digest[:8])
            return False
        return True
    except Exception as e:
        logger.warning("发信频率检查失败，放行: {!r}", e)
        return True


# ===== 验证链接 =====


async def _create_verification(
    db: AsyncSession,
    *,
    kind: str,
    email: str,
    ttl_hours: int,
    user_id: int | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> str:
    """作废同一邮箱同类未用的旧链接，新建一条，返回明文 token（只出现在邮件里）。"""
    kinds = ("register", "claim") if kind in ("register", "claim") else (kind,)
    await db.execute(
        update(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.kind.in_(kinds),
            EmailVerification.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            kind=kind,
            email=email,
            token_hash=_hash_token(token),
            user_id=user_id,
            payload=payload or {},
            request_ip=ip,
            expires_at=_now() + timedelta(hours=ttl_hours),
        )
    )
    await db.commit()
    return token


async def _live_verification(db: AsyncSession, token: str) -> EmailVerification:
    row = await db.scalar(
        select(EmailVerification).where(EmailVerification.token_hash == _hash_token(token))
    )
    if row is None or row.used_at is not None or (_aware(row.expires_at) or _now()) <= _now():
        raise AccountError("LINK_INVALID", "链接无效或已过期，请重新申请", 404)
    return row


async def _consume_verification(db: AsyncSession, token: str) -> EmailVerification:
    """原子地把链接标记为已用；并发提交时只有一个能成功。调用方负责后续写入和 commit。"""
    now = _now()
    vid = await db.scalar(
        update(EmailVerification)
        .where(
            EmailVerification.token_hash == _hash_token(token),
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > now,
        )
        .values(used_at=now)
        .returning(EmailVerification.id)
    )
    if vid is None:
        raise AccountError("LINK_INVALID", "链接无效或已过期，请重新申请", 404)
    row = await db.get(EmailVerification, vid)
    assert row is not None
    return row


# ===== 查询辅助 =====


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == email))


async def _active_binding(db: AsyncSession, persona_id: int) -> EaBinding | None:
    return await db.scalar(
        select(EaBinding)
        .options(selectinload(EaBinding.user))
        .where(EaBinding.persona_id == persona_id, EaBinding.is_frozen.is_(False))
    )


def primary_binding(user: User) -> EaBinding | None:
    for b in user.ea_bindings:
        if b.is_primary and not b.is_frozen:
            return b
    return None


# ===== 邀请码 =====


async def check_invite_code(db: AsyncSession, code: str) -> InviteCode:
    row = await db.scalar(select(InviteCode).where(InviteCode.code == code.strip().upper()))
    if (
        row is None
        or row.used_at is not None
        or row.revoked_at is not None
        or (_aware(row.expires_at) or _now()) <= _now()
    ):
        raise AccountError("INVITE_INVALID", "邀请码无效、已被使用或已过期")
    return row


async def _consume_invite(db: AsyncSession, invite_id: int, user_id: int) -> None:
    now = _now()
    hit = await db.scalar(
        update(InviteCode)
        .where(
            InviteCode.id == invite_id,
            InviteCode.used_at.is_(None),
            InviteCode.revoked_at.is_(None),
            InviteCode.expires_at > now,
        )
        .values(used_at=now, used_by=user_id)
        .returning(InviteCode.id)
    )
    if hit is None:
        raise AccountError("INVITE_INVALID", "邀请码已被使用或已过期，请换一个邀请码重新注册")


async def list_invite_codes(db: AsyncSession, user: User) -> list[InviteCode]:
    rows = await db.scalars(
        select(InviteCode)
        .where(InviteCode.created_by == user.id)
        .order_by(InviteCode.created_at.desc(), InviteCode.id.desc())
    )
    return list(rows)


async def invite_quota_left(db: AsyncSession, user: User) -> int | None:
    """剩余可生成数；管理员不限，返回 None。作废的、过期没用的码退还名额。"""
    if user.role == "admin":
        return None
    now = _now()
    used = await db.scalar(
        select(func.count())
        .select_from(InviteCode)
        .where(
            InviteCode.created_by == user.id,
            InviteCode.revoked_at.is_(None),
            (InviteCode.used_at.isnot(None)) | (InviteCode.expires_at > now),
        )
    )
    return max(get_settings().invite_quota_per_user - int(used or 0), 0)


async def create_invite_code(db: AsyncSession, user: User) -> InviteCode:
    if user.role != "admin" and primary_binding(user) is None:
        raise AccountError("INVITE_FORBIDDEN", "绑定 EA 账号后才能生成邀请码", 403)
    # 锁住自己的用户行再数名额：同一个人并发点「生成」时排队，名额不会被多算
    await lock_user(db, user.id)
    left = await invite_quota_left(db, user)
    if left is not None and left <= 0:
        raise AccountError("INVITE_QUOTA", "邀请码名额已用完")
    # 32^8 种组合，撞码几乎不可能；先查一下，提交时真撞了再让用户重试
    for _ in range(5):
        raw = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        if await db.scalar(select(InviteCode.id).where(InviteCode.code == code)) is None:
            break
    else:
        raise AccountError("INVITE_RETRY", "生成失败，请重试", 500)
    row = InviteCode(
        code=code,
        created_by=user.id,
        expires_at=_now() + timedelta(days=get_settings().invite_ttl_days),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AccountError("INVITE_RETRY", "生成失败，请重试", 500) from e
    await db.refresh(row)
    return row


async def revoke_invite_code(db: AsyncSession, user: User, invite_id: int) -> None:
    row = await db.get(InviteCode, invite_id)
    if row is None or row.created_by != user.id:
        raise NotFoundError("邀请码")
    if row.used_at is None and row.revoked_at is None:
        row.revoked_at = _now()
        await db.commit()


# ===== 注册（后台任务） =====


async def process_register_request(
    session_factory: SessionFactory,
    *,
    email: str,
    mode: str,
    invite_id: int | None,
    ip: str | None,
) -> None:
    """注册请求的后台部分。mode=ea 先按邮箱反查 EA 号；mode=plain 用任意邮箱注册、之后再绑 EA。"""
    try:
        if not await _mail_allowed(email):
            logger.info("注册信频率超限，跳过")
            return
        if invite_id is not None and not await _invite_mail_allowed(invite_id):
            logger.info("邀请码 {} 今天触发的注册信已达上限，跳过", invite_id)
            return
        async with session_factory() as db:
            message = await _build_register_mail(
                db, email=email, mode=mode, invite_id=invite_id, ip=ip
            )
        if message is not None:
            await get_mail_sender().send(message)
    except Exception as e:
        logger.exception("注册请求处理失败: {!r}", e)


async def _build_register_mail(  # noqa: PLR0911 按情形逐个返回比嵌套分支好读
    db: AsyncSession, *, email: str, mode: str, invite_id: int | None, ip: str | None
) -> MailMessage | None:
    settings = get_settings()
    meta = RequestMeta.now(ip)
    ttl = settings.verify_link_ttl_hours
    login_url, forgot_url = _site("/login"), _site("/forgot-password")

    if mode == "ea":
        match = await lookup_ea_by_email(db, email)
        if match is None:
            # 不是 EA 账号邮箱：不发信。页面会提示改用其他邮箱注册
            return None
        binding = await _active_binding(db, match.persona_id)
        if binding is not None:
            if binding.user.status == "legacy":
                token = await _create_verification(
                    db,
                    kind="claim",
                    email=email,
                    ttl_hours=ttl,
                    user_id=binding.user_id,
                    payload={
                        "persona_id": match.persona_id,
                        "ea_user_id": match.ea_user_id,
                        "display_name": match.display_name,
                    },
                    ip=ip,
                )
                return templates.claim_legacy(
                    to=email,
                    persona_name=match.display_name,
                    url=_site(f"/verify#token={token}"),
                    ttl_hours=ttl,
                    meta=meta,
                )
            return templates.already_registered(
                to=email,
                persona_name=match.display_name,
                login_url=login_url,
                forgot_url=forgot_url,
                meta=meta,
            )
        if await _user_by_email(db, email) is not None:
            return templates.already_registered(
                to=email, persona_name=None, login_url=login_url, forgot_url=forgot_url, meta=meta
            )
        if settings.registration_invite_required and invite_id is None:
            logger.info("EA 邮箱注册缺少邀请码，跳过")
            return None
        token = await _create_verification(
            db,
            kind="register",
            email=email,
            ttl_hours=ttl,
            payload={
                "mode": "ea",
                "persona_id": match.persona_id,
                "ea_user_id": match.ea_user_id,
                "display_name": match.display_name,
                "invite_id": invite_id,
            },
            ip=ip,
        )
        return templates.register_ea(
            to=email,
            persona_name=match.display_name,
            url=_site(f"/verify#token={token}"),
            ttl_hours=ttl,
            meta=meta,
        )

    # mode == "plain"
    if await _user_by_email(db, email) is not None:
        return templates.already_registered(
            to=email, persona_name=None, login_url=login_url, forgot_url=forgot_url, meta=meta
        )
    if settings.registration_invite_required and invite_id is None:
        logger.info("其他邮箱注册缺少邀请码，跳过")
        return None
    token = await _create_verification(
        db,
        kind="register",
        email=email,
        ttl_hours=ttl,
        payload={"mode": "plain", "invite_id": invite_id},
        ip=ip,
    )
    return templates.register_plain(
        to=email, url=_site(f"/verify#token={token}"), ttl_hours=ttl, meta=meta
    )


# ===== 找回密码、补邮箱（后台任务） =====


async def process_reset_request(
    session_factory: SessionFactory, *, email: str, ip: str | None
) -> None:
    try:
        if not await _mail_allowed(email):
            return
        async with session_factory() as db:
            user = await db.scalar(
                select(User)
                .options(selectinload(User.ea_bindings))
                .where(func.lower(User.email) == email)
            )
            # 只给有 EA 绑定的正常账号发：本地管理员不走邮箱找回，邮箱失陷不能等于平台管理员失陷
            if (
                user is None
                or user.status != "active"
                or user.is_frozen
                or not user.is_active
                or primary_binding(user) is None
            ):
                return
            ttl = get_settings().reset_link_ttl_hours
            token = await _create_verification(
                db, kind="reset", email=email, ttl_hours=ttl, user_id=user.id, ip=ip
            )
        await get_mail_sender().send(
            templates.reset_password(
                to=email,
                url=_site(f"/verify#token={token}"),
                ttl_hours=ttl,
                meta=RequestMeta.now(ip),
            )
        )
    except Exception as e:
        logger.exception("找回密码请求处理失败: {!r}", e)


async def process_set_email_request(
    session_factory: SessionFactory, *, user_id: int, email: str, ip: str | None
) -> None:
    """旧账号（legacy）登录状态下补邮箱。邮箱已被占用时给那个邮箱发“账号已存在”。"""
    try:
        if not await _mail_allowed(email):
            return
        meta = RequestMeta.now(ip)
        async with session_factory() as db:
            user = await db.scalar(
                select(User).options(selectinload(User.ea_bindings)).where(User.id == user_id)
            )
            if user is None or user.status != "legacy":
                return
            if await _user_by_email(db, email) is not None:
                message = templates.already_registered(
                    to=email,
                    persona_name=None,
                    login_url=_site("/login"),
                    forgot_url=_site("/forgot-password"),
                    meta=meta,
                )
            else:
                primary = primary_binding(user)
                ttl = get_settings().verify_link_ttl_hours
                token = await _create_verification(
                    db, kind="set_email", email=email, ttl_hours=ttl, user_id=user.id, ip=ip
                )
                message = templates.set_email(
                    to=email,
                    persona_name=(primary.display_name if primary else None) or "你的 EA 账号",
                    url=_site(f"/verify#token={token}"),
                    ttl_hours=ttl,
                    meta=meta,
                )
        await get_mail_sender().send(message)
    except Exception as e:
        logger.exception("补邮箱请求处理失败: {!r}", e)


async def send_password_changed(email: str, ip: str | None) -> None:
    try:
        await get_mail_sender().send(
            templates.password_changed(
                to=email, forgot_url=_site("/forgot-password"), meta=RequestMeta.now(ip)
            )
        )
    except Exception as e:
        logger.warning("密码修改通知发送失败: {!r}", e)


# ===== 打开、确认验证链接 =====


@dataclass(frozen=True)
class VerificationInfo:
    kind: str
    email: str
    persona_name: str | None
    mode: str | None


async def get_verification_info(db: AsyncSession, token: str) -> VerificationInfo:
    """页面打开链接时调用，只读，不消耗 token。"""
    row = await _live_verification(db, token)
    payload = row.payload or {}
    persona_name = payload.get("display_name")
    if row.kind in ("reset", "set_email") and row.user_id is not None:
        user = await db.scalar(
            select(User).options(selectinload(User.ea_bindings)).where(User.id == row.user_id)
        )
        primary = primary_binding(user) if user else None
        persona_name = primary.display_name if primary else None
    return VerificationInfo(
        kind=row.kind, email=row.email, persona_name=persona_name, mode=payload.get("mode")
    )


async def confirm_verification(db: AsyncSession, token: str, password: str) -> User:
    """提交密码：消耗 token，并在同一事务里完成注册 / 认领 / 重置 / 补邮箱。返回要登录的账号。"""
    validate_password(password)
    try:
        row = await _consume_verification(db, token)
        if row.kind == "register":
            user = await _finish_register(db, row, password)
        elif row.kind in ("claim", "set_email"):
            user = await _finish_claim(db, row, password)
        elif row.kind == "reset":
            user = await _finish_reset(db, row, password)
        else:
            raise AccountError("LINK_INVALID", "链接无效或已过期，请重新申请", 404)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.info("确认验证链接时撞唯一约束: {!r}", e)
        raise AccountError(
            "ACCOUNT_CONFLICT", "这个邮箱或 EA 账号已经被其他账号使用，请直接登录或找回密码"
        ) from e
    except Exception:
        await db.rollback()
        raise
    loaded = await db.scalar(
        select(User)
        .options(selectinload(User.ea_bindings))
        .where(User.id == user.id)
        .execution_options(populate_existing=True)
    )
    assert loaded is not None
    return loaded


async def _unique_username(db: AsyncSession, preferred: str | None) -> str:
    if preferred and await db.scalar(select(User.id).where(User.username == preferred)) is None:
        return preferred
    while True:
        name = f"user_{secrets.token_hex(5)}"
        if await db.scalar(select(User.id).where(User.username == name)) is None:
            return name


async def _finish_register(db: AsyncSession, row: EmailVerification, password: str) -> User:
    payload = row.payload or {}
    now = _now()
    mode = payload.get("mode")
    persona_id = payload.get("persona_id")
    if mode == "ea" and await _active_binding(db, int(persona_id)) is not None:
        raise AccountError("ACCOUNT_CONFLICT", "这个 EA 账号已经绑定在其他账号上，请直接登录")
    user = User(
        username=await _unique_username(db, f"persona_{persona_id}" if mode == "ea" else None),
        local_password_hash=hash_password(password),
        email=row.email,
        email_verified_at=now,
        status="active" if mode == "ea" else "pending_binding",
        role="user",
        is_active=True,
        is_frozen=False,
        last_login_at=now,
    )
    db.add(user)
    await db.flush()
    if mode == "ea":
        db.add(
            EaBinding(
                user_id=user.id,
                persona_id=int(persona_id),
                ea_user_id=payload.get("ea_user_id"),
                display_name=payload.get("display_name"),
                verified_via="email",
                is_primary=True,
                is_frozen=False,
                last_verified_at=now,
            )
        )
    if payload.get("invite_id"):
        await _consume_invite(db, int(payload["invite_id"]), user.id)
    await db.flush()
    return user


async def _finish_claim(db: AsyncSession, row: EmailVerification, password: str) -> User:
    """claim（EA 邮箱认领旧账号）和 set_email（旧账号登录后补邮箱）都落在这里。"""
    # 锁住旧账号再检查：同一个旧账号可能同时有认领信和补邮箱信（发到不同邮箱），
    # 或者正被另一个账号用 remid 认领，只能有一个成功
    user = await lock_user(db, row.user_id) if row.user_id is not None else None
    if user is None or user.status != "legacy":
        raise AccountError("LINK_INVALID", "这个账号已经设置过邮箱，请直接登录", 404)
    payload = row.payload or {}
    if row.kind == "claim":
        binding = await _active_binding(db, int(payload["persona_id"]))
        if binding is None or binding.user_id != user.id:
            raise AccountError("LINK_INVALID", "链接无效或已过期，请重新申请", 404)
        binding.verified_via = "email"
        binding.ea_user_id = payload.get("ea_user_id") or binding.ea_user_id
    now = _now()
    user.email = row.email
    user.email_verified_at = now
    user.local_password_hash = hash_password(password)
    user.status = "active"
    user.last_login_at = now
    await db.flush()
    # 旧会话可能是别人拿 remid 登的，认领后全部作废
    await bump_token_version(db, user)
    return user


async def _finish_reset(db: AsyncSession, row: EmailVerification, password: str) -> User:
    user = await lock_user(db, row.user_id) if row.user_id is not None else None
    if user is None or user.status != "active" or user.is_frozen or not user.is_active:
        raise AccountError("LINK_INVALID", "链接无效或已过期，请重新申请", 404)
    user.local_password_hash = hash_password(password)
    user.last_login_at = _now()
    await db.flush()
    await bump_token_version(db, user)
    return user


# ===== 登录、改密码、登出所有设备 =====


async def login_with_email(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(
        select(User).options(selectinload(User.ea_bindings)).where(func.lower(User.email) == email)
    )
    # 不管账号在不在都做一次 bcrypt，响应时间不泄露邮箱是否注册过
    password_ok = verify_password_timing_safe(password, user.local_password_hash if user else None)
    if (
        user is None
        or not password_ok
        or user.status not in ("active", "pending_binding")
        or not user.is_active
        or user.is_frozen
    ):
        raise UnauthorizedError("邮箱或密码错误")
    user.last_login_at = _now()
    await db.commit()
    return user


async def change_password(db: AsyncSession, user: User, current: str, new: str) -> None:
    validate_password(new)
    # 锁住再校验当前密码：两个改密码请求并发时，后一个要用前一个改完的密码校验
    locked = await lock_user(db, user.id)
    if locked is None or not verify_password(current, locked.local_password_hash):
        raise AccountError("PASSWORD_WRONG", "当前密码不正确")
    locked.local_password_hash = hash_password(new)
    await db.flush()
    await bump_token_version(db, locked)
    await db.commit()


async def revoke_sessions(db: AsyncSession, user: User) -> None:
    await bump_token_version(db, user)
    await db.commit()


# ===== 清理 =====

CLEANUP_INTERVAL_SECONDS = 3600


async def cleanup_once(db: AsyncSession) -> None:
    now = _now()
    settings = get_settings()
    stale = now - timedelta(hours=settings.pending_binding_ttl_hours)
    # 只清理从没绑过 EA 的：绑过又解绑的老账号也会是 pending_binding，不能删
    pending = await db.scalars(
        select(User.id).where(
            User.status == "pending_binding",
            User.created_at < stale,
            ~exists().where(EaBinding.user_id == User.id),
        )
    )
    ids = list(pending)
    if ids:
        await db.execute(delete(User).where(User.id.in_(ids)))
        logger.info("清理超时未绑定 EA 的账号 {} 个", len(ids))
    await db.execute(
        delete(EmailVerification).where(EmailVerification.expires_at < now - timedelta(days=1))
    )
    await db.commit()


async def account_cleanup_poller(session_factory: SessionFactory) -> None:
    while True:
        try:
            async with session_factory() as db:
                await cleanup_once(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("账号清理失败: {!r}", e)
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
