"""群组服务账号与绑服

挂在 /groups/{group_id}/… 下：服务账号（remid + sid，或 EA 账号密码登录）、绑服、复核。
群主可以改，群里的管理员只能看。服主视图挂在 BF1 服务器路由下（/bf1/servers/{game_id}/groups）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.client_ip import client_ip
from app.api.deps import CurrentUser, DbDep
from app.api.rate_limit import rate_limit
from app.domain.ea.login.schemas import (
    EALoginTaskCreateRequest,
    EALoginTaskResponse,
    EALoginTaskSelectMethodRequest,
    EALoginTaskSubmitCodeRequest,
)
from app.models import GroupEaAccount
from app.schemas.group import (
    GroupAccountCookieRequest,
    GroupAccountItem,
    GroupAccountListResponse,
    GroupServerBindRequest,
    GroupServerExecutor,
    GroupServerExecutorRequest,
    GroupServerItem,
    GroupServerListResponse,
)
from app.services import ea_login_task_service as login_tasks
from app.services import group_server_service as gss
from app.services.auth_service import AuthService
from app.services.group_service import require_member

router = APIRouter()


def _account_item(a: GroupEaAccount) -> GroupAccountItem:
    return GroupAccountItem.model_validate(gss.account_view(a))


def _server_item(v: gss.GroupServerView) -> GroupServerItem:
    gs, server, executor = v.row, v.server, v.executor
    return GroupServerItem(
        id=gs.id,
        server_id=server.server_id,
        game_id=server.game_id,
        name=server.name,
        bound_by_name=v.bound_by_name,
        bound_via=gs.bound_via,  # type: ignore[arg-type]
        executor=(
            GroupServerExecutor(
                id=executor.id,
                persona_id=executor.persona_id,
                display_name=executor.display_name,
                status=executor.status,  # type: ignore[arg-type]
            )
            if executor
            else None
        ),
        status=gs.status,  # type: ignore[arg-type]
        status_reason=gs.status_reason,
        executor_problem=gs.executor_problem,
        last_verified_at=gs.last_verified_at,
        created_at=gs.created_at,
    )


# ===== 服务账号 =====


@router.get("/{group_id}/accounts", response_model=GroupAccountListResponse)
async def list_accounts(group_id: int, user: CurrentUser, db: DbDep) -> GroupAccountListResponse:
    accounts = await gss.list_accounts(db, group_id, user)
    return GroupAccountListResponse(items=[_account_item(a) for a in accounts])


@router.post(
    "/{group_id}/accounts/cookie",
    response_model=GroupAccountItem,
    status_code=201,
    dependencies=[rate_limit("ea_login")],
)
async def add_account_with_cookie(
    group_id: int,
    payload: GroupAccountCookieRequest,
    user: CurrentUser,
    db: DbDep,
    request: Request,
) -> GroupAccountItem:
    """用 remid / sid 添加服务账号：先在 EA 上登录一次确认凭据有效，再加密保存"""
    # 先查权限，免得非群主也能拿这个接口试 EA 凭据
    await require_member(db, group_id, user, "owner")
    identity = await AuthService(db).verify_ea_cookie(payload.remid, payload.sid)
    account = await gss.save_account(
        db,
        group_id,
        user,
        persona_id=identity.persona_id,
        display_name=identity.display_name,
        remid=payload.remid,
        sid=payload.sid,
        ip=client_ip(request),
    )
    return _account_item(account)


@router.post("/{group_id}/accounts/{account_id}/default", status_code=204)
async def set_default_account(
    group_id: int, account_id: int, user: CurrentUser, db: DbDep, request: Request
) -> None:
    await gss.set_default_account(db, group_id, account_id, user, ip=client_ip(request))


@router.delete("/{group_id}/accounts/{account_id}", status_code=204)
async def remove_account(
    group_id: int, account_id: int, user: CurrentUser, db: DbDep, request: Request
) -> None:
    await gss.remove_account(db, group_id, account_id, user, ip=client_ip(request))


# ===== 走 EA 账号密码登录添加服务账号 =====


@router.post(
    "/{group_id}/accounts/login-tasks",
    response_model=EALoginTaskResponse,
    status_code=201,
    dependencies=[rate_limit("ea_login")],
)
async def create_account_login_task(
    group_id: int, payload: EALoginTaskCreateRequest, user: CurrentUser, db: DbDep
) -> EALoginTaskResponse:
    await require_member(db, group_id, user, "owner")
    return await login_tasks.create_task(
        actor_kind="group", actor_id=user.id, payload=payload, target_account_id=group_id
    )


@router.get("/{group_id}/accounts/login-tasks/{task_id}", response_model=EALoginTaskResponse)
async def get_account_login_task(
    group_id: int,
    task_id: str,
    user: CurrentUser,
    since_version: Annotated[int | None, Query(ge=0)] = None,
) -> EALoginTaskResponse:
    return await login_tasks.get_state(
        task_id, actor_kind="group", actor_id=user.id, since_version=since_version
    )


@router.post(
    "/{group_id}/accounts/login-tasks/{task_id}/2fa-method", response_model=EALoginTaskResponse
)
async def submit_account_login_method(
    group_id: int, task_id: str, payload: EALoginTaskSelectMethodRequest, user: CurrentUser
) -> EALoginTaskResponse:
    return await login_tasks.submit_method(
        task_id, actor_kind="group", actor_id=user.id, payload=payload
    )


@router.post(
    "/{group_id}/accounts/login-tasks/{task_id}/2fa-code", response_model=EALoginTaskResponse
)
async def submit_account_login_code(
    group_id: int, task_id: str, payload: EALoginTaskSubmitCodeRequest, user: CurrentUser
) -> EALoginTaskResponse:
    return await login_tasks.submit_code(
        task_id, actor_kind="group", actor_id=user.id, payload=payload
    )


@router.post(
    "/{group_id}/accounts/login-tasks/{task_id}/cancel", response_model=EALoginTaskResponse
)
async def cancel_account_login_task(
    group_id: int, task_id: str, user: CurrentUser
) -> EALoginTaskResponse:
    return await login_tasks.cancel_task(task_id, actor_kind="group", actor_id=user.id)


# ===== 绑服 =====


@router.get("/{group_id}/servers", response_model=GroupServerListResponse)
async def list_servers(group_id: int, user: CurrentUser, db: DbDep) -> GroupServerListResponse:
    views = await gss.list_servers(db, group_id, user)
    return GroupServerListResponse(items=[_server_item(v) for v in views])


@router.post("/{group_id}/servers", response_model=GroupServerItem, status_code=201)
async def bind_server(
    group_id: int,
    payload: GroupServerBindRequest,
    user: CurrentUser,
    db: DbDep,
    request: Request,
) -> GroupServerItem:
    view = await gss.bind_server(
        db,
        group_id,
        user,
        game_id=payload.game_id,
        account_id=payload.account_id,
        ip=client_ip(request),
    )
    return _server_item(view)


@router.put("/{group_id}/servers/{binding_id}/executor", response_model=GroupServerItem)
async def set_server_executor(
    group_id: int,
    binding_id: int,
    payload: GroupServerExecutorRequest,
    user: CurrentUser,
    db: DbDep,
    request: Request,
) -> GroupServerItem:
    view = await gss.set_server_executor(
        db, group_id, binding_id, payload.account_id, user, ip=client_ip(request)
    )
    return _server_item(view)


@router.delete("/{group_id}/servers/{binding_id}", status_code=204)
async def unbind_server(
    group_id: int, binding_id: int, user: CurrentUser, db: DbDep, request: Request
) -> None:
    await gss.unbind_server(db, group_id, binding_id, user, ip=client_ip(request))


@router.post(
    "/{group_id}/servers/recheck",
    response_model=GroupServerListResponse,
    dependencies=[rate_limit("ea_login")],
)
async def recheck_servers(group_id: int, user: CurrentUser, db: DbDep) -> GroupServerListResponse:
    views = await gss.recheck_group(db, group_id, user)
    return GroupServerListResponse(items=[_server_item(v) for v in views])
