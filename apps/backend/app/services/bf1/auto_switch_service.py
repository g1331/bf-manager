"""BF1 行动服自动换图：编排读写、开关，以及后台轮询执行。

判断逻辑在 auto_switch_engine（纯函数）。这里负责：
- 每 POLL_SECONDS 秒用生产已登录的 Blaze 连接一次查完所有开启的服（不另行登录）；
- 需要换图时用开启人的绑定凭据调 RSP.chooseLevel（EA 要求服务器 RSP 管理员），审计里
  操作者记为「自动换图」（user_id 为空，payload.auto_switch=true，附开启人）；
- 换图失败、编排跑完、与别的机器人冲突时自动关闭并留下记录。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import EAApiError, ForbiddenError, ValidationError
from app.core import ea_metrics
from app.db.session import get_sessionmaker
from app.domain.games.bf1.client_provider import BindingFirstBF1ClientProvider
from app.domain.games.bf1.maps import operation_maps, translate_map_name
from app.models import AuditLog, User
from app.models.bf1 import Bf1AutoSwitch
from app.schemas.bf1.auto_switch import AutoSwitchEvent, AutoSwitchPlan, AutoSwitchView
from app.services.audit_service import AuditService
from app.services.bf1 import auto_switch_engine as engine
from app.services.bf1.blaze_service import get_operation_states
from app.services.bf1.server_admin_service import resolve_ea_ids
from app.services.bf1.server_service import BF1ServerService

POLL_SECONDS = 5
ROTATION_REFRESH_SECONDS = 600
# 这段时间内有人在平台上手动换过图，落图按人工切图处理
MANUAL_WINDOW_SECONDS = 120
OPERATIONS_MODE = "BreakthroughLarge"

# 进程内缓存每台服的 RSP 轮换（地图代号，下标即 levelIndex）
_rotations: dict[int, tuple[float, list[str]]] = {}


async def _rotation(db: AsyncSession, game_id: int, *, force: bool = False) -> list[str]:
    cached = _rotations.get(game_id)
    if cached and not force and time.time() - cached[0] < ROTATION_REFRESH_SECONDS:
        return cached[1]
    detail = await BF1ServerService(db).get_detail(game_id)
    maps = [m.map_name or "" if m.game_mode == OPERATIONS_MODE else "" for m in detail.map_rotation]
    _rotations[game_id] = (time.time(), maps)
    return maps


def _validate_plan(plan: AutoSwitchPlan, rotation: list[str]) -> None:
    for i, item in enumerate(plan.items, start=1):
        name = translate_map_name(item.map) or item.map
        if item.map not in rotation:
            raise ValidationError(f"第 {i} 项「{name}」不在本服的行动模式图池里")
        ops = operation_maps(item.map)
        if item.scope == "operation" and (len(ops) < 2 or ops[0] != item.map):
            raise ValidationError(f"第 {i} 项「{name}」不是多图战役的第一张，只能按单图编排")


class AutoSwitchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _row(self, game_id: int) -> Bf1AutoSwitch | None:
        return await self.db.scalar(select(Bf1AutoSwitch).where(Bf1AutoSwitch.game_id == game_id))

    async def get(self, game_id: int) -> AutoSwitchView:
        row = await self._row(game_id)
        if row is None:
            return AutoSwitchView()
        user = await self.db.get(User, row.enabled_by_user_id) if row.enabled_by_user_id else None
        st = {**engine.initial_state(), **(row.state or {})}
        return AutoSwitchView(
            enabled=row.enabled,
            plan=AutoSwitchPlan.model_validate(row.plan),
            cursor=st["cursor"],
            done=st["done"],
            loop=st["loop"],
            pending_map=(st["pending"] or {}).get("target"),
            enabled_by=user.username if user else None,
            enabled_at=row.enabled_at.timestamp() if row.enabled_at else None,
            events=[AutoSwitchEvent.model_validate(e) for e in row.events or []],
        )

    async def save_plan(self, game_id: int, plan: AutoSwitchPlan) -> AutoSwitchView:
        _validate_plan(plan, await _rotation(self.db, game_id, force=True))
        row = await self._row(game_id)
        if row is None:
            row = Bf1AutoSwitch(game_id=game_id, plan={}, state={}, events=[])
            self.db.add(row)
        row.plan = plan.model_dump()
        # 编排变了，下一次观测重新定位
        row.state = engine.initial_state()
        if row.enabled and not plan.items:
            row.enabled = False
        await self.db.commit()
        return await self.get(game_id)

    async def enable(self, game_id: int, user: User) -> AutoSwitchView:
        row = await self._row(game_id)
        if row is None or not row.plan.get("items"):
            raise ValidationError("先保存编排再开启自动换图")
        _validate_plan(
            AutoSwitchPlan.model_validate(row.plan), await _rotation(self.db, game_id, force=True)
        )
        # 换图要用 RSP 管理员凭据：开启时就确认开启人的绑定（或兜底的账号池）有权限
        provider = BindingFirstBF1ClientProvider(self.db, user=user, game_id=game_id)
        async with provider.acquire() as client:
            res = await client.getFullServerDetails(game_id)
        rsp_server = (
            ((res.get("result") or {}).get("rspInfo") or {}).get("server")
            if isinstance(res, dict)
            else None
        )
        if not (rsp_server or {}).get("serverId"):
            raise ForbiddenError("你绑定的 EA 账号不是这台服的 RSP 管理员，无法自动换图")
        now = time.time()
        row.enabled = True
        row.enabled_by_user_id = user.id
        row.enabled_at = datetime.now(UTC)
        row.state = engine.initial_state()
        row.events = engine.append_events(
            row.events or [], [("start", f"{user.username} 开启了自动换图")], now
        )
        await self.db.commit()
        await self._audit(user, game_id, "auto_switch_enable")
        return await self.get(game_id)

    async def disable(self, game_id: int, user: User) -> AutoSwitchView:
        row = await self._row(game_id)
        if row is not None and row.enabled:
            row.enabled = False
            row.events = engine.append_events(
                row.events or [], [("stop", f"{user.username} 关闭了自动换图")], time.time()
            )
            await self.db.commit()
            await self._audit(user, game_id, "auto_switch_disable")
        return await self.get(game_id)

    async def _audit(self, user: User, game_id: int, action: str) -> None:
        persona = next(
            (b.persona_id for b in user.ea_bindings if b.is_primary and not b.is_frozen), 0
        )
        await AuditService(self.db).record(
            user_id=user.id, acting_persona_id=persona, game="bf1", action=action, server_id=game_id
        )


# ----------------------------------------------------------------------------- 后台轮询


async def _manual_recent(db: AsyncSession, game_id: int) -> bool:
    """最近有人在平台上手动换过图（自动换图的审计 user_id 为空，不算）"""
    since = datetime.now(UTC) - timedelta(seconds=MANUAL_WINDOW_SECONDS)
    hit = await db.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.game == "bf1",
            AuditLog.server_id == game_id,
            AuditLog.action == "choose_level",
            AuditLog.result == "success",
            AuditLog.user_id.is_not(None),
            AuditLog.created_at >= since,
        )
        .limit(1)
    )
    return hit is not None


async def _choose(db: AsyncSession, row: Bf1AutoSwitch, choose: engine.Choose) -> None:
    """以开启人的凭据换图；审计操作者记为自动换图。失败抛 EAApiError。"""
    user = await db.scalar(
        select(User)
        .options(selectinload(User.ea_bindings))
        .where(User.id == row.enabled_by_user_id)
    )
    if user is None:
        raise EAApiError(code="AUTO_SWITCH_NO_USER", message="开启人账号已不存在")
    provider = BindingFirstBF1ClientProvider(db, user=user, game_id=row.game_id)
    payload: dict[str, Any] = {
        "level_index": choose.level_index,
        "map": choose.map,
        "auto_switch": True,
        "enabled_by_user_id": user.id,
    }
    audit = AuditService(db)
    try:
        async with provider.acquire() as client:
            payload["credential_source"] = provider.credential_source
            _, persisted_game_id = await resolve_ea_ids(client, row.game_id)
            if not persisted_game_id:
                raise EAApiError(code="EA_SERVER_NOT_INITIALIZED", message="服务器尚未完成初始化")
            res = await client.chooseLevel(persisted_game_id, choose.level_index)
            if not isinstance(res, dict):
                raise EAApiError(code="EA_CHOOSE_LEVEL_FAILED", message=str(res)[:256])
    except EAApiError as err:
        await audit.record(
            user_id=None,
            acting_persona_id=0,
            game="bf1",
            action="choose_level",
            server_id=row.game_id,
            payload=payload,
            result="failure",
            error_code=err.code,
            error_message=err.message,
        )
        raise
    await audit.record(
        user_id=None,
        acting_persona_id=0,
        game="bf1",
        action="choose_level",
        server_id=row.game_id,
        payload=payload,
    )


async def _tick(db: AsyncSession) -> None:
    rows = list(await db.scalars(select(Bf1AutoSwitch).where(Bf1AutoSwitch.enabled.is_(True))))
    if not rows:
        return
    states = await get_operation_states(db, [r.game_id for r in rows])
    for row in rows:
        info = states.get(row.game_id)
        if not info or not info["map"]:
            continue
        try:
            await _step(db, row, info)
        except Exception as e:
            await db.rollback()
            logger.warning("BF1 auto switch game_id={} failed: {}", row.game_id, e)


async def _step(db: AsyncSession, row: Bf1AutoSwitch, info: dict[str, Any]) -> None:
    now = time.time()
    known = _rotations.get(row.game_id, (0.0, []))[1]
    rotation = await _rotation(db, row.game_id, force=info["map"] not in known)
    obs = engine.Observation(map=info["map"], full=info["progress"] == "5", state=info["state"])
    d = engine.decide(
        row.plan,
        rotation,
        row.state or {},
        obs,
        now,
        manual_recent=await _manual_recent(db, row.game_id),
    )
    events = list(d.events)
    if d.choose and not d.stop:
        try:
            await _choose(db, row, d.choose)
        except EAApiError as err:
            events.append(("error", f"换图失败：{err.message}，停止自动换图"))
            d.stop = "error"
    row.state = d.state
    if events:
        row.events = engine.append_events(row.events or [], events, now)
    if d.stop:
        row.enabled = False
    await db.commit()


async def auto_switch_poller() -> None:
    """后台定时轮询开启了自动换图的服。在应用 lifespan 中以 asyncio 任务启动。"""
    ea_metrics.set_source("auto_switch")
    while True:
        try:
            async with get_sessionmaker()() as db:
                await _tick(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("BF1 auto switch tick failed: {}", e)
        await asyncio.sleep(POLL_SECONDS)
