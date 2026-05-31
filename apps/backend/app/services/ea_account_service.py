"""EA 账号池服务：取可用账号、解密凭据、登记调用结果"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError, ValidationError
from app.core.security import get_cipher
from app.domain.ea.account_pool import EACredentials
from app.models import EAAccount
from app.schemas.ea_account import (
    EAAccountCreate,
    EAAccountCredentialsUpdate,
    EAAccountItem,
    EAAccountVerifyResult,
)


def _to_item(account: EAAccount) -> EAAccountItem:
    """把 ORM 账号转为只含健康状态的读取模型，绝不携带任何明文凭据。"""
    return EAAccountItem(
        id=account.id,
        persona_id=account.persona_id,
        display_name=account.display_name,
        enabled=account.enabled,
        last_used_at=account.last_used_at,
        failure_count=account.failure_count,
        has_session=account.encrypted_session is not None,
        has_access_token=account.encrypted_access_token is not None,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


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

    # ===== 管理端 CRUD（仅平台 admin 经路由调用）=====

    async def list_all(self) -> list[EAAccountItem]:
        """列出全部账号的健康状态，按创建时间倒序。"""
        rows = (
            await self.db.scalars(select(EAAccount).order_by(EAAccount.created_at.desc()))
        ).all()
        return [_to_item(account) for account in rows]

    async def create(self, payload: EAAccountCreate) -> EAAccountItem:
        """创建账号：persona_id 唯一，remid/sid 为必填明文凭据，写入即加密。"""
        existing = await self._get(payload.persona_id)
        if existing is not None:
            raise ValidationError(message=f"persona_id {payload.persona_id} 已存在")
        cipher = get_cipher()
        account = EAAccount(
            persona_id=payload.persona_id,
            display_name=payload.display_name,
            encrypted_remid=cipher.encrypt(payload.remid),
            encrypted_sid=cipher.encrypt(payload.sid),
            encrypted_session=cipher.encrypt(payload.session) if payload.session else None,
            encrypted_access_token=(
                cipher.encrypt(payload.access_token) if payload.access_token else None
            ),
            enabled=payload.enabled,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return _to_item(account)

    async def update_credentials(
        self, account_id: int, payload: EAAccountCredentialsUpdate
    ) -> EAAccountItem:
        """更新账号凭据：仅覆盖本次提供的字段，未提供的保持原值。

        手动更新凭据视为运维已修复账号，因此同步清零失败计数。
        """
        account = await self._get_by_id(account_id)
        cipher = get_cipher()
        if payload.remid is not None:
            account.encrypted_remid = cipher.encrypt(payload.remid)
        if payload.sid is not None:
            account.encrypted_sid = cipher.encrypt(payload.sid)
        if payload.session is not None:
            account.encrypted_session = cipher.encrypt(payload.session)
        if payload.access_token is not None:
            account.encrypted_access_token = cipher.encrypt(payload.access_token)
        account.failure_count = 0
        await self.db.commit()
        await self.db.refresh(account)
        return _to_item(account)

    async def set_enabled(self, account_id: int, enabled: bool) -> EAAccountItem:
        """启用或停用账号。

        启用时同步清零失败计数，避免凭据已修复却因历史计数立刻被再次自动禁用。
        """
        account = await self._get_by_id(account_id)
        account.enabled = enabled
        if enabled:
            account.failure_count = 0
        await self.db.commit()
        await self.db.refresh(account)
        return _to_item(account)

    async def delete(self, account_id: int) -> None:
        """删除账号。"""
        account = await self._get_by_id(account_id)
        await self.db.delete(account)
        await self.db.commit()

    async def upsert(
        self,
        *,
        persona_id: int,
        display_name: str | None = None,
        remid: str | None = None,
        sid: str | None = None,
        session: str | None = None,
        access_token: str | None = None,
        enabled: bool = True,
    ) -> EAAccountItem:
        """按 persona_id 创建或更新，供 CLI 兜底使用。

        新建时 remid/sid 必填；更新时仅覆盖本次提供的字段，并清零失败计数。
        """
        existing = await self._get(persona_id)
        if existing is None:
            if not remid or not sid:
                raise ValidationError(message="新建账号必须提供 remid 与 sid")
            return await self.create(
                EAAccountCreate(
                    persona_id=persona_id,
                    display_name=display_name,
                    remid=remid,
                    sid=sid,
                    session=session,
                    access_token=access_token,
                    enabled=enabled,
                )
            )
        cipher = get_cipher()
        if display_name is not None:
            existing.display_name = display_name
        if remid is not None:
            existing.encrypted_remid = cipher.encrypt(remid)
        if sid is not None:
            existing.encrypted_sid = cipher.encrypt(sid)
        if session is not None:
            existing.encrypted_session = cipher.encrypt(session)
        if access_token is not None:
            existing.encrypted_access_token = cipher.encrypt(access_token)
        existing.enabled = enabled
        existing.failure_count = 0
        await self.db.commit()
        await self.db.refresh(existing)
        return _to_item(existing)

    async def verify(self, account_id: int) -> EAAccountVerifyResult:
        """用账号当前凭据触发一次真实 EA 调用，返回连通性结果。

        复用各战绩接口共用的判定约定：gateway 认证类方法成功返回 dict，失败返回
        错误字符串。结果只反映调用时刻 EA 服务器的响应，不保证与并发写入原子一致。
        """
        # 惰性导入：gateway 的导入链经 gateway_factory 回指本模块，顶层导入会构成循环。
        from app.domain.games.bf1.gateway import BF1GatewayClient  # noqa: PLC0415

        account = await self._get_by_id(account_id)
        cipher = get_cipher()
        persona_id = account.persona_id

        async def _on_refresh(pid: int, new_sid: str | None, new_session: str | None) -> None:
            await self.update_session(pid, sid=new_sid, session=new_session)

        client = BF1GatewayClient(
            pid=persona_id,
            remid=cipher.decrypt(account.encrypted_remid),
            sid=cipher.decrypt(account.encrypted_sid),
            session=cipher.decrypt(account.encrypted_session)
            if account.encrypted_session
            else None,
            on_session_refreshed=_on_refresh,
        )
        try:
            res = await client.getServersByPersonaIds([persona_id])
        finally:
            with contextlib.suppress(Exception):
                http_session = getattr(client, "http_session", None)
                if http_session is not None:
                    await http_session.close()

        if isinstance(res, dict):
            await self.mark_used(persona_id)
            return EAAccountVerifyResult(success=True, persona_id=persona_id)
        await self.mark_failure(persona_id)
        return EAAccountVerifyResult(success=False, persona_id=persona_id, message=str(res)[:256])

    async def _get(self, persona_id: int) -> EAAccount | None:
        return await self.db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))

    async def _get_by_id(self, account_id: int) -> EAAccount:
        account = await self.db.scalar(select(EAAccount).where(EAAccount.id == account_id))
        if account is None:
            raise NotFoundError(resource="EA 账号")
        return account
