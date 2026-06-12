"""BF1 Gateway 客户端构造工厂"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_cipher
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import EaBinding
from app.services.ea_account_service import EAAccountService
from app.services.ea_binding_service import EaBindingService


@asynccontextmanager
async def get_bf1_client(db: AsyncSession) -> AsyncIterator[BF1GatewayClient]:
    """异步上下文：取账号池中可用账号构造 client，使用后清理 http session。

    注意：此工厂只服务于 `ea_accounts` 后台账号池。on_session_refreshed 回调把刷新的 sid
    写回 EAAccountService，传入 pid 必须命中池中行。
    按发起者 binding 凭据构造 client 请用 :func:`get_bf1_client_for_binding`，
    其回调回写 EaBindingService，两条链路的凭据持久化目标不可混用。
    """
    account_service = EAAccountService(db)
    creds = await account_service.pick_available()

    async def _on_refresh(pid: int, new_sid: str | None, new_session: str | None) -> None:
        await account_service.update_session(pid, sid=new_sid, session=new_session)

    client = BF1GatewayClient(
        pid=creds.persona_id,
        remid=creds.remid,
        sid=creds.sid,
        session=creds.session,
        on_session_refreshed=_on_refresh,
    )
    # BF1GatewayClient 每次请求新建，access_token 不在内存中持久存在；
    # 走 api_call() 的 JSON-RPC 方法靠 get_session() 自动登录，但走独立 HTTP
    # GET 的 getPersonasByName 等会直接判 access_token 为空返回错误。
    # 在工厂层统一确保拿到 client 时已经登录过一次。
    try:
        if not client.access_token and creds.remid and creds.sid:
            await client.login(creds.remid, creds.sid)
        yield client
        await account_service.mark_used(creds.persona_id)
    except Exception:
        await account_service.mark_failure(creds.persona_id)
        raise
    finally:
        with contextlib.suppress(Exception):
            http_session = getattr(client, "http_session", None)
            if http_session is not None:
                await http_session.close()


@asynccontextmanager
async def get_bf1_client_for_binding(
    db: AsyncSession, binding: EaBinding
) -> AsyncIterator[BF1GatewayClient]:
    """异步上下文：用单条 ea_binding 的凭据构造 client，使用后清理 http session。

    与 :func:`get_bf1_client` 的差异：

    - on_session_refreshed 回调按 ``binding.id`` 回写 EaBindingService（回调签名携带
      的 pid 被忽略——binding 按主键寻址，不存在池里「pid 不命中」的丢弃问题）。
    - 不做 mark_used / mark_failure：失败计数与禁用是账号池的健康度概念，用户 binding
      偶发登录失败（EA 5xx / 限流）不应留下持久痕迹，降级决策由调用方负责。
    """
    cipher = get_cipher()
    if not binding.encrypted_remid or not binding.encrypted_sid:
        raise ValueError(f"binding {binding.id} 凭据不完整，无法构造 BF1 client")
    remid = cipher.decrypt(binding.encrypted_remid)
    sid = cipher.decrypt(binding.encrypted_sid)
    session = cipher.decrypt(binding.encrypted_session) if binding.encrypted_session else None

    binding_service = EaBindingService(db)
    binding_id = binding.id

    async def _on_refresh(pid: int, new_sid: str | None, new_session: str | None) -> None:
        await binding_service.update_session(binding_id, sid=new_sid, session=new_session)

    client = BF1GatewayClient(
        pid=binding.persona_id,
        remid=remid,
        sid=sid,
        session=session,
        on_session_refreshed=_on_refresh,
    )
    try:
        # 与池工厂相同的预热语义：保证拿到 client 时已经登录过一次。
        # login() 失败不抛异常，调用方须检查 client.access_token 判定是否登录成功。
        if not client.access_token and remid and sid:
            await client.login(remid, sid)
        yield client
    finally:
        with contextlib.suppress(Exception):
            http_session = getattr(client, "http_session", None)
            if http_session is not None:
                await http_session.close()
