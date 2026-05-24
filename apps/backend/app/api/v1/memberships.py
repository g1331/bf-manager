"""服管权限授予路由（仅平台 admin 可访问）"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbDep
from app.api.errors import ForbiddenError
from app.models import User
from app.schemas.membership import MembershipItem, MembershipPage, MembershipUpsertRequest
from app.services.membership_service import MembershipService

router = APIRouter()


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise ForbiddenError(message="仅平台管理员可管理服管权限")


@router.get("", response_model=MembershipPage)
async def list_memberships(
    db: DbDep,
    user: CurrentUser,
    game: str | None = Query(None, max_length=16),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> MembershipPage:
    _require_admin(user)
    items, total = await MembershipService(db).list(game=game, page=page, page_size=page_size)
    return MembershipPage(items=items, total=total)


@router.post("", response_model=MembershipItem)
async def upsert_membership(
    payload: MembershipUpsertRequest,
    db: DbDep,
    user: CurrentUser,
) -> MembershipItem:
    _require_admin(user)
    return await MembershipService(db).upsert(
        target_persona_id=payload.target_persona_id,
        game=payload.game,
        server_id=payload.server_id,
        role=payload.role,
        granted_by_user=user,
    )


@router.delete("/{membership_id}", status_code=204)
async def delete_membership(
    membership_id: int,
    db: DbDep,
    user: CurrentUser,
) -> None:
    _require_admin(user)
    await MembershipService(db).delete(membership_id)
