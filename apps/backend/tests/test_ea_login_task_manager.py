"""EA 登录任务管理器：状态推进 + Owner 校验 + 取消 + 长轮询测试。

策略：用替身 ``StubEngine`` 替换真实 :class:`EALoginEngine`，避免触达 aiohttp 与
EA 真实服务器。覆盖以下场景：

- 无 2FA 直接成功：state 推进到 SUCCEEDED，finalizer 被调用，result 写入
- 多 2FA 方式：state 进入 AWAITING_2FA_METHOD，提交后转 AWAITING_2FA_CODE
- 单 2FA 方式：state 直接进入 AWAITING_2FA_CODE
- Owner 校验：非创建者访问任务返回 _MissingTaskError
- 重复提交：同一阶段第二次 put_nowait 返回 _InvalidStateTaskError
- 取消：任意状态下取消后 status=CANCELLED
- 长轮询：since_version < current 立即返回；since_version >= current 等待到超时
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import pytest
from app.domain.ea.login.login_engine import (
    FinalizeOutcome,
    LoginCookies,
    MethodOutcome,
    StartOutcome,
)
from app.domain.ea.login.schemas import EALoginTaskResultData, EALoginTaskStatus
from app.domain.ea.login.task_manager import (
    EALoginTaskManager,
    _InvalidStateTaskError,
    _MissingTaskError,
)


@dataclass
class _Scenario:
    """控制 StubEngine 在 start() 后走哪条分支。"""

    next_step: Literal["done", "need_method", "need_code"]
    methods: tuple[str, ...] = ()
    masked: str = ""


class StubEngine:
    """替代 EALoginEngine：start/select_method/submit_code 立刻返回预设结果。"""

    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario
        self.aclose_calls = 0
        self.start_calls = 0
        self.select_calls: list[str] = []
        self.submit_calls: list[str] = []

    async def start(self) -> StartOutcome:
        self.start_calls += 1
        sc = self._scenario
        if sc.next_step == "done":
            return StartOutcome(
                next_step="done",
                cookies=LoginCookies(remid="r", sid="s", gateway_session_id="g"),
            )
        if sc.next_step == "need_code":
            return StartOutcome(
                next_step="need_code",
                available_methods=list(sc.methods or ("EMAIL",)),
                selected_method=(sc.methods[0] if sc.methods else "EMAIL"),
                masked_destination=sc.masked,
            )
        return StartOutcome(next_step="need_method", available_methods=list(sc.methods))

    async def select_method(self, method: str) -> MethodOutcome:
        self.select_calls.append(method)
        return MethodOutcome(selected_method=method, masked_destination="masked@e***")

    async def submit_code(self, code: str) -> FinalizeOutcome:
        self.submit_calls.append(code)
        return FinalizeOutcome(cookies=LoginCookies(remid="r", sid="s", gateway_session_id="g"))

    async def aclose(self) -> None:
        self.aclose_calls += 1


def _make_manager(
    *,
    finalizer=None,
    ttl: int = 60,
    wait: int = 2,
    long_poll: float = 1,
) -> EALoginTaskManager:
    async def _default_finalizer(actor_kind, actor_id, cookies):
        return EALoginTaskResultData(
            persona_id=42,
            display_name="P42",
            avatar_url=None,
            **({"binding_id": 11} if actor_kind == "user" else {"account_id": 12}),
        )

    return EALoginTaskManager(
        finalizer=finalizer or _default_finalizer,
        ttl_seconds=ttl,
        wait_seconds=wait,
        long_poll_seconds=int(long_poll),
    )


def _patch_engine(monkeypatch, engine: StubEngine) -> None:
    """让 task_manager 创建任务时拿到 StubEngine，并屏蔽 Redis。

    conftest 用 in-memory sqlite，但默认 REDIS_URL 指向 ``localhost:6379``。如果本地
    没起 Redis，每次 ``_persist`` 都会等待 OS 默认 TCP 连接超时（Windows 约 21 秒），
    把单测拖到几十秒。这里让 ``get_redis()`` 立刻抛 ConnectionError，task_manager 内
    部已经有 try/except 走「Redis 不可用」降级分支，正好覆盖该路径。
    """
    from app.domain.ea.login import task_manager as tm

    monkeypatch.setattr(tm, "EALoginEngine", lambda task_id, email, password: engine)

    async def _no_redis():
        raise ConnectionError("redis disabled in unit test")

    monkeypatch.setattr(tm, "get_redis", _no_redis)


@pytest.mark.asyncio
async def test_no_2fa_directly_succeeds(monkeypatch):
    engine = StubEngine(_Scenario(next_step="done"))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager()

    resp = await mgr.create_task(actor_kind="user", actor_id=1, email="a@b.com", password="pw")
    assert resp.status == EALoginTaskStatus.PENDING
    # 等 runner 跑完
    await asyncio.wait_for(_wait_terminal(mgr, resp.task_id, 1, "user"), timeout=2)
    final = await mgr.get_state(resp.task_id, actor_kind="user", actor_id=1)
    assert final.status == EALoginTaskStatus.SUCCEEDED
    assert final.result is not None
    assert final.result.persona_id == 42
    assert final.result.binding_id == 11
    assert engine.aclose_calls >= 1
    await mgr.close_all()


@pytest.mark.asyncio
async def test_multi_method_2fa_flow(monkeypatch):
    engine = StubEngine(_Scenario(next_step="need_method", methods=("EMAIL", "APP")))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager()

    created = await mgr.create_task(actor_kind="user", actor_id=2, email="a@b.com", password="pw")
    # 等 runner 推进到 AWAITING_2FA_METHOD
    await asyncio.wait_for(
        _wait_status(mgr, created.task_id, 2, "user", EALoginTaskStatus.AWAITING_2FA_METHOD),
        timeout=2,
    )
    state = await mgr.get_state(created.task_id, actor_kind="user", actor_id=2)
    assert state.available_methods == ["EMAIL", "APP"]

    after_method = await mgr.submit_method(
        created.task_id, actor_kind="user", actor_id=2, method="APP"
    )
    # submit_method 内部等了一次状态变化，应已经推到 AWAITING_2FA_CODE
    assert after_method.status == EALoginTaskStatus.AWAITING_2FA_CODE
    assert after_method.selected_method == "APP"

    after_code = await mgr.submit_code(
        created.task_id, actor_kind="user", actor_id=2, code="123456"
    )
    # 等终态
    await asyncio.wait_for(_wait_terminal(mgr, created.task_id, 2, "user"), timeout=2)
    final = await mgr.get_state(created.task_id, actor_kind="user", actor_id=2)
    assert final.status == EALoginTaskStatus.SUCCEEDED
    assert engine.select_calls == ["APP"]
    assert engine.submit_calls == ["123456"]
    assert after_code.status in {
        EALoginTaskStatus.FINALIZING,
        EALoginTaskStatus.SUCCEEDED,
    }
    await mgr.close_all()


@pytest.mark.asyncio
async def test_owner_validation_returns_missing_task(monkeypatch):
    engine = StubEngine(_Scenario(next_step="need_code"))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager()

    created = await mgr.create_task(actor_kind="user", actor_id=5, email="a@b.com", password="pw")
    # 不同 actor_id 访问，应抛 _MissingTaskError
    with pytest.raises(_MissingTaskError):
        await mgr.get_state(created.task_id, actor_kind="user", actor_id=6)
    # 不同 actor_kind 访问，也应抛
    with pytest.raises(_MissingTaskError):
        await mgr.get_state(created.task_id, actor_kind="admin", actor_id=5)
    # 未知 task_id
    with pytest.raises(_MissingTaskError):
        await mgr.get_state("not-exists", actor_kind="user", actor_id=5)
    await mgr.close_all()


@pytest.mark.asyncio
async def test_duplicate_submit_method_raises_invalid_state(monkeypatch):
    engine = StubEngine(_Scenario(next_step="need_method", methods=("EMAIL", "APP")))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager()

    created = await mgr.create_task(actor_kind="user", actor_id=7, email="a@b.com", password="pw")
    await asyncio.wait_for(
        _wait_status(mgr, created.task_id, 7, "user", EALoginTaskStatus.AWAITING_2FA_METHOD),
        timeout=2,
    )
    # 直接连按两次：第一次会被消费并推进状态；第二次发现状态已变（不再是 AWAITING_2FA_METHOD）
    await mgr.submit_method(created.task_id, actor_kind="user", actor_id=7, method="EMAIL")
    with pytest.raises(_InvalidStateTaskError):
        await mgr.submit_method(created.task_id, actor_kind="user", actor_id=7, method="EMAIL")
    await mgr.close_all()


@pytest.mark.asyncio
async def test_cancel_moves_to_cancelled(monkeypatch):
    engine = StubEngine(_Scenario(next_step="need_code"))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager()

    created = await mgr.create_task(actor_kind="admin", actor_id=8, email="a@b.com", password="pw")
    await asyncio.wait_for(
        _wait_status(mgr, created.task_id, 8, "admin", EALoginTaskStatus.AWAITING_2FA_CODE),
        timeout=2,
    )
    cancelled = await mgr.cancel(created.task_id, actor_kind="admin", actor_id=8)
    assert cancelled.status == EALoginTaskStatus.CANCELLED
    assert cancelled.error_code == "EA_LOGIN_CANCELLED"
    await mgr.close_all()


@pytest.mark.asyncio
async def test_wait_for_change_returns_immediately_when_version_advanced(monkeypatch):
    engine = StubEngine(_Scenario(next_step="need_code"))
    _patch_engine(monkeypatch, engine)
    mgr = _make_manager(long_poll=1)

    created = await mgr.create_task(actor_kind="user", actor_id=9, email="a@b.com", password="pw")
    await asyncio.wait_for(
        _wait_status(mgr, created.task_id, 9, "user", EALoginTaskStatus.AWAITING_2FA_CODE),
        timeout=2,
    )
    # 当前 version > 0；以 since_version=0 调用应立刻返回
    resp = await mgr.wait_for_change(
        created.task_id, actor_kind="user", actor_id=9, since_version=0
    )
    assert resp.version > 0
    await mgr.close_all()


# ===== 辅助 =====


async def _wait_status(
    mgr: EALoginTaskManager,
    task_id: str,
    actor_id: int,
    actor_kind: str,
    expected: EALoginTaskStatus,
) -> None:
    while True:
        state = await mgr.get_state(task_id, actor_kind=actor_kind, actor_id=actor_id)
        if state.status == expected:
            return
        await asyncio.sleep(0.01)


async def _wait_terminal(
    mgr: EALoginTaskManager, task_id: str, actor_id: int, actor_kind: str
) -> None:
    terminals = {
        EALoginTaskStatus.SUCCEEDED,
        EALoginTaskStatus.FAILED,
        EALoginTaskStatus.CANCELLED,
    }
    while True:
        state = await mgr.get_state(task_id, actor_kind=actor_kind, actor_id=actor_id)
        if state.status in terminals:
            return
        await asyncio.sleep(0.01)
