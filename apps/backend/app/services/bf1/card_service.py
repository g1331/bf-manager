"""BF1 一键卡行动：预检、任务编排、停止、恢复。

判断与请求体在 card_engine（纯函数），Blaze 进服在 card_blaze。这里负责：
- 用服主或管理员的凭据（匿名填的 remid + sid，或登录用户的主绑定）登录 Gateway，核对它在
  这台服的 rspInfo 里是服主或管理员；不回落号池；
- 每个任务一个 asyncio 任务，凭据只在任务内存里，结束即丢弃；进度、事件和设置快照落库，
  快照含服务器密码，加密存放；
- 护栏：同一台服同时一个任务、全站最多 MAX_CONCURRENT 个，抽图最多 MAX_ATTEMPTS 轮或
  MAX_SECONDS 秒，非噪音错误连续 MAX_CONSECUTIVE_ERRORS 次就中止；运行期间自动换图跳过这台服；
- 进程重启时把没跑完的任务标成已中断（凭据已随内存丢失），用户重新填凭据后可恢复原设置。
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    AppError,
    EAApiError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
    ValidationError,
)
from app.core import ea_metrics
from app.core.security import get_cipher
from app.db.session import get_sessionmaker
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.maps import translate_map_name, translate_mode_name
from app.models import User
from app.models.bf1 import Bf1AutoSwitch, Bf1CardJob
from app.schemas.bf1.card import CardCredentials, CardEvent, CardJobView, CardPrecheck
from app.services.audit_service import AuditService
from app.services.bf1 import card_engine as engine
from app.services.bf1.card_blaze import CardBlazeSession
from app.services.ea_binding_service import EaBindingService

MAX_ATTEMPTS = 120
MAX_SECONDS = 30 * 60
MAX_CONCURRENT = 2
MAX_CONSECUTIVE_ERRORS = 3
# 锚定后留在服里的时间
HOLD_SECONDS = 5
# 手动锚定时进服重试次数
ANCHOR_JOIN_TRIES = 3
# 抽图时服里有别人，每轮多等这么久（CardTool 同款）
OCCUPIED_WAIT_SECONDS = 10

SLEEP: Callable[[float], Awaitable[None]] = asyncio.sleep

# 进程内运行中的任务：job_id → 运行器
_runners: dict[int, _Runner] = {}


def active_game_ids() -> set[int]:
    """有卡行动任务在跑的服，自动换图跳过它们"""
    return {r.game_id for r in _runners.values()}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ts(dt: datetime | None) -> float | None:
    return dt.timestamp() if dt else None


@dataclass(repr=False)
class OwnerCredentials:
    remid: str
    sid: str
    # 来自主绑定时回写刷新后的 sid / session
    binding_id: int | None = None

    def __repr__(self) -> str:  # 别让凭据进日志
        return f"OwnerCredentials(binding_id={self.binding_id})"


def resolve_credentials(req: CardCredentials, user: User | None) -> OwnerCredentials:
    if req.use_binding:
        if user is None:
            raise ValidationError("登录后才能使用绑定账号")
        binding = next((b for b in user.ea_bindings if b.is_primary and not b.is_frozen), None)
        if binding is None or not binding.encrypted_remid or not binding.encrypted_sid:
            raise ValidationError("你还没有可用的主绑定 EA 账号，请直接填写 remid 和 sid")
        cipher = get_cipher()
        return OwnerCredentials(
            remid=cipher.decrypt(binding.encrypted_remid),
            sid=cipher.decrypt(binding.encrypted_sid),
            binding_id=binding.id,
        )
    remid, sid = req.remid.strip(), req.sid.strip()
    if not remid or not sid:
        raise ValidationError("请填写服主或管理员账号的 remid 和 sid")
    return OwnerCredentials(remid=remid, sid=sid)


async def _login(creds: OwnerCredentials) -> BF1GatewayClient:
    """用服主或管理员的凭据登录 Gateway；失败时关闭连接并抛错"""
    binding_id = creds.binding_id

    async def _on_refresh(_pid: int, new_sid: str | None, new_session: str | None) -> None:
        if binding_id is None:
            return
        async with get_sessionmaker()() as db:
            await EaBindingService(db).update_session(binding_id, sid=new_sid, session=new_session)

    client = BF1GatewayClient(
        pid=0, remid=creds.remid, sid=creds.sid, on_session_refreshed=_on_refresh
    )
    try:
        await client.login(creds.remid, creds.sid)
    except Exception as exc:
        await _close(client)
        raise EAApiError(code="CARD_LOGIN_FAILED", message="登录 EA 失败，请稍后再试") from exc
    if not client.check_login or not client.pid:
        await _close(client)
        raise ValidationError("remid / sid 无效或已过期，请重新获取")
    return client


async def _close(client: BF1GatewayClient) -> None:
    with contextlib.suppress(Exception):
        http_session = getattr(client, "http_session", None)
        if http_session is not None:
            await http_session.close()


def _result(res: Any, what: str) -> dict[str, Any]:
    if not isinstance(res, dict):
        raise EAApiError(code="CARD_EA_FAILED", message=f"{what}失败：{str(res)[:120]}")
    return res.get("result") or {}


@dataclass
class _ServerInfo:
    game_id: int
    server_id: int
    persisted_game_id: str
    name: str
    owner_id: int
    owner_name: str
    admins: dict[int, str]  # 管理员 persona_id → 名字，不含服主
    state: engine.ServerState

    def can_manage(self, pid: int) -> bool:
        return pid == self.owner_id or pid in self.admins

    def name_of(self, pid: int) -> str:
        return self.owner_name if pid == self.owner_id else self.admins.get(pid, "")


async def _server_info(client: BF1GatewayClient, game_id: int) -> _ServerInfo:
    raw = _result(await client.getFullServerDetails(game_id), "查询服务器")
    info = raw.get("serverInfo") or {}
    rsp = raw.get("rspInfo") or {}
    server = rsp.get("server") or {}
    if not info or not server.get("serverId"):
        raise ValidationError("找不到这台服，或者它不是可管理的私服")
    owner = rsp.get("owner") or {}
    admins: dict[int, str] = {}
    for a in rsp.get("adminList") or []:
        if not isinstance(a, dict):
            continue
        with contextlib.suppress(TypeError, ValueError):
            if pid := int(a.get("personaId") or 0):
                admins[pid] = str(a.get("displayName") or "")
    return _ServerInfo(
        game_id=game_id,
        server_id=int(server["serverId"]),
        persisted_game_id=str(server.get("persistedGameId") or info.get("guid") or ""),
        name=str(info.get("name") or server.get("name") or ""),
        owner_id=int(owner.get("personaId") or server.get("ownerId") or 0),
        owner_name=str(owner.get("displayName") or ""),
        admins=admins,
        state=engine.parse_state(info),
    )


async def _snapshot(client: BF1GatewayClient, server_id: int) -> engine.Snapshot:
    raw = _result(await client.RSPgetServerDetails(server_id), "读取服务器设置")
    snap = engine.snapshot_from_rsp(raw)
    if not snap.settings["name"]:
        raise EAApiError(code="CARD_SNAPSHOT_FAILED", message="读取服务器设置失败：名称为空")
    return snap


def _mode_name(mode: str) -> str:
    return (translate_mode_name(mode) if mode else None) or "未知模式"


class CardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def precheck(self, creds: OwnerCredentials, game_id: int) -> CardPrecheck:
        client = await _login(creds)
        try:
            srv = await _server_info(client, game_id)
        finally:
            await _close(client)
        auto = await self.db.scalar(
            select(Bf1AutoSwitch.enabled).where(Bf1AutoSwitch.game_id == game_id)
        )
        running = next((jid for jid, r in _runners.items() if r.game_id == game_id), None)
        st = srv.state
        return CardPrecheck(
            game_id=game_id,
            server_id=srv.server_id,
            server_name=srv.name,
            persona_id=int(client.pid),
            owner_id=srv.owner_id,
            owner_name=srv.owner_name,
            is_owner=srv.owner_id == int(client.pid),
            is_admin=int(client.pid) in srv.admins,
            occupied=st.occupied,
            soldier_max=st.soldier_max,
            mode=st.mode,
            map_name=st.map,
            map_count=len(st.maps),
            is_operation=engine.is_hit(st),
            auto_switch_enabled=bool(auto),
            running_job_id=running,
        )

    async def start(
        self,
        creds: OwnerCredentials,
        game_id: int,
        kind: str,
        *,
        user: User | None,
        ip: str | None,
    ) -> tuple[CardJobView, str]:
        if any(r.game_id == game_id for r in _runners.values()):
            raise ValidationError("这台服已经有一个卡行动任务在跑")
        if len(_runners) >= MAX_CONCURRENT:
            raise TooManyRequestsError("同时卡行动的服太多了，请过几分钟再试", retry_after=120)
        client = await _login(creds)
        try:
            srv = await _server_info(client, game_id)
            if not srv.can_manage(int(client.pid)):
                raise ForbiddenError(
                    f"这个账号不是这台服的服主或管理员（服主：{srv.owner_name or srv.owner_id}）"
                )
            st = srv.state
            if kind == "card" and st.occupied > 0:
                raise ValidationError(
                    f"服里还有 {st.occupied} 人，抽图需要空服；已经是行动服的话请用手动锚定"
                )
            if kind == "anchor" and not engine.is_hit(st):
                raise ValidationError(
                    f"当前是{_mode_name(st.mode)}、{len(st.maps)} 张图，不是 24 图行动，锚定没有意义"
                )
            snap = await _snapshot(client, srv.server_id)
            # 再查一次，挡住并发的两个请求
            if any(r.game_id == game_id for r in _runners.values()):
                raise ValidationError("这台服已经有一个卡行动任务在跑")
            token = secrets.token_urlsafe(24)
            job = Bf1CardJob(
                kind=kind,
                game_id=game_id,
                server_id=srv.server_id,
                server_name=srv.name[:128],
                user_id=user.id if user else None,
                persona_id=int(client.pid),
                persona_name=srv.name_of(int(client.pid))[:64],
                token_hash=_hash(token),
                client_ip=ip,
                status="running",
                snapshot_enc=get_cipher().encrypt(json.dumps(snap.to_dict(), ensure_ascii=False)),
                events=[],
            )
            self.db.add(job)
            await self.db.commit()
        except BaseException:
            await _close(client)
            raise
        runner = _Runner(job.id, kind, srv, snap, client, creds)
        _runners[job.id] = runner
        # 新上下文：不继承请求里的公共 EA 预算标记和计数来源
        runner.task = asyncio.create_task(runner.run(), context=contextvars.Context())
        await self._audit(job, "card_start" if kind == "card" else "card_anchor")
        return await self.view(job.id), token

    async def _job(self, job_id: int, token: str | None, user: User | None) -> Bf1CardJob:
        job = await self.db.get(Bf1CardJob, job_id)
        if job is None:
            raise NotFoundError("任务")
        by_token = bool(token) and hmac.compare_digest(_hash(token or ""), job.token_hash)
        by_user = user is not None and job.user_id is not None and job.user_id == user.id
        if not (by_token or by_user):
            raise ForbiddenError("无权查看这个任务")
        return job

    async def view(self, job_id: int) -> CardJobView:
        job = await self.db.get(Bf1CardJob, job_id)
        if job is None:
            raise NotFoundError("任务")
        await self.db.refresh(job)
        return CardJobView(
            id=job.id,
            kind=job.kind,
            game_id=job.game_id,
            server_name=job.server_name,
            persona_id=job.persona_id,
            persona_name=job.persona_name,
            status=job.status,  # type: ignore[arg-type]
            attempts=job.attempts,
            max_attempts=MAX_ATTEMPTS if job.kind == "card" else 0,
            message=job.message,
            result_maps=job.result_maps,
            can_restore=job.status != "running" and bool(job.snapshot_enc),
            restored_at=_ts(job.restored_at),
            started_at=job.created_at.timestamp(),
            finished_at=_ts(job.finished_at),
            events=[CardEvent.model_validate(e) for e in job.events or []],
        )

    async def get(self, job_id: int, token: str | None, user: User | None) -> CardJobView:
        await self._job(job_id, token, user)
        return await self.view(job_id)

    async def cancel(self, job_id: int, token: str | None, user: User | None) -> CardJobView:
        await self._job(job_id, token, user)
        runner = _runners.get(job_id)
        if runner is not None and runner.task is not None:
            runner.cancel_reason = "cancelled"
            runner.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(runner.task), 15)
        return await self.view(job_id)

    async def restore(
        self, job_id: int, token: str | None, user: User | None, creds: OwnerCredentials
    ) -> CardJobView:
        job = await self._job(job_id, token, user)
        if job.status == "running" or job_id in _runners:
            raise ValidationError("任务还在运行，先停止再恢复")
        if not job.snapshot_enc:
            raise ValidationError("这个任务没有保存原设置，无法恢复")
        snap = engine.Snapshot.from_dict(json.loads(get_cipher().decrypt(job.snapshot_enc)))
        client = await _login(creds)
        try:
            if int(client.pid) != job.persona_id:
                raise ForbiddenError("请使用开始任务时的同一个账号")
            err = engine.update_error(
                await client.updateServer(engine.update_params(job.server_id, snap))
            )
        finally:
            await _close(client)
        if err:
            await self._audit(job, "card_restore", error=err)
            raise EAApiError(code="CARD_RESTORE_FAILED", message=f"恢复失败：{err}")
        job.restored_at = datetime.now(UTC)
        job.events = engine.append_events(
            job.events or [],
            [("info", f"已恢复原设置和原轮换（{len(snap.rotation.get('maps') or [])} 张图）")],
            time.time(),
        )
        await self.db.commit()
        await self._audit(job, "card_restore")
        return await self.view(job_id)

    async def _audit(self, job: Bf1CardJob, action: str, *, error: str | None = None) -> None:
        await AuditService(self.db).record(
            user_id=job.user_id,
            acting_persona_id=job.persona_id,
            game="bf1",
            action=action,
            server_id=job.game_id,
            payload={"card_job_id": job.id, "kind": job.kind},
            result="failure" if error else "success",
            error_code="CARD_EA_FAILED" if error else None,
            error_message=error,
            ip=job.client_ip,
        )


# ----------------------------------------------------------------------------- 后台执行


class _AbortError(Exception):
    """任务以失败结束，消息直接给用户看"""


@dataclass
class _Runner:
    job_id: int
    kind: str
    srv: _ServerInfo
    snap: engine.Snapshot
    client: BF1GatewayClient
    creds: OwnerCredentials
    task: asyncio.Task[None] | None = None
    # 被取消时的结局：cancelled（用户停止）或 interrupted（进程关闭）
    cancel_reason: str = "interrupted"
    blaze: CardBlazeSession | None = None
    errors: int = 0
    joined: bool = False
    started: float = field(default_factory=time.monotonic)

    @property
    def game_id(self) -> int:
        return self.srv.game_id

    # ---- 持久化

    async def _save(self, events: list[tuple[str, str]] | None = None, **fields: Any) -> None:
        try:
            async with get_sessionmaker()() as db:
                job = await db.get(Bf1CardJob, self.job_id)
                if job is None:
                    return
                for k, v in fields.items():
                    setattr(job, k, v)
                if events:
                    job.events = engine.append_events(job.events or [], list(events), time.time())
                await db.commit()
        except Exception as exc:
            logger.warning("卡行动任务 {} 写库失败: {!r}", self.job_id, exc)

    async def log(self, kind: str, message: str) -> None:
        await self._save([(kind, message)])

    async def _finish(self, status: str, message: str, kind: str, **fields: Any) -> None:
        await self._save(
            [(kind, message)],
            status=status,
            message=message[:256],
            finished_at=datetime.now(UTC),
            **fields,
        )
        action = {"succeeded": "card_success", "failed": "card_fail"}.get(status)
        if action is None:
            return
        try:
            async with get_sessionmaker()() as db:
                job = await db.get(Bf1CardJob, self.job_id)
                if job is not None:
                    await CardService(db)._audit(
                        job, action, error=None if status == "succeeded" else message
                    )
        except Exception as exc:
            logger.warning("卡行动任务 {} 写审计失败: {!r}", self.job_id, exc)

    # ---- 错误计数

    def ok(self) -> None:
        self.errors = 0

    async def fail(self, message: str) -> None:
        """记一次非噪音错误；权限错误或连续出错太多就中止"""
        await self.log("error", message)
        if engine.is_permission_error(message):
            raise _AbortError(f"EA 拒绝了操作：{message}")
        self.errors += 1
        if self.errors >= MAX_CONSECUTIVE_ERRORS:
            raise _AbortError(f"连续 {self.errors} 次出错，已停止：{message}")

    # ---- EA 调用

    async def update(self, maps: list[dict[str, str]] | None, what: str) -> None:
        err = engine.update_error(
            await self.client.updateServer(
                engine.update_params(self.srv.server_id, self.snap, maps)
            )
        )
        if err:
            await self.fail(f"{what}失败：{err}")
        else:
            self.ok()

    async def state(self) -> engine.ServerState | None:
        res = await self.client.getServerDetails(self.game_id)
        if not isinstance(res, dict) or not res.get("result"):
            await self.fail(f"查询服务器状态失败：{str(res)[:120]}")
            return None
        self.ok()
        return engine.parse_state(res["result"])

    async def choose_level(self, guid: str) -> None:
        res = await self.client.chooseLevel(guid, 0)
        if not isinstance(res, dict):
            await self.fail(f"切图失败：{str(res)[:120]}")

    async def open_blaze(self) -> None:
        if self.blaze is None:
            # Gateway 登录会刷新 sid，取 Blaze authcode 用客户端里的当前值
            self.blaze = CardBlazeSession(
                int(self.client.pid),
                self.client.remid or self.creds.remid,
                self.client.sid or self.creds.sid,
            )
        try:
            await self.blaze.open()
            self.ok()
        except AppError as exc:
            await self.fail(f"Blaze 登录失败：{exc.message}")
        except Exception as exc:
            await self.fail(f"Blaze 连接失败：{exc!r}"[:200])

    async def join(self) -> str | None:
        if self.blaze is None or not self.blaze.alive:
            await self.log("warn", "Blaze 连接已断开，重新登录")
            await self.open_blaze()
            if self.blaze is None or not self.blaze.alive:
                return "Blaze 未连接"
        reason = await self.blaze.join(self.game_id)
        self.joined = reason is None
        return reason

    async def leave(self) -> None:
        if not self.joined:
            return
        self.joined = False
        with contextlib.suppress(Exception):
            await self.client.leaveGame(self.game_id)

    # ---- 流程

    async def run(self) -> None:
        ea_metrics.set_source("card")
        try:
            if self.kind == "card":
                await self._card()
            else:
                await self._manual_anchor()
        except asyncio.CancelledError:
            if self.cancel_reason == "cancelled":
                await self._finish(
                    "cancelled", "已停止，服务器可能停在 BUG 轮换，可以恢复原设置", "warn"
                )
            else:
                await self._finish(
                    "interrupted",
                    "服务重启，任务中断；服务器可能停在 BUG 轮换，可以恢复原设置",
                    "warn",
                )
        except _AbortError as exc:
            await self._finish("failed", str(exc), "error")
        except Exception as exc:
            logger.exception("卡行动任务 {} 异常: {!r}", self.job_id, exc)
            await self._finish("failed", "内部错误，任务已停止；可以恢复原设置后重试", "error")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        with contextlib.suppress(Exception):
            await asyncio.shield(self.leave())
        if self.blaze is not None:
            with contextlib.suppress(Exception):
                await asyncio.shield(self.blaze.close())
        await _close(self.client)
        _runners.pop(self.job_id, None)

    async def _card(self) -> None:
        st = self.srv.state
        seed = engine.seed_maps(st.soldier_max)
        await self.log(
            "info",
            f"已保存原设置；按 {st.soldier_max or 64} 人服种入 BUG 图"
            f"（{translate_map_name(seed[0]['mapName'])} · {seed[0]['gameMode']}）",
        )
        await self.update(seed, "种入 BUG 图")
        await self.open_blaze()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if time.monotonic() - self.started > MAX_SECONDS:
                raise _AbortError(
                    f"{MAX_SECONDS // 60} 分钟内没有抽中，已停止；可以恢复原设置或稍后重试"
                )
            await self._save(attempts=attempt)
            reason = await self.join()
            if reason:
                await self.fail(f"第 {attempt} 轮进服失败：{reason}")
                await self.leave()
                await SLEEP(1)
                continue
            await self.update(seed, f"第 {attempt} 轮更新服务器")
            await SLEEP(2)
            cur = await self.state()
            if cur is None:
                await self.leave()
                continue
            await self.log(
                "round", f"第 {attempt} 轮：{_mode_name(cur.mode)}，{len(cur.maps)} 张图"
            )
            if engine.is_hit(cur):
                await self.log("info", "抽中 24 图行动，开始锚定")
                await self._anchor(cur)
                return
            await self.leave()
            await SLEEP(1)
            await self.update(seed, "重置 BUG 图")
            await self.update(seed, "重置 BUG 图")
            await SLEEP(3)
            if cur.occupied > 1:
                await self.log(
                    "warn", f"服里有 {cur.occupied - 1} 个其他玩家，多等 {OCCUPIED_WAIT_SECONDS} 秒"
                )
                await SLEEP(OCCUPIED_WAIT_SECONDS)
        raise _AbortError(f"{MAX_ATTEMPTS} 轮都没有抽中，已停止；可以恢复原设置或稍后重试")

    async def _manual_anchor(self) -> None:
        st = self.srv.state
        if st.occupied > 0:
            await self.log("info", f"服里已有 {st.occupied} 人，不用进服，直接锚定")
        else:
            await self.log("info", "服里没人，先用这个账号进服（锚定要求服里有人）")
            await self.open_blaze()
            for i in range(1, ANCHOR_JOIN_TRIES + 1):
                reason = await self.join()
                if reason is None:
                    break
                await self.fail(f"第 {i} 次进服失败：{reason}")
                await SLEEP(2)
            else:
                raise _AbortError("进服失败，无法锚定")
            await SLEEP(2)
        cur = await self.state()
        if cur is None or not engine.is_hit(cur):
            raise _AbortError("服务器已经不是 24 图行动，没有锚定")
        await self._anchor(cur)

    async def _anchor(self, cur: engine.ServerState) -> None:
        guid = cur.guid or self.srv.persisted_game_id
        await self.choose_level(guid)
        await self.update(engine.anchor_maps(cur.maps), "锚定轮换")
        await SLEEP(1)
        await self.choose_level(guid)
        anchored = None
        with contextlib.suppress(Exception):
            snap = await _snapshot(self.client, self.srv.server_id)
            anchored = engine.is_anchored(cur, snap.rotation.get("maps") or [])
        if anchored is False:
            await self.log("warn", "复查时 RSP 轮换与当前图池不一致，可以稍后再手动锚定一次")
        if self.joined:
            await SLEEP(HOLD_SECONDS)
            await self.leave()
        first = translate_map_name(cur.maps[0]) if cur.maps else ""
        await self._finish(
            "succeeded",
            f"已锚定 {len(cur.maps)} 图行动（从{first}开始），请尽快进服",
            "success",
            result_maps=cur.maps,
        )


async def mark_interrupted_jobs() -> None:
    """进程启动时调用：上次没跑完的任务凭据已丢失，标成已中断"""
    try:
        async with get_sessionmaker()() as db:
            await db.execute(
                update(Bf1CardJob)
                .where(Bf1CardJob.status == "running")
                .values(
                    status="interrupted",
                    message="服务重启，任务中断；服务器可能停在 BUG 轮换，可以恢复原设置",
                    finished_at=datetime.now(UTC),
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("卡行动任务启动清理失败: {!r}", exc)


async def shutdown_card_jobs() -> None:
    """进程关闭时调用：取消运行中的任务，状态记为已中断"""
    tasks = [r.task for r in list(_runners.values()) if r.task is not None]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
