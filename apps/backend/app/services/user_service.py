"""用户读写服务"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_cipher
from app.models import User


def _role_for_persona(persona_id: int) -> str:
    """按 env 声明的 admin_persona_ids 决定 role。声明式管理，每次登录都重算。"""
    return "admin" if persona_id in get_settings().admin_persona_id_set else "user"


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_persona_id(self, persona_id: int) -> User | None:
        return await self.db.scalar(select(User).where(User.persona_id == persona_id))

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.scalar(select(User).where(User.id == user_id))

    async def upsert_after_login(
        self,
        *,
        persona_id: int,
        display_name: str | None,
        remid: str,
        sid: str,
        session: str | None,
        access_token: str | None,
        avatar_url: str | None = None,
    ) -> User:
        """登录成功后写入或更新用户记录，凭据 AES-GCM 加密"""
        cipher = get_cipher()
        user = await self.get_by_persona_id(persona_id)
        now = datetime.now(UTC)
        role = _role_for_persona(persona_id)
        if user is None:
            user = User(
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                encrypted_remid=cipher.encrypt(remid),
                encrypted_sid=cipher.encrypt(sid),
                encrypted_session=cipher.encrypt(session) if session else None,
                encrypted_access_token=cipher.encrypt(access_token) if access_token else None,
                role=role,
                last_login_at=now,
            )
            self.db.add(user)
        else:
            user.display_name = display_name or user.display_name
            user.avatar_url = avatar_url or user.avatar_url
            user.encrypted_remid = cipher.encrypt(remid)
            user.encrypted_sid = cipher.encrypt(sid)
            if session:
                user.encrypted_session = cipher.encrypt(session)
            if access_token:
                user.encrypted_access_token = cipher.encrypt(access_token)
            user.role = role
            user.last_login_at = now
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_session(
        self,
        user_id: int,
        *,
        sid: str | None = None,
        session: str | None = None,
        access_token: str | None = None,
    ) -> None:
        """凭据刷新后更新字段"""
        cipher = get_cipher()
        user = await self.get_by_id(user_id)
        if user is None:
            return
        if sid is not None:
            user.encrypted_sid = cipher.encrypt(sid)
        if session is not None:
            user.encrypted_session = cipher.encrypt(session)
        if access_token is not None:
            user.encrypted_access_token = cipher.encrypt(access_token)
        await self.db.commit()
