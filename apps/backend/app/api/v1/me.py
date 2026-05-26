"""当前用户自有资源管理路由：EA 绑定列表与解绑"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.api.errors import NotFoundError
from app.schemas.auth import BindingListItem, BindingListResponse
from app.services.ea_binding_service import EaBindingService

router = APIRouter()


@router.get("/ea-bindings", response_model=BindingListResponse)
async def list_my_bindings(user: CurrentUser, db: DbDep) -> BindingListResponse:
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


@router.post("/ea-bindings/{binding_id}/unbind", status_code=204)
async def unbind(binding_id: int, user: CurrentUser, db: DbDep) -> None:
    """用户主动解绑自有 binding。

    解绑后保留行作为历史记录，但 `is_frozen=true`、`is_primary=false`、所有加密凭据置 NULL。
    若该 binding 原为 primary 且还有其他未冻结 binding，自动提升另一条为新 primary。

    访问非自有 binding 返回 404，不暴露 binding 是否存在。
    """
    service = EaBindingService(db)
    binding = await service.get_by_id(binding_id)
    if binding is None or binding.user_id != user.id:
        raise NotFoundError(resource=f"EA 绑定 {binding_id}")
    await service.unbind(binding)
