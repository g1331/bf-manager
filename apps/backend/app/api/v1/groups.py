"""群组：建群、成员与角色、邀请链接、群组记录

不是群成员的人访问 /groups/{id}/… 一律 404。邀请链接的查看接口不要求登录
（没账号的人也要能看到是哪个群在邀请他），按 IP 限流。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.client_ip import client_ip
from app.api.deps import CurrentUser, DbDep
from app.api.rate_limit import rate_limit
from app.core.config import get_settings
from app.models import Group, GroupInvite, GroupMember, User
from app.schemas.group import (
    GroupAuditItem,
    GroupAuditPage,
    GroupCreateRequest,
    GroupDetailResponse,
    GroupInviteItem,
    GroupListResponse,
    GroupMemberItem,
    GroupPresenceResponse,
    GroupRenameRequest,
    GroupSummaryItem,
    InviteAcceptResponse,
    InviteCreateRequest,
    InviteCreateResponse,
    InviteListResponse,
    InviteLookupResponse,
    InviteTokenRequest,
    MemberRoleRequest,
    MemberServer,
    PresenceGroupItem,
    PresenceMemberItem,
)
from app.services import account_service, group_service, site_settings_service
from app.services.bf1.presence_cache import read_presence
from app.services.bf1.server_snapshot_cache import read_server_snapshot

router = APIRouter()
invite_router = APIRouter()


def _display(user: User | None) -> str | None:
    if user is None:
        return None
    binding = account_service.primary_binding(user)
    return (binding.display_name if binding else None) or user.username


async def _users(db: DbDep, ids: set[int]) -> dict[int, User]:
    ids.discard(0)
    if not ids:
        return {}
    rows = await db.scalars(
        select(User).options(selectinload(User.ea_bindings)).where(User.id.in_(ids))
    )
    return {u.id: u for u in rows.all()}


def _member_item(m: GroupMember, me: User) -> GroupMemberItem:
    binding = account_service.primary_binding(m.user)
    return GroupMemberItem(
        user_id=m.user_id,
        username=m.user.username,
        display_name=binding.display_name if binding else None,
        avatar_url=binding.avatar_url if binding else None,
        persona_id=binding.persona_id if binding else None,
        role=m.role,  # type: ignore[arg-type]
        pending_binding=m.user.status == "pending_binding",
        joined_at=m.joined_at,
        is_me=m.user_id == me.id,
    )


async def _detail(db: DbDep, group_id: int, user: User) -> GroupDetailResponse:
    me = await group_service.require_member(db, group_id, user)
    group = await db.get(Group, group_id)
    assert group is not None
    members = await group_service.list_members(db, group_id)
    return GroupDetailResponse(
        id=group.id,
        name=group.name,
        created_at=group.created_at,
        my_role=me.role,  # type: ignore[arg-type]
        members=[_member_item(m, user) for m in members],
    )


def _invite_item(invite: GroupInvite, users: dict[int, User]) -> GroupInviteItem:
    return GroupInviteItem(
        id=invite.id,
        role=invite.role,  # type: ignore[arg-type]
        max_uses=invite.max_uses,
        uses=invite.uses,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        created_by_name=_display(users.get(invite.created_by or 0)),
    )


# ===== 群 =====


@router.get("", response_model=GroupListResponse)
async def list_groups(user: CurrentUser, db: DbDep) -> GroupListResponse:
    summaries = await group_service.list_my_groups(db, user)
    create_left = None
    if user.role != "admin":
        owned = await db.scalar(
            select(func.count()).select_from(Group).where(Group.created_by == user.id)
        )
        create_left = max(get_settings().group_owned_limit_per_user - int(owned or 0), 0)
    return GroupListResponse(
        items=[
            GroupSummaryItem(
                id=s.group.id,
                name=s.group.name,
                my_role=s.role,  # type: ignore[arg-type]
                member_count=s.member_count,
                created_at=s.group.created_at,
            )
            for s in summaries
        ],
        create_left=create_left,
    )


@router.post("", response_model=GroupDetailResponse, status_code=201)
async def create_group(
    payload: GroupCreateRequest, user: CurrentUser, db: DbDep, request: Request
) -> GroupDetailResponse:
    group = await group_service.create_group(db, user, payload.name, ip=client_ip(request))
    return await _detail(db, group.id, user)


@router.get("/presence", response_model=GroupPresenceResponse)
async def group_presence(user: CurrentUser, db: DbDep) -> GroupPresenceResponse:
    """我所在各群的其他成员此刻在哪个服，给右侧好友栏用。

    所在服来自全服快照的名单缓存，不请求 EA；在服的成员排在前面。
    """
    groups = [
        (s.group, await group_service.list_members(db, s.group.id))
        for s in await group_service.list_my_groups(db, user)
    ]
    pids = {
        binding.persona_id
        for _, members in groups
        for m in members
        if m.user_id != user.id and (binding := account_service.primary_binding(m.user))
    }
    updated_at, presence = await read_presence(sorted(pids))
    servers = (
        {s.game_id: s for s in await read_server_snapshot() or [] if s.game_id is not None}
        if presence
        else {}
    )

    def _server(persona_id: int | None) -> MemberServer | None:
        found = presence.get(persona_id) if persona_id is not None else None
        if found is None:
            return None
        game_id, slot = found
        s = servers.get(game_id)
        return MemberServer(
            game_id=game_id,
            slot=slot,  # type: ignore[arg-type]
            name=s.name if s else None,
            map_display_name=s.map_display_name if s else None,
            mode_display_name=s.mode_display_name if s else None,
            player_count=s.player_count if s else None,
            max_player_count=s.max_player_count if s else None,
        )

    items = []
    for group, members in groups:
        rows = []
        for m in members:
            if m.user_id == user.id:
                continue
            binding = account_service.primary_binding(m.user)
            persona_id = binding.persona_id if binding else None
            rows.append(
                PresenceMemberItem(
                    user_id=m.user_id,
                    username=m.user.username,
                    display_name=binding.display_name if binding else None,
                    avatar_url=binding.avatar_url if binding else None,
                    persona_id=persona_id,
                    role=m.role,  # type: ignore[arg-type]
                    server=_server(persona_id),
                )
            )
        rows.sort(key=lambda r: r.server is None)
        items.append(PresenceGroupItem(id=group.id, name=group.name, members=rows))
    return GroupPresenceResponse(updated_at=updated_at, groups=items)


@router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group(group_id: int, user: CurrentUser, db: DbDep) -> GroupDetailResponse:
    return await _detail(db, group_id, user)


@router.patch("/{group_id}", response_model=GroupDetailResponse)
async def rename_group(
    group_id: int, payload: GroupRenameRequest, user: CurrentUser, db: DbDep, request: Request
) -> GroupDetailResponse:
    await group_service.rename_group(db, group_id, user, payload.name, ip=client_ip(request))
    return await _detail(db, group_id, user)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: int, user: CurrentUser, db: DbDep, request: Request) -> None:
    await group_service.delete_group(db, group_id, user, ip=client_ip(request))


@router.post("/{group_id}/leave", status_code=204)
async def leave_group(group_id: int, user: CurrentUser, db: DbDep, request: Request) -> None:
    await group_service.leave_group(db, group_id, user, ip=client_ip(request))


# ===== 成员 =====


@router.patch("/{group_id}/members/{user_id}", response_model=GroupDetailResponse)
async def set_member_role(
    group_id: int,
    user_id: int,
    payload: MemberRoleRequest,
    user: CurrentUser,
    db: DbDep,
    request: Request,
) -> GroupDetailResponse:
    await group_service.set_member_role(
        db, group_id, user, user_id, payload.role, ip=client_ip(request)
    )
    return await _detail(db, group_id, user)


@router.delete("/{group_id}/members/{user_id}", response_model=GroupDetailResponse)
async def remove_member(
    group_id: int, user_id: int, user: CurrentUser, db: DbDep, request: Request
) -> GroupDetailResponse:
    await group_service.remove_member(db, group_id, user, user_id, ip=client_ip(request))
    return await _detail(db, group_id, user)


# ===== 邀请链接 =====


@router.get("/{group_id}/invites", response_model=InviteListResponse)
async def list_invites(group_id: int, user: CurrentUser, db: DbDep) -> InviteListResponse:
    invites = await group_service.list_live_invites(db, group_id, user)
    users = await _users(db, {i.created_by or 0 for i in invites})
    return InviteListResponse(items=[_invite_item(i, users) for i in invites])


@router.post("/{group_id}/invites", response_model=InviteCreateResponse, status_code=201)
async def create_invite(
    group_id: int,
    payload: InviteCreateRequest,
    user: CurrentUser,
    db: DbDep,
    request: Request,
) -> InviteCreateResponse:
    invite, token = await group_service.create_invite(
        db,
        group_id,
        user,
        role=payload.role,
        max_uses=payload.max_uses,
        ttl_hours=payload.ttl_hours,
        ip=client_ip(request),
    )
    return InviteCreateResponse(invite=_invite_item(invite, {user.id: user}), token=token)


@router.post("/{group_id}/invites/{invite_id}/revoke", status_code=204)
async def revoke_invite(
    group_id: int, invite_id: int, user: CurrentUser, db: DbDep, request: Request
) -> None:
    await group_service.revoke_invite(db, group_id, invite_id, user, ip=client_ip(request))


# ===== 群组记录 =====


@router.get("/{group_id}/audit", response_model=GroupAuditPage)
async def list_audit(
    group_id: int,
    user: CurrentUser,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> GroupAuditPage:
    rows, total = await group_service.list_audit(db, group_id, user, page=page, page_size=page_size)
    ids = {r.user_id or 0 for r in rows} | {int(r.payload.get("target_user_id") or 0) for r in rows}
    users = await _users(db, ids)
    return GroupAuditPage(
        items=[
            GroupAuditItem(
                id=r.id,
                action=r.action,
                actor_name=_display(users.get(r.user_id or 0)),
                target_name=_display(users.get(int(r.payload.get("target_user_id") or 0))),
                # 记录里的 IP 只给平台管理员看（/admin/audit），群里不展示
                payload={k: v for k, v in r.payload.items() if k != "target_user_id"},
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ===== 打开邀请链接 =====


@invite_router.post(
    "/lookup", response_model=InviteLookupResponse, dependencies=[rate_limit("account_link")]
)
async def lookup_invite(payload: InviteTokenRequest, db: DbDep) -> InviteLookupResponse:
    invite = await group_service.find_invite(db, payload.token)
    group = await db.get(Group, invite.group_id)
    assert group is not None
    member_count = await db.scalar(
        select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group.id)
    )
    inviter = (await _users(db, {invite.created_by or 0})).get(invite.created_by or 0)
    # 能不能拿这条链接注册新账号：暂停注册时不能；开放注册时不看名额；邀请注册时看发链接人的名额
    registration = await site_settings_service.get_registration_mode(db)
    if registration == "closed":
        can_register = False
    elif registration == "open":
        can_register = True
    elif inviter is None:
        can_register = False
    else:
        left = await account_service.invite_quota_left(db, inviter)
        can_register = left is None or left > 0
    return InviteLookupResponse(
        group_name=group.name,
        role=invite.role,  # type: ignore[arg-type]
        member_count=int(member_count or 0),
        inviter_name=_display(inviter),
        expires_at=invite.expires_at,
        uses_left=invite.max_uses - invite.uses,
        can_register=can_register,
    )


@invite_router.post(
    "/accept", response_model=InviteAcceptResponse, dependencies=[rate_limit("account_link")]
)
async def accept_invite(
    payload: InviteTokenRequest, user: CurrentUser, db: DbDep, request: Request
) -> InviteAcceptResponse:
    invite = await group_service.find_invite(db, payload.token)
    result = await group_service.join_with_invite(db, invite, user, ip=client_ip(request))
    return InviteAcceptResponse(
        group_id=result.group_id,
        role=result.role,  # type: ignore[arg-type]
        already_member=result.already_member,
    )
