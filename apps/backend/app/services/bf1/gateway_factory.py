"""BF1 Gateway 客户端构造工厂"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.games.bf1.gateway import BF1GatewayClient
from app.services.ea_account_service import EAAccountService


@asynccontextmanager
async def get_bf1_client(db: AsyncSession) -> AsyncIterator[BF1GatewayClient]:
    """异步上下文：取账号池中可用账号构造 client，使用后清理 http session。

    注意：此工厂只服务于 `ea_accounts` 后台账号池。on_session_refreshed 回调把刷新的 sid
    写回 EAAccountService，传入 pid 必须命中池中行。
    issue #1 的 per-user-binding provider 必须实现自己的工厂，把回调改为
    `EaBindingService(db).update_session(binding_id, sid=..., session=...)`，
    否则刷新出的新 sid 会被 EAAccountService 因 pid 不在池中静默丢弃。
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
