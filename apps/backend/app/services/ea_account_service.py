"""EA 账号池服务：取可用账号、解密凭据、登记调用结果"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError
from app.core.security import get_cipher
from app.domain.ea.account_pool import EACredentials
from app.models import EAAccount


class EAAccountService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def pick_available(self) -> EACredentials:
        """取一个可用 EA 账号。MVP 阶段策略：最久未使用的 enabled 账号。"""
        stmt = (
            select(EAAccount)
            .where(EAAccount.enabled.is_(True))
            .order_by(EAAccount.last_used_at.asc().nulls_first())
            .limit(1)
        )
        account = await self.db.scalar(stmt)
        if account is None:
            raise EAApiError(
                code="NO_EA_ACCOUNT_AVAILABLE",
                message="平台未配置可用 EA 账号，无法代查询 EA API",
            )

        cipher = get_cipher()
        return EACredentials(
            persona_id=account.persona_id,
            display_name=account.display_name,
            remid=cipher.decrypt(account.encrypted_remid),
            sid=cipher.decrypt(account.encrypted_sid),
            session=cipher.decrypt(account.encrypted_session)
            if account.encrypted_session
            else None,
            access_token=cipher.decrypt(account.encrypted_access_token)
            if account.encrypted_access_token
            else None,
        )

    async def mark_used(self, persona_id: int) -> None:
        account = await self.db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))
        if account is None:
            return
        account.last_used_at = datetime.now(UTC)
        account.failure_count = 0
        await self.db.commit()

    async def mark_failure(self, persona_id: int) -> None:
        account = await self.db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))
        if account is None:
            return
        account.failure_count += 1
        if account.failure_count >= 10:
            account.enabled = False
        await self.db.commit()

    async def update_session(
        self,
        persona_id: int,
        *,
        sid: str | None = None,
        session: str | None = None,
    ) -> None:
        """gateway 刷新 cookie 后通过 callback 调用本方法"""
        account = await self.db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))
        if account is None:
            return
        cipher = get_cipher()
        if sid is not None:
            account.encrypted_sid = cipher.encrypt(sid)
        if session is not None:
            account.encrypted_session = cipher.encrypt(session)
        await self.db.commit()
