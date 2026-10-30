"""BF1 计时 VIP：加 V / 下 V / checkvip，以及到期自动下 V 的后台轮询。

规则在 vip_engine（纯函数）。这里负责：
- 用操作者的客户端实时拉 EA 名单和服务器状态，先按名单对账，再改记录、调 RSP；
- 行动服的 EA 写操作只在 checkvip 里发生，而且要求服内有人：空服时上下 V 会掉回普通服；
- 后台每分钟找出到期的记录，只在普通服上用授予人（不行再换本服其他管理员）的绑定凭据
  下 V，不用号池（号池账号不是私服管理员）。行动服到期的等管理员 checkvip。

记录的增删改都等 EA 调用有结果之后再写，中途失败时数据库保持原样，下次对账自愈。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError, EAApiError
from app.core import ea_metrics
from app.db.session import get_sessionmaker
from app.domain.games.bf1.client_provider import (
    ExecutorUnavailableError,
    GroupFirstBF1ClientProvider,
)
from app.domain.games.bf1.maps import operation_maps
from app.models import Server, ServerMembership, User
from app.models.bf1 import Bf1ServerVip
from app.schemas.bf1.admin import (
    TimedVipItem,
    TimedVipView,
    VipApplyFailure,
    VipApplyResult,
)
from app.services.audit_service import AuditService
from app.services.authz_service import ROLE_LEVEL, ServerAuthzService
from app.services.bf1 import vip_engine as engine
from app.services.bf1.blaze_service import get_operation_states
from app.services.bf1.card_engine import parse_state
from app.services.bf1.card_service import active_game_ids
from app.services.bf1.server_admin_service import BF1ServerAdminService
from app.services.bf1.server_service import current_game_ids

CN_TZ = ZoneInfo("Asia/Shanghai")
OPERATIONS_MODE = "BreakthroughLarge"
POLL_SECONDS = 60
# 连续的 RSP 写操作之间稍作间隔，不一口气打满 EA
EA_WRITE_INTERVAL = 0.3
BACKOFF_BASE = timedelta(minutes=1)
BACKOFF_MAX = timedelta(hours=6)

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite 读回来不带时区
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(CN_TZ).strftime("%m-%d %H:%M")


def _fmt_span(td: timedelta | None) -> str:
    if td is None:
        return "永久"
    days, hours = td.days, td.seconds // 3600
    if days and hours:
        return f"{days} 天 {hours} 小时"
    if days:
        return f"{days} 天"
    return f"{max(hours, 1)} 小时"


def _seconds_left(entry: engine.Entry, now: datetime) -> int | None:
    if entry.status == engine.ACTIVE and entry.expires_at is not None:
        return max(int((entry.expires_at - now).total_seconds()), 0)
    return int(entry.remaining.total_seconds()) if entry.remaining is not None else None


def _already_vip(res: Any) -> bool:
    return isinstance(res, str) and ("已经是VIP" in res or "AlreadyVip" in res)


def _rule_error(err: engine.VipRuleError) -> AppError:
    code = status.HTTP_409_CONFLICT if err.code == "VIP_IS_PERMANENT" else 400
    return AppError(code, err.code, err.message)


@dataclass
class VipContext:
    """一次 getFullServerDetails 里和 VIP 有关的部分"""

    server_id: int
    persisted_game_id: str | None
    name: str | None
    operation: bool
    map_name: str
    # RSP 轮换的地图代号，下标即 chooseLevel 的 levelIndex
    rotation: list[str]
    soldiers: int
    vips: dict[int, str | None]

    @property
    def campaign_start(self) -> bool:
        return (
            self.operation
            and bool(self.map_name)
            and operation_maps(self.map_name)[0] == self.map_name
        )


async def fetch_context(client: Any, game_id: int) -> VipContext:
    res = await client.getFullServerDetails(game_id)
    if not isinstance(res, dict):
        raise EAApiError(code="EA_SERVER_DETAIL_FAILED", message=str(res)[:256])
    raw = res.get("result") or {}
    info = raw.get("serverInfo") or {}
    rsp = raw.get("rspInfo") or {}
    try:
        server_id = int((rsp.get("server") or {}).get("serverId") or info.get("serverId") or 0)
    except (TypeError, ValueError):
        server_id = 0
    if not server_id:
        raise EAApiError(
            code="EA_RSP_SERVER_ID_MISSING", message="无法获取该服务器的 RSP serverId，请稍后重试"
        )
    # 名单缺失时宁可报错也不能当成空名单，否则对账会把所有托管记录当成被人下了 V
    if not isinstance(rsp.get("vipList"), list):
        raise EAApiError(code="EA_VIP_LIST_MISSING", message="拿不到这台服的 VIP 名单，请稍后重试")
    vips: dict[int, str | None] = {}
    for item in rsp["vipList"]:
        try:
            pid = int(item.get("personaId") or 0)
        except (TypeError, ValueError):
            continue
        if pid:
            vips[pid] = item.get("displayName")
    state = parse_state(info)
    soldiers = int(((info.get("slots") or {}).get("Soldier") or {}).get("current") or 0)
    persisted = info.get("persistedGameId") or raw.get("persistedGameId") or info.get("guid")
    return VipContext(
        server_id=server_id,
        persisted_game_id=persisted,
        name=info.get("name"),
        operation=state.mode == OPERATIONS_MODE,
        map_name=state.map,
        rotation=state.maps,
        soldiers=soldiers,
        vips=vips,
    )


def _entry(row: Bf1ServerVip) -> engine.Entry:
    return engine.Entry(
        status=row.status,
        expires_at=_aware(row.expires_at),
        remaining=(
            timedelta(seconds=row.remaining_seconds) if row.remaining_seconds is not None else None
        ),
        queued_at=_aware(row.queued_at),
    )


async def _ensure_server(db: AsyncSession, ctx: VipContext, game_id: int) -> Server:
    server = await db.scalar(
        select(Server).where(Server.game == "bf1", Server.server_id == ctx.server_id)
    )
    if server is None:
        server = Server(game="bf1", server_id=ctx.server_id, game_id=game_id, name=ctx.name)
        db.add(server)
        await db.flush()
    else:
        server.game_id = game_id
        if ctx.name:
            server.name = ctx.name
    return server


async def _load(db: AsyncSession, server_pk: int) -> dict[int, Bf1ServerVip]:
    rows = await db.scalars(select(Bf1ServerVip).where(Bf1ServerVip.server_pk == server_pk))
    return {r.persona_id: r for r in rows}


class _Ledger:
    """一台服的托管记录：在内存里按规则变更，最后一次性写回。"""

    def __init__(self, db: AsyncSession, server_pk: int, rows: dict[int, Bf1ServerVip]) -> None:
        self.db = db
        self.server_pk = server_pk
        self.rows = rows
        self.entries = {pid: _entry(r) for pid, r in rows.items()}
        self._dirty: dict[int, tuple[engine.Entry | None, str | None, int | None]] = {}

    @classmethod
    async def open(
        cls, db: AsyncSession, server_pk: int, ctx: VipContext, now: datetime
    ) -> _Ledger:
        ledger = cls(db, server_pk, await _load(db, server_pk))
        for pid, change in engine.reconcile(ledger.entries, set(ctx.vips), now).items():
            ledger.set(pid, change.entry, name=ctx.vips.get(pid))
        # EA 名单里的名字更新到记录上
        for pid, row in ledger.rows.items():
            name = ctx.vips.get(pid)
            if name and row.display_name != name and pid not in ledger._dirty:
                row.display_name = name[:64]
        return ledger

    def set(
        self,
        pid: int,
        entry: engine.Entry | None,
        *,
        name: str | None = None,
        granted_by: int | None = None,
    ) -> None:
        if entry is None:
            self.entries.pop(pid, None)
        else:
            self.entries[pid] = entry
        self._dirty[pid] = (entry, name, granted_by)

    def name(self, pid: int) -> str | None:
        row = self.rows.get(pid)
        return row.display_name if row else None

    async def flush(self) -> None:
        for pid, (entry, name, granted_by) in self._dirty.items():
            row = self.rows.get(pid)
            if entry is None:
                if row is not None:
                    await self.db.delete(row)
                    self.rows.pop(pid)
                continue
            if row is None:
                row = Bf1ServerVip(server_pk=self.server_pk, persona_id=pid)
                self.db.add(row)
                self.rows[pid] = row
            row.status = entry.status
            row.expires_at = entry.expires_at
            row.remaining_seconds = (
                int(entry.remaining.total_seconds()) if entry.remaining is not None else None
            )
            row.queued_at = entry.queued_at
            if name:
                row.display_name = name[:64]
            if granted_by is not None:
                row.granted_by_user_id = granted_by
            row.attempts = 0
            row.last_error = None
            row.last_attempt_at = None
        self._dirty.clear()
        await self.db.flush()


def _grant_message(name: str, change: engine.Change) -> str:
    entry = change.entry
    if entry is None:
        return f"已添加永久 VIP {name}" if change.add else f"{name} 已改为永久 VIP"
    if entry.status == engine.PENDING:
        return (
            f"{name} 已加入待生效队列（{_fmt_span(entry.remaining)}），"
            "行动服要在 VIP 名单里点「立即生效」才会加上"
        )
    assert entry.expires_at is not None
    if change.add:
        return f"已添加 VIP {name}，{_fmt_time(entry.expires_at)} 到期"
    return f"{name} 的 VIP 改为 {_fmt_time(entry.expires_at)} 到期"


async def _execute_plan(
    client: Any,
    ctx: VipContext,
    ledger: _Ledger,
    plan: engine.ApplyPlan,
    now: datetime,
    failures: list[VipApplyFailure],
) -> tuple[list[int], list[int]]:
    """按 checkvip 计划逐个下 V / 加 V，单个失败记下来接着做。"""
    removed: list[int] = []
    added: list[int] = []
    for action, pids in (("remove", plan.remove), ("add", plan.add)):
        for pid in pids:
            if action == "remove":
                res = await client.removeServerVip(pid, ctx.server_id)
                ok = isinstance(res, dict)
            else:
                res = await client.addServerVip(pid, ctx.server_id)
                ok = isinstance(res, dict) or _already_vip(res)
            if ok and action == "remove":
                removed.append(pid)
                ledger.set(pid, None)
            elif ok:
                added.append(pid)
                ledger.set(pid, engine.activate(ledger.entries[pid], now))
            else:
                failures.append(
                    VipApplyFailure(
                        persona_id=pid,
                        display_name=ledger.name(pid),
                        action=action,  # type: ignore[arg-type]
                        message=str(res)[:256],
                    )
                )
            await asyncio.sleep(EA_WRITE_INTERVAL)
    return removed, added


def _apply_message(removed: int, added: int, waiting: int, failed: int, restarted: bool) -> str:
    if not removed and not added and not failed:
        return "没有过期的 VIP，也没有能补上的待生效 VIP"
    parts = [f"下掉 {removed} 个过期 VIP，加上 {added} 个"]
    if waiting:
        parts.append(f"还有 {waiting} 个在排队")
    if failed:
        parts.append(f"{failed} 项失败")
    if restarted:
        parts.append("已重开当前地图")
    return "，".join(parts)


class TimedVipService(BF1ServerAdminService):
    """计时 VIP 的服管操作；复用父类的凭据来源与审计写法。"""

    async def view(self) -> TimedVipView:
        now = _now()
        async with self.client_provider.acquire() as client:
            ctx = await fetch_context(client, self.game_id)
        async with _locks[ctx.server_id]:
            server = await _ensure_server(self.db, ctx, self.game_id)
            ledger = await _Ledger.open(self.db, server.id, ctx, now)
            await ledger.flush()
            await self.db.commit()
        queue = engine.queue_order(ledger.entries)
        items = [
            TimedVipItem(
                persona_id=pid,
                display_name=ledger.name(pid),
                status=e.status,  # type: ignore[arg-type]
                expires_at=e.expires_at,
                remaining_seconds=_seconds_left(e, now),
                expired=engine.is_expired(e, now),
                queue_position=queue.index(pid) + 1 if pid in queue else None,
                last_error=ledger.rows[pid].last_error if pid in ledger.rows else None,
            )
            for pid, e in ledger.entries.items()
        ]
        return TimedVipView(
            operation=ctx.operation,
            map_name=ctx.map_name or None,
            campaign_start=ctx.campaign_start,
            players=ctx.soldiers,
            vip_ids=sorted(ctx.vips),
            capacity=engine.VIP_CAPACITY,
            queue_limit=engine.QUEUE_LIMIT,
            items=items,
        )

    async def grant(
        self,
        persona_id: int,
        days: int | None,
        *,
        display_name: str | None = None,
        allow_permanent_to_timed: bool = False,
    ) -> str:
        now = _now()
        payload: dict[str, Any] = {"persona_id": persona_id, "days": days}
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
                ctx = await fetch_context(client, self.game_id)
                payload["server_id"] = ctx.server_id
                payload["operation"] = ctx.operation
                async with _locks[ctx.server_id]:
                    server = await _ensure_server(self.db, ctx, self.game_id)
                    ledger = await _Ledger.open(self.db, server.id, ctx, now)
                    queue_size = sum(
                        1 for e in ledger.entries.values() if e.status == engine.PENDING
                    )
                    try:
                        change = engine.grant(
                            ledger.entries.get(persona_id),
                            on_list=persona_id in ctx.vips,
                            days=days,
                            now=now,
                            operation=ctx.operation,
                            queue_size=queue_size,
                            allow_permanent_to_timed=allow_permanent_to_timed,
                        )
                    except engine.VipRuleError as err:
                        await ledger.flush()
                        await self.db.commit()
                        raise _rule_error(err) from err
                    if change.add:
                        res = await client.addServerVip(persona_id, ctx.server_id)
                        if not isinstance(res, dict) and not _already_vip(res):
                            raise EAApiError(code="EA_ADD_VIP_FAILED", message=str(res)[:256])
                    name = (
                        ctx.vips.get(persona_id)
                        or display_name
                        or ledger.name(persona_id)
                        or str(persona_id)
                    )
                    ledger.set(persona_id, change.entry, name=name, granted_by=self.user.id)
                    await ledger.flush()
                    await self.db.commit()
            entry = change.entry
            payload["status"] = entry.status if entry else "permanent"
            if entry and entry.expires_at:
                payload["expires_at"] = entry.expires_at.isoformat()
            if entry and entry.remaining is not None:
                payload["remaining_seconds"] = int(entry.remaining.total_seconds())
            await self._audit_success("add_vip", payload, target_persona_id=persona_id)
            return _grant_message(name, change)
        except EAApiError as err:
            await self._audit_failure("add_vip", payload, err, target_persona_id=persona_id)
            raise

    async def revoke(self, persona_id: int) -> str:
        now = _now()
        payload: dict[str, Any] = {"persona_id": persona_id}
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
                ctx = await fetch_context(client, self.game_id)
                payload["server_id"] = ctx.server_id
                payload["operation"] = ctx.operation
                async with _locks[ctx.server_id]:
                    server = await _ensure_server(self.db, ctx, self.game_id)
                    ledger = await _Ledger.open(self.db, server.id, ctx, now)
                    on_list = persona_id in ctx.vips
                    try:
                        change = engine.revoke(
                            ledger.entries.get(persona_id),
                            on_list=on_list,
                            now=now,
                            operation=ctx.operation,
                        )
                    except engine.VipRuleError as err:
                        await ledger.flush()
                        await self.db.commit()
                        raise _rule_error(err) from err
                    if change.remove:
                        res = await client.removeServerVip(persona_id, ctx.server_id)
                        if not isinstance(res, dict):
                            raise EAApiError(code="EA_REMOVE_VIP_FAILED", message=str(res)[:256])
                    name = ctx.vips.get(persona_id) or ledger.name(persona_id) or str(persona_id)
                    ledger.set(persona_id, change.entry, name=name, granted_by=self.user.id)
                    await ledger.flush()
                    await self.db.commit()
            await self._audit_success("remove_vip", payload, target_persona_id=persona_id)
            if change.remove:
                return f"已移除 VIP {name}"
            if not on_list:
                return f"已把 {name} 移出待生效队列"
            return f"{name} 已标记为到期，下次「立即生效」时下掉"
        except EAApiError as err:
            await self._audit_failure("remove_vip", payload, err, target_persona_id=persona_id)
            raise

    async def apply(self, restart: bool) -> VipApplyResult:
        """checkvip：先下掉过期的，再按排队顺序补空位，补上的从现在开始计时。"""
        now = _now()
        payload: dict[str, Any] = {"restart": restart}
        failures: list[VipApplyFailure] = []
        restarted = False
        try:
            async with self.client_provider.acquire() as client:
                self._tag_credential_source(payload)
                ctx = await fetch_context(client, self.game_id)
                payload["server_id"] = ctx.server_id
                payload["operation"] = ctx.operation
                async with _locks[ctx.server_id]:
                    server = await _ensure_server(self.db, ctx, self.game_id)
                    ledger = await _Ledger.open(self.db, server.id, ctx, now)
                    if ctx.operation and ctx.soldiers == 0:
                        await ledger.flush()
                        await self.db.commit()
                        raise AppError(
                            status.HTTP_409_CONFLICT,
                            "VIP_SERVER_EMPTY",
                            "服务器里没有人。行动服空服时上下 V 会掉回普通服，等有人在玩时再生效",
                        )
                    plan = engine.plan_apply(ledger.entries, set(ctx.vips), now)
                    removed, added = await _execute_plan(client, ctx, ledger, plan, now, failures)
                    await ledger.flush()
                    await self.db.commit()
                    waiting = plan.waiting + (len(plan.add) - len(added))
                    if restart and (removed or added):
                        restarted = await self._restart(client, ctx, failures)
            payload.update(
                removed=removed,
                added=added,
                waiting=waiting,
                restarted=restarted,
                failures=[f.model_dump() for f in failures],
            )
            await self._audit_success("vip_apply", payload)
        except EAApiError as err:
            await self._audit_failure("vip_apply", payload, err)
            raise
        return VipApplyResult(
            message=_apply_message(len(removed), len(added), waiting, len(failures), restarted),
            removed=len(removed),
            added=len(added),
            waiting=waiting,
            restarted=restarted,
            failures=failures,
        )

    async def _restart(self, client: Any, ctx: VipContext, failures: list[VipApplyFailure]) -> bool:
        """重开当前地图让名单生效；记一条 choose_level 审计，自动换图据此识别为人工换图。"""
        if not ctx.persisted_game_id or ctx.map_name not in ctx.rotation:
            failures.append(
                VipApplyFailure(
                    persona_id=0, action="restart", message="在轮换里找不到当前地图，没有重开"
                )
            )
            return False
        index = ctx.rotation.index(ctx.map_name)
        payload: dict[str, Any] = {
            "level_index": index,
            "persisted_game_id": ctx.persisted_game_id,
            "vip_apply": True,
        }
        self._tag_credential_source(payload)
        res = await client.chooseLevel(ctx.persisted_game_id, index)
        if isinstance(res, dict):
            await self._audit_success("choose_level", payload)
            return True
        err = EAApiError(code="EA_CHOOSE_LEVEL_FAILED", message=str(res)[:256])
        await self._audit_failure("choose_level", payload, err)
        failures.append(
            VipApplyFailure(persona_id=0, action="restart", message=f"重开失败：{err.message}")
        )
        return False


# ----------------------------------------------------------------------------- 到期自动下 V


def _ready(row: Bf1ServerVip, now: datetime) -> bool:
    last = _aware(row.last_attempt_at)
    if not row.attempts or last is None:
        return True
    wait = min(BACKOFF_BASE * 2 ** min(row.attempts, 16), BACKOFF_MAX)
    return last + wait <= now


def _mark_failed(rows: list[Bf1ServerVip], message: str, now: datetime) -> None:
    for row in rows:
        row.attempts += 1
        row.last_error = message[:500]
        row.last_attempt_at = now


async def _executors(db: AsyncSession, server: Server, rows: list[Bf1ServerVip]) -> list[User]:
    """代为下 V 的候选人：授予人优先（最近改过的在前），再是本服其他服主 / 管理员。"""
    ids: list[int] = []
    for row in sorted(rows, key=lambda r: _aware(r.updated_at) or _now(), reverse=True):
        if row.granted_by_user_id and row.granted_by_user_id not in ids:
            ids.append(row.granted_by_user_id)
    members = await db.scalars(
        select(ServerMembership.user_id).where(
            ServerMembership.server_pk == server.id,
            ServerMembership.role.in_(("owner", "admin")),
        )
    )
    ids += [uid for uid in members if uid not in ids]
    if not ids:
        return []
    users = {
        u.id: u
        for u in await db.scalars(
            select(User).options(selectinload(User.ea_bindings)).where(User.id.in_(ids))
        )
    }
    return [users[i] for i in ids if i in users]


async def _expire_with(
    db: AsyncSession,
    client: Any,
    server: Server,
    game_id: int,
    user: User,
    now: datetime,
    provider: GroupFirstBF1ClientProvider,
) -> None:
    ctx = await fetch_context(client, game_id)
    if ctx.server_id != server.server_id:
        raise EAApiError(code="VIP_SERVER_MISMATCH", message="gameId 已指向别的服务器")
    if ctx.operation:
        return
    persona = next((b.persona_id for b in user.ea_bindings if b.is_primary and not b.is_frozen), 0)
    audit = AuditService(db)
    async with _locks[ctx.server_id]:
        ledger = await _Ledger.open(db, server.id, ctx, now)
        due = [pid for pid, e in ledger.entries.items() if engine.is_expired(e, now)]
        for pid in due:
            row = ledger.rows[pid]
            if not _ready(row, now):
                continue
            payload: dict[str, Any] = {
                "persona_id": pid,
                "server_id": ctx.server_id,
                "timed_vip": True,
                "executor_user_id": user.id,
                "credential_source": provider.credential_source,
            }
            res = await client.removeServerVip(pid, ctx.server_id)
            if isinstance(res, dict):
                ledger.set(pid, None)
                await ledger.flush()
                await audit.record(
                    user_id=None,
                    acting_persona_id=persona,
                    game="bf1",
                    action="vip_expire",
                    server_id=game_id,
                    target_persona_id=pid,
                    payload=payload,
                    executor_persona_id=provider.executor_persona_id,
                )
            else:
                _mark_failed([row], f"到期自动下 V 失败：{str(res)[:200]}", now)
                await audit.record(
                    user_id=None,
                    acting_persona_id=persona,
                    game="bf1",
                    action="vip_expire",
                    server_id=game_id,
                    target_persona_id=pid,
                    payload=payload,
                    result="failure",
                    error_code="EA_REMOVE_VIP_FAILED",
                    error_message=str(res)[:256],
                    executor_persona_id=provider.executor_persona_id,
                )
            await asyncio.sleep(EA_WRITE_INTERVAL)
        await ledger.flush()
        await db.commit()


async def _expire_server(
    db: AsyncSession, server: Server, game_id: int, rows: list[Bf1ServerVip], now: datetime
) -> None:
    authz = ServerAuthzService(db)
    for user in await _executors(db, server, rows):
        # 候选人可能已经退群、服被移出群，或者在 EA 上被撤了管理员：按现状重算
        role, is_platform_admin = await authz.resolve_role(user=user, game="bf1", server_id=game_id)
        if not is_platform_admin and ROLE_LEVEL.get(role or "", 0) < ROLE_LEVEL["admin"]:
            continue
        provider = GroupFirstBF1ClientProvider(db, user=user, game_id=game_id, server_pk=server.id)
        try:
            async with provider.acquire() as client:
                await _expire_with(db, client, server, game_id, user, now, provider)
            return
        except ExecutorUnavailableError:
            continue
        except EAApiError as err:
            _mark_failed(rows, f"到期自动下 V 失败：{err.message}", now)
            await db.commit()
            return
    _mark_failed(
        rows,
        "授予人和本服其他管理员都没有能用的服务账号（或已不是本服管理员），没法自动下 V",
        now,
    )
    await db.commit()


async def _tick(db: AsyncSession) -> None:
    now = _now()
    due = [
        r
        for r in await db.scalars(
            select(Bf1ServerVip).where(
                Bf1ServerVip.status == engine.ACTIVE,
                Bf1ServerVip.expires_at.is_not(None),
                Bf1ServerVip.expires_at <= now,
            )
        )
        if _ready(r, now)
    ]
    if not due:
        return
    by_server: dict[int, list[Bf1ServerVip]] = defaultdict(list)
    for row in due:
        by_server[row.server_pk].append(row)
    servers = list(await db.scalars(select(Server).where(Server.id.in_(by_server))))
    game_ids = await current_game_ids(db, servers)
    # 先用生产已登录的 Blaze 连接看模式：行动服整台跳过，不必为它们动用任何人的凭据
    states = await get_operation_states(db, list(game_ids.values()))
    carding = active_game_ids()
    for server in servers:
        rows = by_server[server.id]
        game_id = game_ids.get(server.id)
        info = states.get(game_id) if game_id else None
        if info is None:
            _mark_failed(rows, "找不到这台服当前的 gameId（可能已关服），没法自动下 V", now)
            await db.commit()
            continue
        if info.get("mode") == OPERATIONS_MODE or game_id in carding:
            continue
        try:
            await _expire_server(db, server, game_id, rows, now)
        except Exception as e:
            await db.rollback()
            logger.warning("BF1 timed vip server_pk={} failed: {}", server.id, e)


async def timed_vip_poller() -> None:
    """后台定时下掉普通服上到期的 VIP。在应用 lifespan 中以 asyncio 任务启动。"""
    ea_metrics.set_source("timed_vip")
    while True:
        try:
            async with get_sessionmaker()() as db:
                await _tick(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("BF1 timed vip tick failed: {}", e)
        await asyncio.sleep(POLL_SECONDS)
