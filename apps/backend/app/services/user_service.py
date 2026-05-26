"""平台用户服务：身份层读写

身份层不感知 EA 凭据。EA 相关字段由 EaBindingService 管理。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password, verify_password
from app.models import EaBinding, User


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.scalar(select(User).where(User.id == user_id))

    async def get_by_username(self, username: str) -> User | None:
        return await self.db.scalar(select(User).where(User.username == username))

    async def get_by_persona_id(self, persona_id: int) -> User | None:
        """通过 binding 反查 user。无 binding 或无对应 user 返回 None。"""
        return await self.db.scalar(
            select(User)
            .join(EaBinding, EaBinding.user_id == User.id)
            .where(EaBinding.persona_id == persona_id)
        )

    async def get_or_create_by_ea_login(self, persona_id: int) -> tuple[User, bool]:
        """根据 persona_id 找 user；找不到则自动开户。

        返回 (user, created)。created=True 表示本次新建。
        新建用户：username=`persona_<id>`、role='user'、local_password_hash=NULL。
        """
        user = await self.get_by_persona_id(persona_id)
        if user is not None:
            user.last_login_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(user)
            return user, False

        user = User(
            username=f"persona_{persona_id}",
            local_password_hash=None,
            email=None,
            role="user",
            is_active=True,
            is_frozen=False,
            last_login_at=datetime.now(UTC),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user, True

    async def create_local_admin(
        self,
        *,
        username: str,
        password: str,
        email: str | None = None,
    ) -> User:
        """CLI 创建本地 admin。同名 username 已存在时抛 ValueError。"""
        existing = await self.get_by_username(username)
        if existing is not None:
            raise ValueError(f"username '{username}' 已存在")
        user = User(
            username=username,
            local_password_hash=hash_password(password),
            email=email,
            role="admin",
            is_active=True,
            is_frozen=False,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def set_local_password(self, user: User, new_password: str) -> None:
        user.local_password_hash = hash_password(new_password)
        await self.db.commit()

    async def verify_local_password(self, username: str, password: str) -> User | None:
        """本地登录校验。username 不存在或密码错误或无本地密码时返回 None。"""
        user = await self.get_by_username(username)
        if user is None or user.local_password_hash is None:
            return None
        if not verify_password(password, user.local_password_hash):
            return None
        return user

    async def mark_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.db.commit()

    async def grant_admin(self, persona_id: int) -> User:
        """CLI grant-admin：把指定 persona 对应 user 的 role 升为 admin。

        要求 user 必须已存在（即该 persona 至少登录过一次）。
        """
        user = await self.get_by_persona_id(persona_id)
        if user is None:
            raise ValueError(f"persona_id={persona_id} 对应的 user 不存在，请先让该用户登录一次")
        user.role = "admin"
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def revoke_admin(self, persona_id: int) -> User:
        user = await self.get_by_persona_id(persona_id)
        if user is None:
            raise ValueError(f"persona_id={persona_id} 对应的 user 不存在")
        user.role = "user"
        await self.db.commit()
        await self.db.refresh(user)
        return user
