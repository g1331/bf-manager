"""EA 邮箱密码登录任务的 service 层。

API 端点应只调用本模块，不要直接 import :mod:`app.domain.ea.login.task_manager`。
本层负责：

1. 解封 ``SecretStr`` 字段（email/password/code），把明文交给 task_manager。
2. 把 task_manager 抛出的内部异常映射成 ``app.api.errors`` 中的 HTTP 错误。

特别注意：解封后的明文绝不再返回给 API 层，也不会被记录到日志。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from app.api.errors import EALoginTaskConflictError, EALoginTaskNotFoundError
from app.domain.ea.login.schemas import (
    EALoginTaskCreateRequest,
    EALoginTaskResponse,
    EALoginTaskSelectMethodRequest,
    EALoginTaskSubmitCodeRequest,
)
from app.domain.ea.login.task_manager import (
    ActorKind,
    _InvalidStateTaskError,
    _MissingTaskError,
    get_task_manager,
)


@contextlib.contextmanager
def _map_errors() -> Iterator[None]:
    """统一把 task_manager 内部异常翻译为 HTTP 错误。

    保持 service 函数本身简洁；调用方 ``with _map_errors(): await mgr.xxx(...)``。
    """
    try:
        yield
    except _MissingTaskError as e:
        raise EALoginTaskNotFoundError() from e
    except _InvalidStateTaskError as e:
        raise EALoginTaskConflictError(message=e.message) from e


async def create_task(
    *,
    actor_kind: ActorKind,
    actor_id: int,
    payload: EALoginTaskCreateRequest,
) -> EALoginTaskResponse:
    mgr = get_task_manager()
    with _map_errors():
        return await mgr.create_task(
            actor_kind=actor_kind,
            actor_id=actor_id,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
        )


async def get_state(
    task_id: str,
    *,
    actor_kind: ActorKind,
    actor_id: int,
    since_version: int | None = None,
) -> EALoginTaskResponse:
    """同步快照查询 + 可选长轮询。

    ``since_version is None`` 直接返回当前状态；否则当当前版本 ``<= since_version``
    时，阻塞等待至下一次状态推进或到达 ``ea_login_long_poll_seconds`` 上限，到点
    返回当前状态由前端自行决定是否续轮询。
    """
    mgr = get_task_manager()
    with _map_errors():
        if since_version is None:
            return await mgr.get_state(task_id, actor_kind=actor_kind, actor_id=actor_id)
        return await mgr.wait_for_change(
            task_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            since_version=since_version,
        )


async def submit_method(
    task_id: str,
    *,
    actor_kind: ActorKind,
    actor_id: int,
    payload: EALoginTaskSelectMethodRequest,
) -> EALoginTaskResponse:
    mgr = get_task_manager()
    with _map_errors():
        return await mgr.submit_method(
            task_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            method=payload.method,
        )


async def submit_code(
    task_id: str,
    *,
    actor_kind: ActorKind,
    actor_id: int,
    payload: EALoginTaskSubmitCodeRequest,
) -> EALoginTaskResponse:
    mgr = get_task_manager()
    with _map_errors():
        return await mgr.submit_code(
            task_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            code=payload.code.get_secret_value(),
        )


async def cancel_task(
    task_id: str,
    *,
    actor_kind: ActorKind,
    actor_id: int,
) -> EALoginTaskResponse:
    mgr = get_task_manager()
    with _map_errors():
        return await mgr.cancel(task_id, actor_kind=actor_kind, actor_id=actor_id)


__all__ = [
    "cancel_task",
    "create_task",
    "get_state",
    "submit_code",
    "submit_method",
]
