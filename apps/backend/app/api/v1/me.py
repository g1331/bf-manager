"""当前用户自有资源：EA 绑定、密码、邮箱、邀请码"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Request, Response

from app.api.client_ip import client_ip
from app.api.deps import CurrentUser, CurrentUserAnyStatus, DbDep, SessionFactoryDep
from app.api.errors import NotFoundError
from app.api.rate_limit import rate_limit
from app.api.turnstile import require_turnstile
from app.api.v1.auth import MAIL_ACCEPTED, clear_session, issue_session
from app.core.config import get_settings
from app.models import InviteCode
from app.schemas.auth import (
    AcceptedResponse,
    BindingListItem,
    BindingListResponse,
    ChangePasswordRequest,
    CookieBindRequest,
    CookieBindResponse,
    EmailOnlyRequest,
    InviteCodeItem,
    InviteCodeListResponse,
)
from app.services import account_service
from app.services.account_service import AccountError, normalize_email
from app.services.auth_service import AuthService
from app.services.ea_binding_service import EaBindingService

router = APIRouter()


@router.get("/ea-bindings", response_model=BindingListResponse)
async def list_my_bindings(user: CurrentUserAnyStatus, db: DbDep) -> BindingListResponse:
    bindings = await EaBindingService(db).list_for_user(user.id)
    return BindingListResponse(
        items=[
            BindingListItem(
                id=b.id,
                persona_id=b.persona_id,
                display_name=b.display_name,
                avatar_url=b.avatar_url,
                is_primary=b.is_primary,
                is_frozen=b.is_frozen,
                last_verified_at=b.last_verified_at,
            )
            for b in bindings
        ]
    )


@router.post(
    "/ea-bindings/cookie",
    response_model=CookieBindResponse,
    dependencies=[rate_limit("ea_login")],
)
async def bind_with_cookie(
    payload: CookieBindRequest,
    user: CurrentUserAnyStatus,
    db: DbDep,
    response: Response,
) -> CookieBindResponse:
    """用 remid / sid 证明 EA 账号归属并绑定。凭据只用这一次，不保存。

    这个 EA 号挂在旧账号上时会认领旧账号：当前账号的邮箱和密码挪过去，当前会话作废，
    前端提示用同样的邮箱密码重新登录。
    """
    identity = await AuthService(db).verify_ea_cookie(payload.remid, payload.sid)
    outcome = await EaBindingService(db).bind_verified_persona(
        user=user,
        persona_id=identity.persona_id,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        verified_via="cookie",
    )
    if outcome.claimed_user_id is not None:
        clear_session(response)
    return CookieBindResponse(
        claimed=outcome.claimed_user_id is not None,
        persona_id=identity.persona_id,
        display_name=outcome.binding.display_name,
    )


@router.post("/ea-bindings/{binding_id}/unbind", status_code=204)
async def unbind(binding_id: int, user: CurrentUser, db: DbDep) -> None:
    """用户主动解绑自有 binding。

    解绑后保留行作为历史记录，但 `is_frozen=true`、`is_primary=false`、所有加密凭据置 NULL。
    若该 binding 原为 primary 且还有其他未冻结 binding，自动提升另一条为新 primary；
    一条都不剩时账号回到“待绑定 EA”状态。

    访问非自有 binding 返回 404，不暴露 binding 是否存在。
    """
    service = EaBindingService(db)
    binding = await service.get_by_id(binding_id)
    if binding is None or binding.user_id != user.id:
        raise NotFoundError(resource=f"EA 绑定 {binding_id}")
    active = [b for b in user.ea_bindings if not b.is_frozen]
    if user.status == "legacy" and len(active) <= 1:
        # 旧账号没有邮箱，解绑最后一个 EA 号后就再也登不进来了
        raise AccountError("UNBIND_LAST_LEGACY", "请先设置登录邮箱，再解绑这个 EA 账号")
    await service.unbind(binding)


@router.post("/password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUserAnyStatus,
    db: DbDep,
    request: Request,
    response: Response,
    background: BackgroundTasks,
) -> None:
    """改密码。其他设备上的登录全部失效，当前设备换发新会话。"""
    if user.local_password_hash is None:
        raise AccountError("PASSWORD_NOT_SET", "这个账号还没有设置密码，请先设置登录邮箱")
    await account_service.change_password(db, user, payload.current_password, payload.new_password)
    issue_session(response, user)
    if user.email:
        background.add_task(account_service.send_password_changed, user.email, client_ip(request))


@router.post(
    "/email",
    status_code=202,
    response_model=AcceptedResponse,
    dependencies=[rate_limit("account_mail"), require_turnstile()],
)
async def set_email(
    payload: EmailOnlyRequest,
    user: CurrentUserAnyStatus,
    request: Request,
    background: BackgroundTasks,
    session_factory: SessionFactoryDep,
) -> AcceptedResponse:
    """旧账号（remid 登录时代建的）补登录邮箱：发验证信，打开后设置密码。"""
    if user.status != "legacy":
        raise AccountError("EMAIL_ALREADY_SET", "这个账号已经设置过登录邮箱")
    background.add_task(
        account_service.process_set_email_request,
        session_factory,
        user_id=user.id,
        email=normalize_email(payload.email),
        ip=client_ip(request),
    )
    return AcceptedResponse(message=MAIL_ACCEPTED)


def _invite_item(row: InviteCode, now: datetime) -> InviteCodeItem:
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if row.used_at is not None:
        status = "used"
    elif row.revoked_at is not None:
        status = "revoked"
    elif expires_at <= now:
        status = "expired"
    else:
        status = "unused"
    return InviteCodeItem(
        id=row.id,
        code=row.code,
        status=status,  # type: ignore[arg-type]
        expires_at=expires_at,
        used_at=row.used_at,
        created_at=row.created_at,
        via_group_link=account_service.is_group_link_code(row.code),
    )


async def _invite_list(db: DbDep, user: CurrentUser) -> InviteCodeListResponse:
    rows = await account_service.list_invite_codes(db, user)
    now = datetime.now(UTC)
    return InviteCodeListResponse(
        items=[_invite_item(r, now) for r in rows],
        quota_left=await account_service.invite_quota_left(db, user),
        invite_required=get_settings().registration_invite_required,
    )


@router.get("/invite-codes", response_model=InviteCodeListResponse)
async def list_invite_codes(user: CurrentUser, db: DbDep) -> InviteCodeListResponse:
    return await _invite_list(db, user)


@router.post("/invite-codes", response_model=InviteCodeListResponse, status_code=201)
async def create_invite_code(user: CurrentUser, db: DbDep) -> InviteCodeListResponse:
    await account_service.create_invite_code(db, user)
    return await _invite_list(db, user)


@router.post("/invite-codes/{invite_id}/revoke", response_model=InviteCodeListResponse)
async def revoke_invite_code(
    invite_id: int, user: CurrentUser, db: DbDep
) -> InviteCodeListResponse:
    await account_service.revoke_invite_code(db, user, invite_id)
    return await _invite_list(db, user)
