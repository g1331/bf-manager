"""BF6 查询凭据：后台保存、按需刷新、换会话。

- 管理员保存时立即用这组凭据向 EA 刷新一次，EA 不认就不保存，免得存进一组用不了的值。
- refresh token 一刷新就轮换。刷新放在独立事务里，对唯一那一行加 ``FOR UPDATE``，
  同一时刻只有一个刷新请求在用旧值；锁内再检查一次，后来的直接用前一个刷出来的 access token。
- BF6 会话 JWT 只放进程内存：约 4 小时有效，丢了用 access token 再换一个即可。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, EAApiError
from app.core.security import get_cipher
from app.domain.games.bf6 import client as bf6
from app.models import AuditLog, EaBinding, User
from app.models.bf6_credential import BF6_CREDENTIAL_ID, Bf6Credential
from app.services.account_service import SessionFactory

AUDIT_GAME = "bf6"
# access token 剩不到这么久就提前刷新，避免请求途中过期
_ACCESS_MARGIN_SECONDS = 600
_SESSION_MARGIN_SECONDS = 120
# refresh token 绝对 9 天过期、每次刷新重新计时：闲置超过 9 天就只能重新签发。
# 后台每天主动刷新一次，连续失败也有一周多的时间处理
_REFRESH_EVERY_SECONDS = 86400
_POLL_INTERVAL_SECONDS = 3600


class Bf6NotConfiguredError(bf6.Bf6CredentialError):
    """后台还没填凭据。"""


@dataclass(frozen=True)
class CredentialStatus:
    configured: bool
    refresh_expires_at: datetime | None = None
    access_expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    updated_at: datetime | None = None


def _ts(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value else None


def _aware(value: datetime | None) -> datetime | None:
    # sqlite 读回来不带时区
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _status(row: Bf6Credential | None) -> CredentialStatus:
    if row is None:
        return CredentialStatus(configured=False)
    return CredentialStatus(
        configured=True,
        refresh_expires_at=_aware(row.refresh_expires_at),
        access_expires_at=_aware(row.access_expires_at),
        last_refreshed_at=_aware(row.last_refreshed_at),
        last_error=row.last_error,
        last_error_at=_aware(row.last_error_at),
        updated_at=_aware(row.updated_at),
    )


async def get_status(db: AsyncSession) -> CredentialStatus:
    return _status(await db.get(Bf6Credential, BF6_CREDENTIAL_ID, populate_existing=True))


def _apply_grant(row: Bf6Credential, grant: bf6.TokenGrant, now: datetime) -> None:
    cipher = get_cipher()
    row.encrypted_refresh_token = cipher.encrypt(grant.refresh_token)
    row.refresh_expires_at = _ts(grant.refresh_expires_at)
    row.encrypted_access_token = cipher.encrypt(grant.access_token)
    row.access_expires_at = _ts(grant.access_expires_at)
    row.last_refreshed_at = now
    row.last_error = None
    row.last_error_at = None


async def save_credentials(
    db: AsyncSession,
    *,
    refresh_token: str,
    client_secret: str | None,
    actor: User,
    ip: str | None = None,
) -> CredentialStatus:
    """保存后台填写的凭据。client_secret 留空表示沿用已保存的值（只换 refresh token 的情况）。"""
    refresh_token = refresh_token.strip()
    client_secret = (client_secret or "").strip() or None
    secret_changed = client_secret is not None
    claims = bf6.jwt_claims(refresh_token)
    if not claims:
        raise AppError(400, "BF6_CREDENTIAL_INVALID", "refresh token 格式不对，应为三段式 JWT")
    if claims.get("azp") not in (None, bf6.CLIENT_ID):
        raise AppError(
            400, "BF6_CREDENTIAL_INVALID", f"这个 refresh token 不是 {bf6.CLIENT_ID} 签发的"
        )
    exp = claims.get("exp")
    if isinstance(exp, int | float) and exp <= time.time():
        raise AppError(400, "BF6_CREDENTIAL_INVALID", "这个 refresh token 已过期")

    row = await db.get(Bf6Credential, BF6_CREDENTIAL_ID, populate_existing=True)
    if client_secret is None:
        if row is None:
            raise AppError(400, "BF6_CREDENTIAL_INVALID", "首次保存需要填写 client secret")
        client_secret = get_cipher().decrypt(row.encrypted_client_secret)

    try:
        grant = await bf6.refresh_access_token(client_secret, refresh_token, now=int(time.time()))
    except bf6.Bf6CredentialError as e:
        raise AppError(400, "BF6_CREDENTIAL_REJECTED", str(e)) from e
    except bf6.Bf6Error as e:
        raise EAApiError("BF6_UPSTREAM_ERROR", f"验证凭据时 EA 没有正常响应：{e}") from e

    # 第一次保存时还没有这一行，FOR UPDATE 锁不住不存在的行：先占位再锁
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    cipher = get_cipher()
    await db.execute(
        insert(Bf6Credential)
        .values(
            id=BF6_CREDENTIAL_ID,
            encrypted_client_secret=cipher.encrypt(client_secret),
            encrypted_refresh_token=cipher.encrypt(grant.refresh_token),
        )
        .on_conflict_do_nothing(index_elements=[Bf6Credential.id])
    )
    row = await db.get(
        Bf6Credential, BF6_CREDENTIAL_ID, with_for_update=True, populate_existing=True
    )
    assert row is not None
    row.encrypted_client_secret = cipher.encrypt(client_secret)
    _apply_grant(row, grant, datetime.now(UTC))
    row.updated_by = actor.id

    persona = await db.scalar(
        select(EaBinding.persona_id).where(
            EaBinding.user_id == actor.id, EaBinding.is_primary.is_(True)
        )
    )
    db.add(
        AuditLog(
            user_id=actor.id,
            acting_persona_id=persona or 0,
            game=AUDIT_GAME,
            action="bf6_credentials_update",
            payload={
                "client_secret_changed": secret_changed,
                "refresh_expires_at": row.refresh_expires_at.isoformat()
                if row.refresh_expires_at
                else None,
            },
            result="success",
            ip=ip,
        )
    )
    await db.commit()
    # updated_at 由数据库生成，提交后已过期；异步会话里不能懒加载，显式读回
    await db.refresh(row)
    _session.clear()
    return _status(row)


async def _record_error(session_factory: SessionFactory, message: str) -> None:
    async with session_factory() as db:
        row = await db.get(Bf6Credential, BF6_CREDENTIAL_ID)
        if row is not None:
            row.last_error = message[:255]
            row.last_error_at = datetime.now(UTC)
            await db.commit()


def _cached_access(row: Bf6Credential, now: float, max_age: int | None) -> str | None:
    """库里的 access token 还能用就解密返回；max_age 指定时，上次刷新太久也视为需要刷新。"""
    if not row.encrypted_access_token:
        return None
    expires = _aware(row.access_expires_at)
    if expires is None or expires.timestamp() <= now + _ACCESS_MARGIN_SECONDS:
        return None
    if max_age is not None:
        refreshed = _aware(row.last_refreshed_at)
        if refreshed is None or refreshed.timestamp() <= now - max_age:
            return None
    return get_cipher().decrypt(row.encrypted_access_token)


async def get_access_token(session_factory: SessionFactory, *, max_age: int | None = None) -> str:
    async with session_factory() as db:
        row = await db.get(Bf6Credential, BF6_CREDENTIAL_ID)
        if row is None:
            raise Bf6NotConfiguredError("后台还没有填写 BF6 凭据")
        cached = _cached_access(row, time.time(), max_age)
        if cached:
            return cached

    try:
        async with session_factory() as db:
            row = await db.get(
                Bf6Credential, BF6_CREDENTIAL_ID, with_for_update=True, populate_existing=True
            )
            if row is None:
                raise Bf6NotConfiguredError("后台还没有填写 BF6 凭据")
            # 等锁期间别人可能已经刷新过
            cached = _cached_access(row, time.time(), max_age)
            if cached:
                return cached
            cipher = get_cipher()
            grant = await bf6.refresh_access_token(
                cipher.decrypt(row.encrypted_client_secret),
                cipher.decrypt(row.encrypted_refresh_token),
                now=int(time.time()),
            )
            _apply_grant(row, grant, datetime.now(UTC))
            try:
                await db.commit()
            except Exception:
                # EA 已经轮换，旧 refresh token 作废，新的又没存上：只能让管理员重新填
                logger.critical("BF6 refresh token 已轮换但写库失败，需要在后台重新填写凭据")
                raise
            logger.info(
                "BF6 access token 已刷新，refresh token 有效期到 {}", row.refresh_expires_at
            )
            return grant.access_token
    except Bf6NotConfiguredError:
        raise
    except bf6.Bf6Error as e:
        logger.warning("BF6 access token 刷新失败: {}", e)
        await _record_error(session_factory, str(e))
        raise


class _SessionCache:
    def __init__(self) -> None:
        self.token = ""
        self.expires_at = 0
        self.lock = asyncio.Lock()

    def clear(self) -> None:
        self.token = ""
        self.expires_at = 0


_session = _SessionCache()


async def get_session_jwt(session_factory: SessionFactory, *, renew: bool = False) -> str:
    """BF6 网关会话。renew=True 表示当前会话被网关拒绝了，换一个新的。"""
    stale = _session.token if renew else None
    if not renew and _session.token and _session.expires_at > time.time() + _SESSION_MARGIN_SECONDS:
        return _session.token
    async with _session.lock:
        # 等锁期间别的请求可能已经换好了
        if (
            _session.token
            and _session.token != stale
            and (_session.expires_at > time.time() + _SESSION_MARGIN_SECONDS)
        ):
            return _session.token
        access = await get_access_token(session_factory)
        try:
            token, expires_at = await bf6.via_jwt(access, now=int(time.time()))
        except bf6.Bf6CredentialError as e:
            await _record_error(session_factory, str(e))
            raise
        _session.token, _session.expires_at = token, expires_at
        return token


async def refresh_poller(session_factory: SessionFactory) -> None:
    """保持 refresh token 不过期：没人查询时也每天刷新一次。没填凭据时什么都不做。"""
    while True:
        try:
            await get_access_token(session_factory, max_age=_REFRESH_EVERY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Bf6NotConfiguredError:
            pass
        except Exception as e:
            # 凭据类错误已写进 last_error，后台能看到
            logger.warning("BF6 定时刷新失败: {!r}", e)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
