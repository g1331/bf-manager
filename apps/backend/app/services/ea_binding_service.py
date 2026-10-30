"""EA 绑定服务：管理 ea_bindings 表的生命周期"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import AppError
from app.core.security import get_cipher
from app.models import EaBinding, User


class BindingConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            409,
            "EA_BINDING_CONFLICT",
            "这个 EA 账号已经绑定在其他账号上，一个 EA 账号只能绑一个账号",
        )


@dataclass(frozen=True)
class BindOutcome:
    binding: EaBinding
    # 认领了旧账号时是旧账号的 id：当前账号已被删除，需要重新登录
    claimed_user_id: int | None = None


class EaBindingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_persona(self, persona_id: int) -> EaBinding | None:
        """取这个 EA 号当前（未冻结）的绑定；解绑后的历史行不算"""
        return await self.db.scalar(
            select(EaBinding).where(
                EaBinding.persona_id == persona_id, EaBinding.is_frozen.is_(False)
            )
        )

    async def get_by_id(self, binding_id: int) -> EaBinding | None:
        return await self.db.scalar(select(EaBinding).where(EaBinding.id == binding_id))

    async def list_for_user(self, user_id: int) -> list[EaBinding]:
        rows = (
            await self.db.scalars(
                select(EaBinding)
                .where(EaBinding.user_id == user_id)
                .order_by(
                    EaBinding.is_primary.desc(), EaBinding.last_verified_at.desc().nullslast()
                )
            )
        ).all()
        return list(rows)

    async def get_primary_for_user(self, user_id: int) -> EaBinding | None:
        """取该 user 的 primary 且未冻结 binding，没有则返回 None"""
        return await self.db.scalar(
            select(EaBinding).where(
                EaBinding.user_id == user_id,
                EaBinding.is_primary.is_(True),
                EaBinding.is_frozen.is_(False),
            )
        )

    async def bind_verified_persona(
        self,
        *,
        user: User,
        persona_id: int,
        display_name: str | None,
        avatar_url: str | None,
        verified_via: str,
        ea_user_id: int | None = None,
    ) -> BindOutcome:
        """调用方已经证明 user 拥有这个 EA 号（remid / EA 账号密码登录成功）后写 binding。

        归属规则（方案 8.2）：
        - 没被绑过，或只有冻结的历史行：新建一行，不保存任何凭据；
        - 已经绑在自己身上：只刷新昵称头像；
        - 绑在旧账号（status=legacy）上，且当前账号是刚注册、还没绑 EA 的：认领。把当前账号的
          邮箱和密码挪到旧账号上，删掉当前账号，调用方要让用户重新登录；
        - 其他情况一律拒绝：一个 EA 号同时只能绑在一个账号上，也不能借此把别人的绑定挪走。
        """
        now = datetime.now(UTC)
        existing = await self.db.scalar(
            select(EaBinding)
            .options(selectinload(EaBinding.user))
            .where(EaBinding.persona_id == persona_id, EaBinding.is_frozen.is_(False))
        )
        if existing is not None:
            if existing.user_id == user.id:
                existing.display_name = display_name or existing.display_name
                existing.avatar_url = avatar_url or existing.avatar_url
                existing.last_verified_at = now
                await self.db.commit()
                return BindOutcome(binding=existing)
            owner = existing.user
            if owner.status == "legacy" and user.status == "pending_binding" and user.email:
                email, verified_at, pw = (
                    user.email,
                    user.email_verified_at,
                    user.local_password_hash,
                )
                await self.db.delete(user)
                await self.db.flush()
                owner.email = email
                owner.email_verified_at = verified_at
                owner.local_password_hash = pw
                owner.status = "active"
                owner.token_version += 1
                existing.verified_via = verified_via
                existing.ea_user_id = ea_user_id or existing.ea_user_id
                existing.display_name = display_name or existing.display_name
                existing.avatar_url = avatar_url or existing.avatar_url
                existing.last_verified_at = now
                await self.db.commit()
                return BindOutcome(binding=existing, claimed_user_id=owner.id)
            raise BindingConflictError()

        has_primary = await self.get_primary_for_user(user.id) is not None
        binding = EaBinding(
            user_id=user.id,
            persona_id=persona_id,
            ea_user_id=ea_user_id,
            display_name=display_name,
            avatar_url=avatar_url,
            verified_via=verified_via,
            is_primary=not has_primary,
            is_frozen=False,
            last_verified_at=now,
        )
        self.db.add(binding)
        if user.status == "pending_binding":
            user.status = "active"
        try:
            await self.db.commit()
        except IntegrityError as e:
            # 并发绑定同一个 EA 号：部分唯一索引兜底
            await self.db.rollback()
            raise BindingConflictError() from e
        await self.db.refresh(binding)
        return BindOutcome(binding=binding)

    async def update_session(
        self,
        binding_id: int,
        *,
        sid: str | None = None,
        session: str | None = None,
        access_token: str | None = None,
    ) -> None:
        """凭据刷新后更新对应 binding（用于 BF1GatewayClient on_session_refreshed 回调）"""
        cipher = get_cipher()
        binding = await self.get_by_id(binding_id)
        if binding is None:
            return
        if sid is not None:
            binding.encrypted_sid = cipher.encrypt(sid)
        if session is not None:
            binding.encrypted_session = cipher.encrypt(session)
        if access_token is not None:
            binding.encrypted_access_token = cipher.encrypt(access_token)
        binding.last_verified_at = datetime.now(UTC)
        await self.db.commit()

    async def unbind(self, binding: EaBinding) -> None:
        """用户主动解绑：保留行作为历史记录，清空所有凭据，置 frozen，丢 primary"""
        binding.encrypted_remid = None
        binding.encrypted_sid = None
        binding.encrypted_session = None
        binding.encrypted_access_token = None
        binding.is_frozen = True
        was_primary = binding.is_primary
        binding.is_primary = False
        await self.db.flush()

        if was_primary:
            # 自动提升另一条未冻结 binding 为 primary（按 last_verified_at 最近）
            next_primary = await self.db.scalar(
                select(EaBinding)
                .where(
                    EaBinding.user_id == binding.user_id,
                    EaBinding.id != binding.id,
                    EaBinding.is_frozen.is_(False),
                )
                .order_by(EaBinding.last_verified_at.desc().nullslast())
                .limit(1)
            )
            if next_primary is not None:
                next_primary.is_primary = True

        # 一条未冻结的绑定都不剩：正常账号回到“待绑定 EA”（平台管理员不受影响）
        remaining = await self.db.scalar(
            select(EaBinding.id).where(
                EaBinding.user_id == binding.user_id, EaBinding.is_frozen.is_(False)
            )
        )
        if remaining is None:
            user = await self.db.get(User, binding.user_id)
            if user is not None and user.status == "active" and user.role != "admin":
                user.status = "pending_binding"

        await self.db.commit()
