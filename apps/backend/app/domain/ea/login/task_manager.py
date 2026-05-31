"""EA 登录任务的生命周期管理。

设计原则
========

* **内存承担敏感数据**：email / password / 验证码 / remid / sid / gatewaySessionId 全部
  保存在 :class:`_TaskState` 与底层 :class:`EALoginEngine` 实例中，禁止落 Redis、磁盘、
  日志。
* **Redis 承担可共享元数据**：``status / version / available_methods / selected_method /
  masked_destination / error_code / error_message / timestamps``。这部分允许跨 worker
  查询（前端长轮询命中其他 worker 时仍能返回最新状态）。
* **Redis 不可用时降级**：所有 Redis 操作 try/except 仅记录 warning，不影响本 worker
  的任务流转。跨 worker 查询会自然失败（task 不在本 worker 内存中即返回未找到），
  前端需要重新发起任务。
* **Owner 强校验**：所有公开方法都接收 ``(actor_kind, actor_id)``。任意一项不匹配
  统一以 ``_MissingTaskError`` 抛出，由 service 层映射成 404，避免泄漏任务是否存在。
* **长轮询协议**：每次状态推进 ``version += 1``，前端通过 ``since_version`` 拉取增量；
  ``wait_for_change`` 以 :data:`Settings.ea_login_long_poll_seconds` 为窗口阻塞等待。

类与函数命名以下划线开头者为内部细节，service 层不应直接依赖。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from loguru import logger

from app.core.cache import get_redis
from app.core.config import get_settings
from app.domain.ea.login.exceptions import EALoginError
from app.domain.ea.login.login_engine import EALoginEngine, LoginCookies
from app.domain.ea.login.schemas import (
    TERMINAL_STATUSES,
    EALoginTaskResponse,
    EALoginTaskResultData,
    EALoginTaskStatus,
)

ActorKind = Literal["user", "admin"]

# finalize（写库）失败的统一错误码。具体异常细节走 logger，不透传给前端。
_FINALIZE_FAILED_CODE = "EA_LOGIN_FINALIZE_FAILED"
_FINALIZE_FAILED_MSG = "登录成功但凭据回填失败，请重试"

_REDIS_KEY_PREFIX = "ea_login:task"


def _redis_key(task_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}:{task_id}"


FinalizerFunc = Callable[
    [ActorKind, int, LoginCookies],
    Awaitable[EALoginTaskResultData],
]
"""登录引擎完成后回填账号体系的回调签名。

参数依次为：actor 类型（``user`` / ``admin``）、actor 主键（``users.id``）、登录引擎
抓到的 cookies。返回值由调用方组装成 :class:`EALoginTaskResultData` 写入任务状态。
回调内部应当自行管理数据库会话与异常，抛出的非 :class:`EALoginError` 异常会被本模块
按 ``EA_LOGIN_FINALIZE_FAILED`` 统一处理。
"""


# ===== 内部异常（仅 task_manager ⇄ service 层之间使用）=====


class _MissingTaskError(Exception):
    """任务不存在、已被清理，或当前 actor 无权访问。"""


class _InvalidStateTaskError(Exception):
    """当前任务状态不允许此操作。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ===== 内部状态 =====


@dataclass
class _TaskState:
    """单个登录任务的内存全状态。"""

    task_id: str
    actor_kind: ActorKind
    actor_id: int
    engine: EALoginEngine
    status: EALoginTaskStatus = EALoginTaskStatus.PENDING
    version: int = 0
    available_methods: list[str] = field(default_factory=list)
    selected_method: str | None = None
    masked_destination: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: EALoginTaskResultData | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # 状态推进通知。每次 _bump() 都会 set 旧 event 再换成新 event，使长轮询的多个
    # waiter 各自只被「下一次推进」唤醒一次。
    change_event: asyncio.Event = field(default_factory=asyncio.Event)
    # 用户输入通道，最多排队一个待消费的输入（重复提交直接报冲突）
    method_input: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    code_input: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    runner: asyncio.Task[None] | None = None
    # 终态后的延迟清理任务；close_all 时一并取消
    cleanup_handle: asyncio.Task[None] | None = None


# ===== 任务管理器 =====


