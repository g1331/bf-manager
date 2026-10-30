"""平台用户服务：身份层读写

身份层不感知 EA 凭据。EA 相关字段由 EaBindingService 管理。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.passwords import hash_password, verify_password_timing_safe
from app.models import EaBinding, User


async def lock_user(db: AsyncSession, user_id: int) -> User | None:
    """在当前事务里锁住用户行（SELECT … FOR UPDATE）并读最新值，连同 EA 绑定一起加载。

    认领、改密码、生成邀请码这类「先检查再写」的操作都要先锁：两个请求并发时，
    后到的一个等前一个提交后，读到的是更新过的状态，再检查一次。
    """
    return await db.scalar(
        select(User)
        .options(selectinload(User.ea_bindings))
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def bump_token_version(db: AsyncSession, user: User) -> None:
    """让这个账号的所有会话失效：在数据库里原子地 +1，而不是读出来在 Python 里加。

    改密码和「退出所有设备」并发时，两次递增都会生效，不会互相覆盖成同一个版本号。
    """
    new_version = await db.scalar(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .returning(User.token_version)
        .execution_options(synchronize_session=False)
    )
    set_committed_value(user, "token_version", new_version)


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
            .where(EaBinding.persona_id == persona_id, EaBinding.is_frozen.is_(False))
        )

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
            email=email.strip().lower() if email else None,
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
        # 用户名不存在时也做一次同等成本的比对，响应时间不泄露用户名是否存在
        if not verify_password_timing_safe(password, user.local_password_hash if user else None):
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
