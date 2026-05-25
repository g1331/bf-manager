"""BF1 客户端获取策略（凭据来源抽象）

封装「按何种策略选择 EA 凭据」的决策。当前默认实现 PooledBF1ClientProvider 从全局
ea_accounts 后台账号池取凭据。未来引入「按发起者身份 + 群组绑定 + 账号池兜底」
路由策略时（见 https://github.com/g1331/bf-manager/issues/1），新增 provider 实现替换或
扩展即可，service 与路由层不感知凭据来源。

provider.acquire() 返回一个 async context manager，进入时构造已登录 client，
退出时清理资源（http session、池标记等）。若 provider 判断无可用凭据源，
应在 acquire 进入阶段抛出 EaBindingRequiredError。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.games.bf1.gateway import BF1GatewayClient
from app.services.bf1.gateway_factory import get_bf1_client


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

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BF1GatewayClient]:
        async with get_bf1_client(self.db) as client:
            yield client