class EALoginTaskManager:
    """单例任务管理器。

    通常由 :func:`init_task_manager` 在 FastAPI lifespan 中实例化，shutdown 时调用
    :meth:`close_all` 释放未结束任务的 aiohttp 连接。
    """

    def __init__(
        self,
        *,
        finalizer: FinalizerFunc,
        ttl_seconds: int,
        wait_seconds: int,
        long_poll_seconds: int,
    ) -> None:
        self._finalizer = finalizer
        self._ttl = ttl_seconds
        self._wait = wait_seconds
        self._long_poll = long_poll_seconds
        self._tasks: dict[str, _TaskState] = {}

    # ===== 公共 API =====

    async def create_task(
        self,
        *,
        actor_kind: ActorKind,
        actor_id: int,
        email: str,
        password: str,
    ) -> EALoginTaskResponse:
        """启动一次新登录任务。

        同一 actor 已有进行中任务时，先取消旧任务。这样避免一个用户连续点登录把 EA
        风控配额打满，也保证用户视角下「同一时间只有一个待办任务」。
        """
        await self._cancel_in_progress_for_actor(actor_kind, actor_id)

        task_id = str(uuid.uuid4())
        engine = EALoginEngine(task_id=task_id, email=email, password=password)
        state = _TaskState(
            task_id=task_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            engine=engine,
        )
        self._tasks[task_id] = state
        state.runner = asyncio.create_task(self._run(state))
        await self._persist(state)
        self._log_state(state, event="created")
        return self._to_response(state)

    async def get_state(
        self, task_id: str, *, actor_kind: ActorKind, actor_id: int
    ) -> EALoginTaskResponse:
        state = self._require_owned(task_id, actor_kind, actor_id)
        return self._to_response(state)

    async def submit_method(
        self,
        task_id: str,
        *,
        actor_kind: ActorKind,
        actor_id: int,
        method: str,
    ) -> EALoginTaskResponse:
        state = self._require_owned(task_id, actor_kind, actor_id)
        if state.status != EALoginTaskStatus.AWAITING_2FA_METHOD:
            raise _InvalidStateTaskError(f"当前状态 {state.status.value} 不可提交 2FA 方式")
        # schema 层放宽 method 为任意字符串以兼容 EA 的 SECOND_EMAIL 等扩展值；
        # 真正的白名单校验放在这里，避免前端被攻击成把任意值透传到 EA 表单字段。
        if method not in state.available_methods:
            raise _InvalidStateTaskError(
                f"2FA 方式 {method!r} 不在 EA 返回的可选范围内：{state.available_methods}"
            )
        try:
            state.method_input.put_nowait(method)
        except asyncio.QueueFull as e:
            raise _InvalidStateTaskError("2FA 方式已提交，请等待状态更新") from e
        # 等一次 runner 推进，方便调用方拿到最新状态
        await self._wait_event(state, timeout=self._long_poll)
        return self._to_response(state)

    async def submit_code(
        self,
        task_id: str,
        *,
        actor_kind: ActorKind,
        actor_id: int,
        code: str,
    ) -> EALoginTaskResponse:
        state = self._require_owned(task_id, actor_kind, actor_id)
        if state.status != EALoginTaskStatus.AWAITING_2FA_CODE:
            raise _InvalidStateTaskError(f"当前状态 {state.status.value} 不可提交验证码")
        try:
            state.code_input.put_nowait(code)
        except asyncio.QueueFull as e:
            raise _InvalidStateTaskError("验证码已提交，请等待状态更新") from e
        await self._wait_event(state, timeout=self._long_poll)
        return self._to_response(state)

    async def cancel(
        self, task_id: str, *, actor_kind: ActorKind, actor_id: int
    ) -> EALoginTaskResponse:
        state = self._require_owned(task_id, actor_kind, actor_id)
        await self._cancel(state)
        return self._to_response(state)

    async def wait_for_change(
        self,
        task_id: str,
        *,
        actor_kind: ActorKind,
        actor_id: int,
        since_version: int,
    ) -> EALoginTaskResponse:
        """长轮询：当前版本 > ``since_version`` 立刻返回，否则等到下一次推进或超时。"""
        state = self._require_owned(task_id, actor_kind, actor_id)
        if state.version > since_version:
            return self._to_response(state)
        await self._wait_event(state, timeout=self._long_poll)
        return self._to_response(state)

    async def close_all(self) -> None:
        for state in list(self._tasks.values()):
            await self._cancel(state)
            if state.cleanup_handle is not None and not state.cleanup_handle.done():
                state.cleanup_handle.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await state.cleanup_handle
        self._tasks.clear()

    # ===== 内部：owner 校验 =====

    def _require_owned(self, task_id: str, actor_kind: ActorKind, actor_id: int) -> _TaskState:
        state = self._tasks.get(task_id)
        if state is None or state.actor_kind != actor_kind or state.actor_id != actor_id:
            raise _MissingTaskError()
        return state

    async def _cancel_in_progress_for_actor(self, actor_kind: ActorKind, actor_id: int) -> None:
        for state in list(self._tasks.values()):
            if (
                state.actor_kind == actor_kind
                and state.actor_id == actor_id
                and state.status not in TERMINAL_STATUSES
            ):
                await self._cancel(state)

    async def _cancel(self, state: _TaskState) -> None:
        if state.status in TERMINAL_STATUSES:
            return
        state.status = EALoginTaskStatus.CANCELLED
        state.error_code = "EA_LOGIN_CANCELLED"
        state.error_message = "任务已取消"
        self._bump(state)
        if state.runner is not None and not state.runner.done():
            state.runner.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await state.runner
        with contextlib.suppress(Exception):
            await state.engine.aclose()
        await self._persist(state)
        self._log_state(state, event="cancelled")
        self._schedule_cleanup(state)

    # ===== 后台 runner =====

    async def _run(self, state: _TaskState) -> None:
        """驱动 EALoginEngine 一直到终态。"""
        try:
            outcome = await state.engine.start()
            if outcome.next_step == "need_method":
                state.available_methods = outcome.available_methods
                state.status = EALoginTaskStatus.AWAITING_2FA_METHOD
                self._bump(state)
                await self._persist(state)
                method = await asyncio.wait_for(state.method_input.get(), timeout=self._wait)
                mo = await state.engine.select_method(method)
                state.selected_method = mo.selected_method
                state.masked_destination = mo.masked_destination or None
                state.status = EALoginTaskStatus.AWAITING_2FA_CODE
                self._bump(state)
                await self._persist(state)
            elif outcome.next_step == "need_code":
                state.available_methods = outcome.available_methods
                state.selected_method = outcome.selected_method
                state.masked_destination = outcome.masked_destination or None
                state.status = EALoginTaskStatus.AWAITING_2FA_CODE
                self._bump(state)
                await self._persist(state)
            else:  # next_step == "done"，无 2FA 直接拿到 cookies
                assert outcome.cookies is not None
                await self._finalize(state, outcome.cookies)
                return

            code = await asyncio.wait_for(state.code_input.get(), timeout=self._wait)
            fo = await state.engine.submit_code(code)
            await self._finalize(state, fo.cookies)
        except asyncio.CancelledError:
            # _cancel() 已经处理过状态，直接退出协程
            raise
        except TimeoutError:
            await self._mark_failed(
                state,
                code="EA_LOGIN_2FA_TIMEOUT",
                message="等待用户操作超时，请重新发起登录",
            )
        except EALoginError as e:
            await self._mark_failed(state, code=e.code, message=e.message)
        except Exception as e:
            logger.bind(component="ea_login", task_id=state.task_id).warning(
                "ea_login.unhandled_exception: {} {}",
                type(e).__name__,
                e,
            )
            await self._mark_failed(state, code="EA_LOGIN_UNKNOWN", message="登录失败，请重试")
        finally:
            with contextlib.suppress(Exception):
                await state.engine.aclose()

    async def _finalize(self, state: _TaskState, cookies: LoginCookies) -> None:
        state.status = EALoginTaskStatus.FINALIZING
        self._bump(state)
        await self._persist(state)
        try:
            result = await self._finalizer(state.actor_kind, state.actor_id, cookies)
        except EALoginError as e:
            await self._mark_failed(state, code=e.code, message=e.message)
            return
        except Exception as e:
            logger.bind(component="ea_login", task_id=state.task_id).warning(
                "ea_login.finalize_failed: {} {}", type(e).__name__, e
            )
            await self._mark_failed(
                state,
                code=_FINALIZE_FAILED_CODE,
                message=_FINALIZE_FAILED_MSG,
            )
            return
        state.result = result
        state.status = EALoginTaskStatus.SUCCEEDED
        self._bump(state)
        await self._persist(state)
        self._log_state(state, event="succeeded")
        self._schedule_cleanup(state)

    async def _mark_failed(self, state: _TaskState, *, code: str, message: str) -> None:
        if state.status in TERMINAL_STATUSES:
            return
        state.status = EALoginTaskStatus.FAILED
        state.error_code = code
        state.error_message = message
        self._bump(state)
        await self._persist(state)
        self._log_state(state, event="failed")
        self._schedule_cleanup(state)

    # ===== 状态推进与轮询 =====

    def _bump(self, state: _TaskState) -> None:
        state.version += 1
        state.updated_at = datetime.now(UTC)
        # 唤醒当前所有等待者，再换一个新 Event 给后续等待者使用
        state.change_event.set()
        state.change_event = asyncio.Event()

    async def _wait_event(self, state: _TaskState, *, timeout: float) -> None:
        event = state.change_event
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=timeout)

    # ===== Redis 持久化（可降级）=====

    async def _persist(self, state: _TaskState) -> None:
        try:
            r = await get_redis()
        except Exception as e:
            logger.bind(component="ea_login", task_id=state.task_id).warning(
                "ea_login.redis_unavailable_on_persist: {}", e
            )
            return
        payload = {
            "task_id": state.task_id,
            "scope": state.actor_kind,
            "owner_id": state.actor_id,
            "status": state.status.value,
            "version": state.version,
            "available_methods": state.available_methods,
            "selected_method": state.selected_method,
            "masked_destination": state.masked_destination,
            "error_code": state.error_code,
            "error_message": state.error_message,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
        }
        try:
            await r.set(_redis_key(state.task_id), json.dumps(payload), ex=self._ttl)
        except Exception as e:
            logger.bind(component="ea_login", task_id=state.task_id).warning(
                "ea_login.redis_set_failed: {}", e
            )

    # ===== 终态后的延迟清理 =====

    def _schedule_cleanup(self, state: _TaskState) -> None:
        if state.cleanup_handle is not None:
            return
        state.cleanup_handle = asyncio.create_task(self._cleanup_after_ttl(state))

    async def _cleanup_after_ttl(self, state: _TaskState) -> None:
        try:
            await asyncio.sleep(self._ttl)
        except asyncio.CancelledError:
            return
        self._tasks.pop(state.task_id, None)
        try:
            r = await get_redis()
            await r.delete(_redis_key(state.task_id))
        except Exception as e:
            logger.bind(component="ea_login", task_id=state.task_id).debug(
                "ea_login.redis_delete_failed: {}", e
            )

    # ===== 输出与日志 =====

    def _to_response(self, state: _TaskState) -> EALoginTaskResponse:
        return EALoginTaskResponse(
            task_id=state.task_id,
            status=state.status,
            version=state.version,
            available_methods=state.available_methods,
            selected_method=state.selected_method,
            masked_destination=state.masked_destination,
            error_code=state.error_code,
            error_message=state.error_message,
            result=state.result,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )

    def _log_state(self, state: _TaskState, *, event: str) -> None:
        logger.bind(
            component="ea_login",
            task_id=state.task_id,
            scope=state.actor_kind,
            owner_id=state.actor_id,
            status=state.status.value,
            version=state.version,
        ).info("ea_login.task.{}", event)


# ===== 进程级单例 =====


_instance: EALoginTaskManager | None = None


def init_task_manager(finalizer: FinalizerFunc) -> EALoginTaskManager:
    """在 FastAPI lifespan 内调用，注册全局任务管理器单例。"""
    global _instance  # noqa: PLW0603
    settings = get_settings()
    _instance = EALoginTaskManager(
        finalizer=finalizer,
        ttl_seconds=settings.ea_login_task_ttl_seconds,
        wait_seconds=settings.ea_login_2fa_wait_seconds,
        long_poll_seconds=settings.ea_login_long_poll_seconds,
    )
    return _instance


def get_task_manager() -> EALoginTaskManager:
    if _instance is None:
        raise RuntimeError(
            "EALoginTaskManager 未初始化：FastAPI lifespan 必须调用 init_task_manager"
        )
    return _instance


async def close_task_manager() -> None:
    """供 FastAPI shutdown 调用，释放所有未结束任务的资源。"""
    global _instance  # noqa: PLW0603
    if _instance is None:
        return
    await _instance.close_all()
    _instance = None


__all__ = [
    "ActorKind",
    "EALoginTaskManager",
    "FinalizerFunc",
    "close_task_manager",
    "get_task_manager",
    "init_task_manager",
]
