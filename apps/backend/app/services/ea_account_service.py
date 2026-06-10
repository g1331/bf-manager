"""EA 账号池服务：取可用账号、解密凭据、登记调用结果"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, NotFoundError, ValidationError
from app.core.security import get_cipher
from app.domain.ea.account_pool import EACredentials
from app.models import EAAccount
from app.schemas.ea_account import (
    EAAccountCreate,
    EAAccountCredentialsUpdate,
    EAAccountDisplayNameUpdate,
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
        use_count=account.use_count,
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
        # 数据库侧原子自增 use_count：账号池小时多个并发请求会命中同一 persona，
        # 读改写会丢失计数，故用 SET use_count = use_count + 1 由数据库保证原子。
        await self.db.execute(
            update(EAAccount)
            .where(EAAccount.persona_id == persona_id)
            .values(
                last_used_at=datetime.now(UTC),
                failure_count=0,
                use_count=EAAccount.use_count + 1,
            )
        )
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

    async def update_display_name(
        self, account_id: int, payload: EAAccountDisplayNameUpdate
    ) -> EAAccountItem:
        """仅更新备注名。备注属于展示层，故不触发任何凭据相关副作用。"""
        account = await self._get_by_id(account_id)
        account.display_name = payload.display_name
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
        if display_name is not None:
            existing.display_name = display_name
        self._apply_credentials(
            existing,
            remid=remid,
            sid=sid,
            session=session,
            access_token=access_token,
        )
        existing.enabled = enabled
        existing.failure_count = 0
        await self.db.commit()
        await self.db.refresh(existing)
        return _to_item(existing)

    async def upsert_after_ea_login(
        self,
        *,
        persona_id: int,
        display_name: str | None,
        remid: str,
        sid: str,
        session: str | None,
        access_token: str | None,
    ) -> EAAccount:
        """EA 邮箱密码登录链路成功后写入或更新后台账号池。

        与 :meth:`EaBindingService.upsert_after_ea_login` 语义对齐：

        - 新建：``persona_id`` 不存在时新增，必须提供 ``remid`` 与 ``sid``，``enabled=True``。
        - 更新：``persona_id`` 已存在时仅覆盖本次提供的非空字段，``enabled`` 复位为
          True、``failure_count`` 清零，相当于「用真人新登录的凭据修复了池子里的旧账号」。

        返回 ORM 实例供调用方取 ``id``；前端永远不会拿到任何明文凭据，落库前由
        :class:`CredentialCipher` 加密。
        """
        if not remid or not sid:
            # EALoginEngine 在拿不到 cookies 时已经抛 CookieExtractionFailed，本检查
            # 仅做最后兜底，避免任何后续调用方误传空串。
            raise ValidationError(message="登录链路缺失 remid / sid，无法回填账号池")

        existing = await self._get(persona_id)
        if existing is None:
            cipher = get_cipher()
            account = EAAccount(
                persona_id=persona_id,
                display_name=display_name,
                encrypted_remid=cipher.encrypt(remid),
                encrypted_sid=cipher.encrypt(sid),
                encrypted_session=cipher.encrypt(session) if session else None,
                encrypted_access_token=(cipher.encrypt(access_token) if access_token else None),
                enabled=True,
                failure_count=0,
            )
            self.db.add(account)
            await self.db.commit()
            await self.db.refresh(account)
            return account

        if display_name is not None:
            existing.display_name = display_name
        self._apply_credentials(
            existing,
            remid=remid,
            sid=sid,
            session=session,
            access_token=access_token,
        )
        existing.enabled = True
        existing.failure_count = 0
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    @staticmethod
    def _apply_credentials(
        account: EAAccount,
        *,
        remid: str | None,
        sid: str | None,
        session: str | None,
        access_token: str | None,
    ) -> None:
        """仅在新值非空时加密覆写，避免空串把上次有效密文抹成 encrypt("")。

        语义参见 :meth:`EaBindingService.upsert_after_ea_login` 同名段落。
        """
        cipher = get_cipher()
        if remid:
            account.encrypted_remid = cipher.encrypt(remid)
        if sid:
            account.encrypted_sid = cipher.encrypt(sid)
        if session:
            account.encrypted_session = cipher.encrypt(session)
        if access_token:
            account.encrypted_access_token = cipher.encrypt(access_token)

    async def verify(self, account_id: int) -> EAAccountVerifyResult:
        """用账号当前凭据触发一次真实 EA 调用，返回连通性结果。

        校验覆盖两条独立链路，二者均通过才判 success：
        1. session 链路：getServersByPersonaIds 走经典 gateway，仅需有效 session。
        2. access_token 链路：_ensure_desktop_token 用 remid/sid 换 EA Desktop SAL
           access_token，按昵称搜索等接口必须走它。session 可能未过期但 remid/sid
           已失效，因此第 1 步通过不代表按昵称查询能用，必须再检 access_token，
           否则会留下「verify 通过、按昵称查询 5xx」的盲区。

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
            servers_res = await client.getServersByPersonaIds([persona_id])
            if not isinstance(servers_res, dict):
                await self.mark_failure(persona_id)
                return EAAccountVerifyResult(
                    success=False,
                    persona_id=persona_id,
                    message=f"session 链路失败：{str(servers_res)[:200]}",
                )

            access_token = await client._ensure_desktop_token()
            if not access_token:
                await self.mark_failure(persona_id)
                return EAAccountVerifyResult(
                    success=False,
                    persona_id=persona_id,
                    message=(
                        "session 链路通过，但 remid/sid 换 access_token 失败，"
                        "按昵称查询等需要 EA Desktop 通道的接口无法使用，"
                        "请从 EA 官网重新登录后用新的 remid/sid 更新凭据"
                    ),
                )
        finally:
            with contextlib.suppress(Exception):
                http_session = getattr(client, "http_session", None)
                if http_session is not None:
                    await http_session.close()

        await self.mark_used(persona_id)
        return EAAccountVerifyResult(success=True, persona_id=persona_id)

    async def _get(self, persona_id: int) -> EAAccount | None:
        return await self.db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))

    async def _get_by_id(self, account_id: int) -> EAAccount:
        account = await self.db.scalar(select(EAAccount).where(EAAccount.id == account_id))
        if account is None:
            raise NotFoundError(resource="EA 账号")
        return account
