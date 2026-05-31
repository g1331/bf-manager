"""EA 邮箱密码登录任务路由。

两组对称端点：

- ``/api/v1/me/ea-bindings/login-tasks/*``：普通用户绑定自有 EA 账号。
- ``/api/v1/ea-accounts/login-tasks/*``：平台管理员补充后台账号池。

均沿用项目既有的 cookie + JWT 鉴权（``get_current_user`` / ``get_current_admin``）。
统一端点形状：

::

    POST   /                                    创建任务，返回 task_id + 初始 status
    GET    /{task_id}?since_version=N            状态查询；提供 since_version 时启用
                                                 ea_login_long_poll_seconds 窗口的长轮询
    POST   /{task_id}/2fa-method                 选择 2FA 方式
    POST   /{task_id}/2fa-code                   提交 2FA 验证码
    POST   /{task_id}/cancel                     取消任务

请求/响应模型集中在 :mod:`app.domain.ea.login.schemas`；service 编排在
:mod:`app.services.ea_login_task_service`。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentAdmin, CurrentUser
from app.domain.ea.login.schemas import (
    EALoginTaskCreateRequest,
    EALoginTaskResponse,
    EALoginTaskSelectMethodRequest,
    EALoginTaskSubmitCodeRequest,
)
from app.services import ea_login_task_service as svc

me_router = APIRouter()
admin_router = APIRouter()


# ===== 用户端 =====


@me_router.post("", response_model=EALoginTaskResponse, status_code=201)
async def create_my_login_task(
    payload: EALoginTaskCreateRequest, user: CurrentUser
) -> EALoginTaskResponse:
    return await svc.create_task(actor_kind="user", actor_id=user.id, payload=payload)


@me_router.get("/{task_id}", response_model=EALoginTaskResponse)
async def get_my_login_task(
    task_id: str,
    user: CurrentUser,
    since_version: Annotated[
        int | None,
        Query(
            ge=0,
            description=(
                "长轮询参数：客户端上一次拿到的版本号。"
                "提供时若当前版本 <= since_version 则阻塞至下次状态推进或超时。"
            ),
        ),
    ] = None,
) -> EALoginTaskResponse:
    return await svc.get_state(
        task_id,
        actor_kind="user",
        actor_id=user.id,
        since_version=since_version,
    )


@me_router.post("/{task_id}/2fa-method", response_model=EALoginTaskResponse)
async def submit_my_2fa_method(
    task_id: str,
    payload: EALoginTaskSelectMethodRequest,
    user: CurrentUser,
) -> EALoginTaskResponse:
    return await svc.submit_method(task_id, actor_kind="user", actor_id=user.id, payload=payload)


@me_router.post("/{task_id}/2fa-code", response_model=EALoginTaskResponse)
async def submit_my_2fa_code(
    task_id: str,
    payload: EALoginTaskSubmitCodeRequest,
    user: CurrentUser,
) -> EALoginTaskResponse:
    return await svc.submit_code(task_id, actor_kind="user", actor_id=user.id, payload=payload)


@me_router.post("/{task_id}/cancel", response_model=EALoginTaskResponse)
async def cancel_my_login_task(task_id: str, user: CurrentUser) -> EALoginTaskResponse:
    return await svc.cancel_task(task_id, actor_kind="user", actor_id=user.id)


# ===== 管理员端 =====


@admin_router.post("", response_model=EALoginTaskResponse, status_code=201)
async def create_admin_login_task(
    payload: EALoginTaskCreateRequest, admin: CurrentAdmin
) -> EALoginTaskResponse:
    return await svc.create_task(actor_kind="admin", actor_id=admin.id, payload=payload)


@admin_router.get("/{task_id}", response_model=EALoginTaskResponse)
async def get_admin_login_task(
    task_id: str,
    admin: CurrentAdmin,
    since_version: Annotated[
        int | None,
        Query(
            ge=0,
            description=(
                "长轮询参数：客户端上一次拿到的版本号。"
                "提供时若当前版本 <= since_version 则阻塞至下次状态推进或超时。"
            ),
        ),
    ] = None,
) -> EALoginTaskResponse:
    return await svc.get_state(
        task_id,
        actor_kind="admin",
        actor_id=admin.id,
        since_version=since_version,
    )


@admin_router.post("/{task_id}/2fa-method", response_model=EALoginTaskResponse)
async def submit_admin_2fa_method(
    task_id: str,
    payload: EALoginTaskSelectMethodRequest,
    admin: CurrentAdmin,
) -> EALoginTaskResponse:
    return await svc.submit_method(task_id, actor_kind="admin", actor_id=admin.id, payload=payload)


@admin_router.post("/{task_id}/2fa-code", response_model=EALoginTaskResponse)
async def submit_admin_2fa_code(
    task_id: str,
    payload: EALoginTaskSubmitCodeRequest,
    admin: CurrentAdmin,
) -> EALoginTaskResponse:
    return await svc.submit_code(task_id, actor_kind="admin", actor_id=admin.id, payload=payload)


@admin_router.post("/{task_id}/cancel", response_model=EALoginTaskResponse)
async def cancel_admin_login_task(task_id: str, admin: CurrentAdmin) -> EALoginTaskResponse:
    return await svc.cancel_task(task_id, actor_kind="admin", actor_id=admin.id)
