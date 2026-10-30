"""BF1 客户端获取策略（凭据来源抽象）

服管操作统一用 GroupFirstBF1ClientProvider：群组服务账号 → 发起者 binding 里留存的老凭据 →
都不行就报错。号池账号不是用户服务器的管理员，不再给服管操作兜底。

封装「按何种策略选择 EA 凭据」的决策。BindingFirstBF1ClientProvider 优先用发起者
自己的 EA binding 凭据（EA 后端看到的操作者即 admin 本人），不可用时降级到全局
ea_accounts 后台账号池；PooledBF1ClientProvider 始终走账号池。未来引入群组绑定
账号路由时（见 https://github.com/g1331/bf-manager/issues/1 第 2 层），在两者之间
插入新的凭据源即可，service 与路由层不感知凭据来源。

provider.acquire() 返回一个 async context manager，进入时构造已登录 client，
退出时清理资源（http session、池标记等）。若 provider 判断无可用凭据源，
应在 acquire 进入阶段抛出 EaBindingRequiredError。

provider 可选暴露 ``credential_source`` 属性（"group_account" / "binding" / "pool"），在 acquire
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

from app.api.errors import ForbiddenError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import GroupEaAccount, User
from app.services import group_server_service
from app.services.bf1.gateway_factory import (
    get_bf1_client,
    get_bf1_client_for_binding,
    get_bf1_client_for_group_account,
)
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


class BindingUnavailableError(Exception):
    """pool_fallback=False 时发起者的 binding 凭据不可用（未绑定 / 登录失败 / 不是本服 RSP 管理员）"""


class BindingFirstBF1ClientProvider:
    """优先用发起者 primary binding 凭据，不可用时降级到后台账号池。

    pool_fallback=False 时不降级，改为在 acquire 进入阶段抛 BindingUnavailableError：
    号池账号不是私服管理员，后台代人执行名单操作时去试只会白白失败。

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

    def __init__(
        self, db: AsyncSession, *, user: User, game_id: int, pool_fallback: bool = True
    ) -> None:
        self.db = db
        self.user = user
        self.game_id = game_id
        self.pool_fallback = pool_fallback
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
        if not self.pool_fallback:
            raise BindingUnavailableError(
                f"user_id={self.user.id} 的绑定凭据不可用或不是服务器 {self.game_id} 的管理员"
            )
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


class ExecutorUnavailableError(ForbiddenError):
    """群组服务账号和发起者自己的凭据都用不了（不是这台服的管理员、登录失败或根本没有）"""

    def __init__(self) -> None:
        super().__init__(
            "没有能执行服管操作的 EA 账号：请群主把这台服挂到群上并指定一个是本服管理员的服务账号"
        )


async def _probe_rsp(client: BF1GatewayClient, game_id: int) -> bool:
    """rspInfo.server.serverId 存在才算这个凭据是本服 RSP 管理员（serverInfo 里的非管理员也能看到）"""
    try:
        res = await client.getFullServerDetails(game_id)
    except Exception as exc:
        logger.warning("探测服务器详情异常 game_id={}: {}", game_id, exc)
        return False
    if not isinstance(res, dict):
        return False
    raw = res.get("result") or {}
    rsp_server = (raw.get("rspInfo") or {}).get("server") or {}
    return bool(rsp_server.get("serverId"))


class GroupFirstBF1ClientProvider:
    """服管操作的凭据：群组服务账号优先，其次发起者 binding 留存的老凭据。

    1. 发起者所在、且挂着这台服的群给这台服指定的服务账号（可能有多个群，正常的排前面），
       逐个登录并探测是不是本服 RSP 管理员；
    2. 发起者自己的 binding 凭据（只有 remid 时代留下来的老凭据才有）；
    3. pool_fallback=True 时走号池（只给不需要管理员身份的调用方留着），否则抛
       ExecutorUnavailableError。

    挑选全部发生在 acquire 进入阶段；client 交给调用方之后出的错原样抛出，不换账号重试
    （踢人、封禁不是幂等操作）。用了哪个账号记在 credential_source / executor_persona_id，
    写进审计。服务账号登录失败会累计失败次数，连续失败到阈值标失效（随调用方的事务提交）。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        user: User,
        game_id: int,
        server_pk: int | None = None,
        pool_fallback: bool = False,
    ) -> None:
        self.db = db
        self.user = user
        self.game_id = game_id
        self.server_pk = server_pk
        self.pool_fallback = pool_fallback
        self.credential_source: str | None = None
        self.executor_persona_id: int | None = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BF1GatewayClient]:
        entered = await self._try_group_accounts()
        if entered is not None:
            self.credential_source = "group_account"
        else:
            binding_provider = BindingFirstBF1ClientProvider(
                self.db, user=self.user, game_id=self.game_id, pool_fallback=False
            )
            via_binding = await binding_provider._try_enter_binding()
            if via_binding is not None:
                cm, client = via_binding
                entered = (cm, client, int(client.pid or 0))
                self.credential_source = "binding"
        if entered is not None:
            cm, client, persona_id = entered
            self.executor_persona_id = persona_id or None
            try:
                yield client
            except BaseException:
                await cm.__aexit__(*sys.exc_info())
                raise
            else:
                await cm.__aexit__(None, None, None)
            return
        if not self.pool_fallback:
            raise ExecutorUnavailableError()
        self.credential_source = "pool"
        async with get_bf1_client(self.db) as client:
            yield client

    async def _try_group_accounts(
        self,
    ) -> tuple[AbstractAsyncContextManager[BF1GatewayClient], BF1GatewayClient, int] | None:
        accounts = await group_server_service.executor_accounts_for(
            self.db, self.user, game_id=self.game_id, server_pk=self.server_pk
        )
        for account in accounts:
            cm = get_bf1_client_for_group_account(self.db, account)
            try:
                client = await cm.__aenter__()
            except Exception as exc:
                logger.warning("服务账号 {} 登录异常: {!r}", account.persona_id, exc)
                await self._record_failure(account, "登录异常")
                continue
            try:
                if not client.access_token:
                    await cm.__aexit__(None, None, None)
                    await self._record_failure(account, "登录失败")
                    continue
                await group_server_service.record_account_result(self.db, account, True)
                if not await _probe_rsp(client, self.game_id):
                    logger.info(
                        "服务账号 {} 不是服务器 game_id={} 的 RSP 管理员，换下一个",
                        account.persona_id,
                        self.game_id,
                    )
                    await cm.__aexit__(None, None, None)
                    continue
            except BaseException:
                await cm.__aexit__(*sys.exc_info())
                raise
            return cm, client, account.persona_id
        return None

    async def _record_failure(self, account: GroupEaAccount, error: str) -> None:
        """登录失败计数马上提交：这次请求多半以 403 收场，跟着请求回滚的话永远攒不到失效阈值。
        取执行账号发生在服管操作之前，此时会话里只有鉴权顺手写的数据，一并提交无妨"""
        await group_server_service.record_account_result(self.db, account, False, error)
        await self.db.commit()
