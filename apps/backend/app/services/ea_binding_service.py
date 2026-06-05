"""EA 绑定服务：管理 ea_bindings 表的生命周期"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_cipher
from app.models import EaBinding


class EaBindingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_persona(self, persona_id: int) -> EaBinding | None:
        return await self.db.scalar(select(EaBinding).where(EaBinding.persona_id == persona_id))

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

    async def upsert_after_ea_login(
        self,
        *,
        user_id: int,
        persona_id: int,
        display_name: str | None,
        avatar_url: str | None,
        remid: str,
        sid: str,
        session: str | None,
        access_token: str | None,
    ) -> EaBinding:
        """EA cookie 登录后写入或更新 binding。

        新建：is_primary=true, is_frozen=false。
        命中已存在：更新所有凭据 + display/avatar + last_verified_at，
        若原为 is_frozen=true 则自动解冻；is_primary 状态不动。
        """
        cipher = get_cipher()
        now = datetime.now(UTC)
        binding = await self.get_by_persona(persona_id)

        if binding is None:
            # 首次出现：若该 user 当前还没有 primary，本条即 primary
            existing_primary = await self.get_primary_for_user(user_id)
            binding = EaBinding(
                user_id=user_id,
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                encrypted_remid=cipher.encrypt(remid),
                encrypted_sid=cipher.encrypt(sid),
                encrypted_session=cipher.encrypt(session) if session else None,
                encrypted_access_token=cipher.encrypt(access_token) if access_token else None,
                is_primary=existing_primary is None,
                is_frozen=False,
                last_verified_at=now,
            )
            self.db.add(binding)
        else:
            if binding.user_id != user_id:
                binding.user_id = user_id
                existing_primary = await self.get_primary_for_user(user_id)
                binding.is_primary = existing_primary is None
            binding.display_name = display_name or binding.display_name
            binding.avatar_url = avatar_url or binding.avatar_url
            if remid:
                binding.encrypted_remid = cipher.encrypt(remid)
            if sid:
                binding.encrypted_sid = cipher.encrypt(sid)
            if session:
                binding.encrypted_session = cipher.encrypt(session)
            if access_token:
                binding.encrypted_access_token = cipher.encrypt(access_token)
            if binding.is_frozen:
                binding.is_frozen = False
            binding.last_verified_at = now

        await self.db.commit()
        await self.db.refresh(binding)
        return binding

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

        await self.db.commit()
