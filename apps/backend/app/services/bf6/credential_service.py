"""BF6 查询凭据：后台保存、按需刷新、换会话。

- 管理员保存时立即用这组凭据向 EA 刷新一次，EA 不认就不保存，免得存进一组用不了的值。
- refresh token 一刷新就轮换。刷新放在独立事务里，对唯一那一行加 ``FOR UPDATE``，
  同一时刻只有一个刷新请求在用旧值；锁内再检查一次，后来的直接用前一个刷出来的 access token。
- BF6 会话 JWT 只放进程内存：约 4 小时有效，丢了用 access token 再换一个即可。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
import uuid
from collections.abc import Coroutine
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, EAApiError
from app.core.cache import get_cache
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


# 已经向 EA 换到新 token、还没确认写进库的任务。EA 一轮换旧值就作废，这些任务不能随调用方
# 一起被取消（客户端断开、停机时 poller 被 cancel），停机前要等它们写完再关数据库
_pending: set[asyncio.Task[Any]] = set()
_refreshing: asyncio.Task[str] | None = None
_PERSIST_ATTEMPTS = 3
# 待补写的 grant 存成 Redis hash：每份一个字段，各自增删，互不覆盖
_UNSAVED_KEY = "bf6:unsaved_grants"
_UNSAVED_TTL_SECONDS = 9 * 86400
_AUDIT_ACTION = "bf6_credentials_update"


def _detach[T](coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    task = asyncio.create_task(coro)
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


@dataclass(frozen=True)
class _AdminWrite:
    """管理员保存的元数据：补写时连同更新人、审计一起写进去。"""

    actor_id: int
    persona_id: int
    ip: str | None
    secret_changed: bool
    write_id: str


@dataclass(frozen=True)
class _Unsaved:
    """EA 已经轮换、还没确认写进库的 grant。

    后台刷新得到的（admin 为 None）：base_generation 是换 token 时库里的版本，补写时版本没变才写；
    变了说明期间有人写进了更新的凭据，或者这份其实已经写进去、又被下一次刷新轮换掉，这份作废。
    管理员保存得到的：总是覆盖库里的值，除非已经写过，或之后又有管理员保存了更新的凭据。
    """

    grant: bf6.TokenGrant
    base_generation: int
    created_at: float
    client_secret: str | None = None
    admin: _AdminWrite | None = None

    @property
    def key(self) -> str:
        # 每份 grant 的 refresh token 都不同，取摘要作 Redis 字段名，不暴露 token 本身
        return hashlib.sha256(self.grant.refresh_token.encode()).hexdigest()[:32]

    def dump(self) -> str:
        return get_cipher().encrypt(
            json.dumps(
                {
                    "grant": asdict(self.grant),
                    "base_generation": self.base_generation,
                    "created_at": self.created_at,
                    "client_secret": self.client_secret,
                    "admin": asdict(self.admin) if self.admin else None,
                }
            )
        )

    @classmethod
    def load(cls, blob: str) -> _Unsaved:
        data = json.loads(get_cipher().decrypt(blob))
        admin = data["admin"]
        return cls(
            grant=bf6.TokenGrant(**data["grant"]),
            base_generation=data["base_generation"],
            created_at=data["created_at"],
            client_secret=data["client_secret"],
            admin=_AdminWrite(**admin) if admin else None,
        )


# 本进程里待补写的 grant；同时加密存一份到 Redis，进程退出、换进程也能接着补写
_unsaved: dict[str, _Unsaved] = {}


async def _stash(unsaved: _Unsaved) -> None:
    try:
        cache = await get_cache()
        await cache.hash_set(_UNSAVED_KEY, unsaved.key, unsaved.dump(), ttl=_UNSAVED_TTL_SECONDS)
    except (RedisError, OSError) as e:
        logger.error("BF6 待补写的 token 存不进 Redis，只留在进程内存里: {!r}", e)


async def _remember(unsaved: _Unsaved) -> None:
    _unsaved[unsaved.key] = unsaved
    await _stash(unsaved)


async def _forget(unsaved: _Unsaved) -> None:
    """unsaved 已写进库或已作废。只删这一份，别的进程、别的请求留下的不动。"""
    _unsaved.pop(unsaved.key, None)
    try:
        await (await get_cache()).hash_delete(_UNSAVED_KEY, unsaved.key)
    except (RedisError, OSError) as e:
        logger.warning("BF6 清理 Redis 里待补写的 token 失败: {!r}", e)


async def _all_unsaved() -> list[_Unsaved]:
    """本进程内存里的和 Redis 里的合在一起，按换到 token 的先后排。"""
    found = dict(_unsaved)
    try:
        stored = await (await get_cache()).hash_all(_UNSAVED_KEY)
    except (RedisError, OSError) as e:
        logger.error("BF6 读不到 Redis 里待补写的 token: {!r}", e)
        stored = {}
    for key, blob in stored.items():
        if key in found:
            continue
        try:
            found[key] = _Unsaved.load(blob)
        except (ValueError, KeyError, TypeError) as e:
            logger.error("BF6 Redis 里待补写的 token 解不开，丢弃: {!r}", e)
            with contextlib.suppress(RedisError, OSError):
                await (await get_cache()).hash_delete(_UNSAVED_KEY, key)
    return sorted(found.values(), key=lambda u: u.created_at)


async def drain(timeout: float = 30) -> None:
    """停机时调用：等进行中的刷新把新 token 写完；等不到就确保它在 Redis 里留了一份。"""
    if _pending:
        _done, pending = await asyncio.wait(set(_pending), timeout=timeout)
        if pending:
            logger.error("BF6 停机时还有 {} 个刷新任务没写完", len(pending))
    for unsaved in list(_unsaved.values()):
        await _stash(unsaved)
        logger.error("BF6 有一份新 token 没写进库，已存进 Redis，下次刷新时补写")


def _write(row: Bf6Credential, unsaved: _Unsaved) -> None:
    if unsaved.client_secret is not None:
        row.encrypted_client_secret = get_cipher().encrypt(unsaved.client_secret)
    _apply_grant(row, unsaved.grant, datetime.now(UTC))
    row.generation += 1


def _write_admin(db: AsyncSession, row: Bf6Credential, unsaved: _Unsaved) -> None:
    """管理员保存：凭据、更新人、审计放进同一个事务。"""
    admin = unsaved.admin
    assert admin is not None
    _write(row, unsaved)
    row.updated_by = admin.actor_id
    db.add(
        AuditLog(
            user_id=admin.actor_id,
            acting_persona_id=admin.persona_id,
            game=AUDIT_GAME,
            action=_AUDIT_ACTION,
            payload={
                "client_secret_changed": admin.secret_changed,
                "refresh_expires_at": row.refresh_expires_at.isoformat()
                if row.refresh_expires_at
                else None,
                "write_id": admin.write_id,
                "issued_at": unsaved.created_at,
            },
            result="success",
            ip=admin.ip,
        )
    )


async def _admin_superseded(db: AsyncSession, unsaved: _Unsaved) -> bool:
    """这份管理员凭据不该再写：已经写过（commit 成功但没收到确认），或之后又有管理员保存了更新的。

    凭据和审计在同一个事务里，看审计就知道写没写进去。
    """
    admin = unsaved.admin
    assert admin is not None
    payloads = await db.scalars(
        select(AuditLog.payload)
        .where(AuditLog.game == AUDIT_GAME, AuditLog.action == _AUDIT_ACTION)
        .order_by(AuditLog.id.desc())
        .limit(10)
    )
    for p in payloads:
        if p.get("write_id") == admin.write_id:
            return True
        issued = p.get("issued_at")
        if isinstance(issued, int | float) and issued > unsaved.created_at:
            return True
    return False


async def _persist_grant(session_factory: SessionFactory, unsaved: _Unsaved) -> None:
    """后台刷新的 commit 失败后，用同一份 grant 重试——旧 refresh token 已经作废，不能再拿去换。

    重试都失败时 grant 还留在内存和 Redis 里，下次刷新先补写它，不会再用旧值。
    """
    for attempt in range(1, _PERSIST_ATTEMPTS + 1):
        try:
            async with session_factory() as db:
                row = await db.get(
                    Bf6Credential, BF6_CREDENTIAL_ID, with_for_update=True, populate_existing=True
                )
                if row is None:
                    raise Bf6NotConfiguredError("BF6 凭据已被删除")
                if row.generation == unsaved.base_generation:
                    _write(row, unsaved)
                    await db.commit()
                elif (
                    row.generation == unsaved.base_generation + 1
                    and get_cipher().decrypt(row.encrypted_refresh_token)
                    == unsaved.grant.refresh_token
                ):
                    pass  # 上一次 commit 其实成功了，只是没收到确认
                else:
                    logger.warning("BF6 待补写的 token 已被后来写入的凭据取代，丢弃")
            await _forget(unsaved)
            return
        except (SQLAlchemyError, OSError) as e:
            if attempt == _PERSIST_ATTEMPTS:
                logger.critical(
                    "BF6 refresh token 已轮换但写库失败 {} 次，新值留在内存和 Redis 里，"
                    "下次刷新时补写: {!r}",
                    attempt,
                    e,
                )
                raise
            logger.error("BF6 新 token 写库失败（第 {} 次），稍后重试: {!r}", attempt, e)
            await asyncio.sleep(attempt)


async def _recover_unsaved(db: AsyncSession, row: Bf6Credential) -> bool:
    """把之前没写进库的 grant 按先后补写（调用方已锁住这一行）。补写了返回 True。"""
    pending = await _all_unsaved()
    if not pending:
        return False
    applied = admin_applied = False
    for unsaved in pending:
        if unsaved.admin is not None:
            if not await _admin_superseded(db, unsaved):
                _write_admin(db, row, unsaved)
                applied = admin_applied = True
        elif row.generation == unsaved.base_generation:
            _write(row, unsaved)
            applied = True
    if applied:
        await db.commit()
        logger.info("BF6 已补写上次没写进库的 token")
    for unsaved in pending:
        await _forget(unsaved)
    if admin_applied:
        _session.clear()
    return applied


def _validate_refresh_token(refresh_token: str) -> None:
    # 报错只说原因，不回显输入
    if not 20 <= len(refresh_token) <= 16384:
        raise AppError(400, "BF6_CREDENTIAL_INVALID", "refresh token 长度不对")
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


@dataclass(frozen=True)
class _SaveRequest:
    """管理员保存的全部输入。提前从请求里取出来，保存任务不依赖请求本身还在。"""

    refresh_token: str
    client_secret: str
    admin: _AdminWrite


async def _store_admin_grant(
    session_factory: SessionFactory, req: _SaveRequest, grant: bf6.TokenGrant
) -> None:
    """管理员的新凭据总是覆盖库里的。写库前先备份：写库失败、卡住或停机，下次刷新都能补写。"""
    unsaved = _Unsaved(grant, 0, time.time(), req.client_secret, req.admin)
    await _remember(unsaved)
    cipher = get_cipher()
    for attempt in range(1, _PERSIST_ATTEMPTS + 1):
        try:
            async with session_factory() as db:
                insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
                # 第一次保存时还没有这一行，FOR UPDATE 锁不住不存在的行：先占位再锁
                await db.execute(
                    insert(Bf6Credential)
                    .values(
                        id=BF6_CREDENTIAL_ID,
                        encrypted_client_secret=cipher.encrypt(req.client_secret),
                        encrypted_refresh_token=cipher.encrypt(grant.refresh_token),
                    )
                    .on_conflict_do_nothing(index_elements=[Bf6Credential.id])
                )
                row = await db.get(
                    Bf6Credential, BF6_CREDENTIAL_ID, with_for_update=True, populate_existing=True
                )
                assert row is not None
                # 别的进程补写过，或上一次 commit 成功但没收到确认
                if not await _admin_superseded(db, unsaved):
                    _write_admin(db, row, unsaved)
                    await db.commit()
                break
        except (SQLAlchemyError, OSError) as e:
            if attempt == _PERSIST_ATTEMPTS:
                logger.critical(
                    "BF6 后台保存的凭据已在 EA 轮换但写库失败 {} 次，新值留在内存和 Redis 里，"
                    "下次刷新时补写: {!r}",
                    attempt,
                    e,
                )
                raise
            logger.error("BF6 后台保存的凭据写库失败（第 {} 次），稍后重试: {!r}", attempt, e)
            await asyncio.sleep(attempt)
    await _forget(unsaved)
    # 新凭据生效，旧的网关会话作废
    _session.clear()


async def _verify_and_store(session_factory: SessionFactory, req: _SaveRequest) -> None:
    try:
        grant = await bf6.refresh_access_token(
            req.client_secret, req.refresh_token, now=int(time.time())
        )
    except bf6.Bf6CredentialError as e:
        raise AppError(400, "BF6_CREDENTIAL_REJECTED", str(e)) from e
    except bf6.Bf6Error as e:
        raise EAApiError("BF6_UPSTREAM_ERROR", f"验证凭据时 EA 没有正常响应：{e}") from e
    await _store_admin_grant(session_factory, req, grant)


async def save_credentials(
    session_factory: SessionFactory,
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
    _validate_refresh_token(refresh_token)
    if client_secret is not None and len(client_secret) > 512:
        raise AppError(400, "BF6_CREDENTIAL_INVALID", "client secret 长度不对")

    async with session_factory() as db:
        if client_secret is None:
            row = await db.get(Bf6Credential, BF6_CREDENTIAL_ID)
            if row is None:
                raise AppError(400, "BF6_CREDENTIAL_INVALID", "首次保存需要填写 client secret")
            client_secret = get_cipher().decrypt(row.encrypted_client_secret)
        persona = await db.scalar(
            select(EaBinding.persona_id).where(
                EaBinding.user_id == actor.id, EaBinding.is_primary.is_(True)
            )
        )
    req = _SaveRequest(
        refresh_token=refresh_token,
        client_secret=client_secret,
        admin=_AdminWrite(
            actor_id=actor.id,
            persona_id=persona or 0,
            ip=ip,
            secret_changed=secret_changed,
            write_id=uuid.uuid4().hex,
        ),
    )

    # EA 一旦轮换，原 refresh token 就作废：保存任务不随请求取消
    await asyncio.shield(_detach(_verify_and_store(session_factory, req)))
    async with session_factory() as db:
        return await get_status(db)


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


async def _lock_row(db: AsyncSession) -> Bf6Credential:
    row = await db.get(
        Bf6Credential, BF6_CREDENTIAL_ID, with_for_update=True, populate_existing=True
    )
    if row is None:
        raise Bf6NotConfiguredError("后台还没有填写 BF6 凭据")
    return row


async def _refresh(session_factory: SessionFactory, max_age: int | None) -> str:
    try:
        async with session_factory() as db:
            row = await _lock_row(db)
            # 上次没写进库的新 token 要先补上，库里的旧值已经作废
            if await _recover_unsaved(db, row):
                row = await _lock_row(db)
            # 等锁期间别的进程可能已经刷新过
            cached = _cached_access(row, time.time(), max_age)
            if cached:
                return cached
            cipher = get_cipher()
            grant = await bf6.refresh_access_token(
                cipher.decrypt(row.encrypted_client_secret),
                cipher.decrypt(row.encrypted_refresh_token),
                now=int(time.time()),
            )
            unsaved = _Unsaved(grant, row.generation, time.time())
            await _remember(unsaved)
            _write(row, unsaved)
            try:
                await db.commit()
            except (SQLAlchemyError, OSError) as e:
                logger.error("BF6 新 token 写库失败，改用新会话重试: {!r}", e)
                await db.rollback()
                await _persist_grant(session_factory, unsaved)
            else:
                await _forget(unsaved)
    except Bf6NotConfiguredError:
        raise
    except bf6.Bf6Error as e:
        logger.warning("BF6 access token 刷新失败: {}", e)
        await _record_error(session_factory, str(e))
        raise
    logger.info("BF6 access token 已刷新，refresh token 有效期到 {}", _ts(grant.refresh_expires_at))
    return grant.access_token


async def get_access_token(session_factory: SessionFactory, *, max_age: int | None = None) -> str:
    global _refreshing  # noqa: PLW0603
    async with session_factory() as db:
        row = await db.get(Bf6Credential, BF6_CREDENTIAL_ID)
        if row is None:
            raise Bf6NotConfiguredError("后台还没有填写 BF6 凭据")
        cached = _cached_access(row, time.time(), max_age)
        if cached:
            return cached

    # 进程内同一时刻只发起一次刷新，其余请求等它的结果；跨进程靠行锁
    if _refreshing is None or _refreshing.done():
        _refreshing = _detach(_refresh(session_factory, max_age))
    return await asyncio.shield(_refreshing)


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
