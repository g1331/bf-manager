"""BF1 客户端获取策略（凭据来源抽象）

封装「按何种策略选择 EA 凭据」的决策。BindingFirstBF1ClientProvider 优先用发起者
自己的 EA binding 凭据（EA 后端看到的操作者即 admin 本人），不可用时降级到全局
ea_accounts 后台账号池；PooledBF1ClientProvider 始终走账号池。未来引入群组绑定
账号路由时（见 https://github.com/g1331/bf-manager/issues/1 第 2 层），在两者之间
插入新的凭据源即可，service 与路由层不感知凭据来源。

provider.acquire() 返回一个 async context manager，进入时构造已登录 client，
退出时清理资源（http session、池标记等）。若 provider 判断无可用凭据源，
应在 acquire 进入阶段抛出 EaBindingRequiredError。

provider 可选暴露 ``credential_source`` 属性（"binding" / "pool"），在 acquire
进入阶段写入本次实际使用的凭据来源，供 service 层写进审计 payload 排查降级。
该属性不属于 Protocol 约定，消费方必须用 getattr 软读取。
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, runtime_checkable

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import User
from app.services.bf1.gateway_factory import get_bf1_client, get_bf1_client_for_binding
from app.services.ea_binding_service import EaBindingService


@runtime_checkable
class BF1ClientProvider(Protocol):
    """BF1 客户端获取策略接口"""

    def acquire(self) -> AbstractAsyncContextManager[BF1GatewayClient]:
        """返回 async context：进入时拿到已登录 client，退出时清理"""
        ...


class PooledBF1ClientProvider:
    """从全局 ea_accounts 后台账号池取凭据。任何登录用户都可调用。

    该 provider 不依赖发起者的 EA binding，因此无需 user 上下文。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.credential_source: str | None = "pool"

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BF1GatewayClient]:
        async with get_bf1_client(self.db) as client:
            yield client


class BindingFirstBF1ClientProvider:
    """优先用发起者 primary binding 凭据，不可用时降级到后台账号池。

    降级条件（任一命中即静默走池，仅记日志，用户无感知）：

    a. 发起者没有 primary 且未冻结的 binding（本地 admin 天然命中）
    b. binding 凭据不完整（解绑后 encrypted_remid / encrypted_sid 置 NULL）
    c. 解密 / 构造 / 登录过程抛异常
    d. login 后 access_token 仍为空（login() 失败不抛异常，须显式检查）
    e. 发起者不是目标服的 RSP 管理员（用发起者凭据探测 getFullServerDetails，
       严格要求 rspInfo.server.serverId 存在——serverInfo.serverId 非管理员也可见，
       不能作为权限证据）

    不变量：降级判定全部发生在 acquire 进入阶段（探测调用无副作用）。client 交付
    之后（yield 之后）的任何异常原样向上传播，绝不换凭据重试——kick / ban 等操作
    非幂等，超时类错误无法区分是否已生效，二次执行有双重处置风险。
    """

    def __init__(self, db: AsyncSession, *, user: User, game_id: int) -> None:
        self.db = db
        self.user = user
        self.game_id = game_id
        self.credential_source: str | None = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BF1GatewayClient]:
        entered = await self._try_enter_binding()
        if entered is not None:
            cm, client = entered
            self.credential_source = "binding"
            try:
                yield client
            except BaseException:
                await cm.__aexit__(*sys.exc_info())
                raise
            else:
                await cm.__aexit__(None, None, None)
            return
        self.credential_source = "pool"
        async with get_bf1_client(self.db) as client:
            yield client

    async def _try_enter_binding(
        self,
    ) -> tuple[AbstractAsyncContextManager[BF1GatewayClient], BF1GatewayClient] | None:
        """尝试以发起者 binding 凭据进入 client 上下文，任一降级条件命中返回 None。

        成功时返回 (已进入的 context manager, client)，由 acquire 负责退出。
        """
        binding = await EaBindingService(self.db).get_primary_for_user(self.user.id)
        if binding is None:
            return None
        if not binding.encrypted_remid or not binding.encrypted_sid:
            return None

        cm = get_bf1_client_for_binding(self.db, binding)
        try:
            client = await cm.__aenter__()
        except Exception as exc:
            logger.warning(
                "binding 凭据构造/登录异常，降级账号池 user_id={} binding_id={} persona_id={}: {}",
                self.user.id,
                binding.id,
                binding.persona_id,
                exc,
            )
            return None

        try:
            if not client.access_token:
                logger.warning(
                    "binding 凭据登录失败（access_token 为空），降级账号池 "
                    "user_id={} binding_id={} persona_id={}",
                    self.user.id,
                    binding.id,
                    binding.persona_id,
                )
                await cm.__aexit__(None, None, None)
                return None
            if not await self._probe_rsp(client):
                logger.info(
                    "发起者 persona_id={} 不是服务器 game_id={} 的 RSP 管理员，降级账号池",
                    binding.persona_id,
                    self.game_id,
                )
                await cm.__aexit__(None, None, None)
                return None
        except BaseException:
            await cm.__aexit__(*sys.exc_info())
            raise
        return cm, client

    async def _probe_rsp(self, client: BF1GatewayClient) -> bool:
        """用发起者凭据探测目标服详情，rspInfo.server.serverId 存在才算 RSP 管理员。"""
        try:
            res = await client.getFullServerDetails(self.game_id)
        except Exception as exc:
            logger.warning("binding 凭据探测服务器详情异常 game_id={}: {}", self.game_id, exc)
            return False
        if not isinstance(res, dict):
            return False
        raw = res.get("result") or {}
        rsp_server = (raw.get("rspInfo") or {}).get("server") or {}
        return bool(rsp_server.get("serverId"))
