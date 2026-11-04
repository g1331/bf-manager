"""BF1 客户端获取策略（凭据来源抽象）

服管操作统一用 GroupFirstBF1ClientProvider：群组服务账号 → 发起者 binding 里留存的老凭据 →
号池里恰好是这台服服主或管理员的账号 → 都不行就报错。号池里不是本服管理员的账号不拿来兜底。

封装「按何种策略选择 EA 凭据」的决策。BindingFirstBF1ClientProvider 优先用发起者
自己的 EA binding 凭据（EA 后端看到的操作者即 admin 本人），不可用时降级到全局
ea_accounts 后台账号池；PooledBF1ClientProvider 始终走账号池。未来引入群组绑定
账号路由时（见 https://github.com/g1331/bf-manager/issues/1 第 2 层），在两者之间
插入新的凭据源即可，service 与路由层不感知凭据来源。

provider.acquire() 返回一个 async context manager，进入时构造已登录 client，
退出时清理资源（http session、池标记等）。若 provider 判断无可用凭据源，
应在 acquire 进入阶段抛出 EaBindingRequiredError。

provider 可选暴露 ``credential_source`` 属性（"group_account" / "binding" / "pool_admin" /
"pool"），在 acquire
进入阶段写入本次实际使用的凭据来源，供 service 层写进审计 payload 排查降级。
该属性不属于 Protocol 约定，消费方必须用 getattr 软读取。
"""

from __future__ import annotations

import sys
import time
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol, cast, runtime_checkable

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import EAApiError, ForbiddenError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.domain.games.bf1.gateway_errors import EAGatewayError, gateway_failure
from app.models import GroupEaAccount, User
from app.services import group_server_service
from app.services.bf1.gateway_factory import (
    get_bf1_client,
    get_bf1_client_for_binding,
    get_bf1_client_for_group_account,
    get_bf1_client_for_pool_account,
)
from app.services.bf1.server_service import BF1ServerService
from app.services.ea_account_service import EAAccountService, blaze_persona, reserved_personas
from app.services.ea_binding_service import EaBindingService

# 服主 + 管理员名单的缓存：自动换图、计时 VIP 这些后台任务每轮都要挑执行账号，不缓存的话
# 没有群服务账号的服每轮都多一次 getFullServerDetails
_ADMIN_IDS_TTL_SECONDS = 120
_admin_ids_cache: dict[int, tuple[float, frozenset[int]]] = {}


async def server_admin_ids(
    db: AsyncSession, game_id: int, *, fresh: bool = False
) -> frozenset[int]:
    """这台服 EA 侧的服主和管理员 persona_id。不是 RSP 私服或查不到时为空；EA 暂时不可用时抛 EAApiError"""
    now = time.monotonic()
    cached = _admin_ids_cache.get(game_id)
    if not fresh and cached is not None and cached[0] > now:
        return cached[1]
    info = await BF1ServerService(db).get_admin_identity(game_id)
    ids: frozenset[int] = frozenset()
    if info is not None:
        owner_pid, admin_pids, _, _ = info
        ids = frozenset([*admin_pids, *([owner_pid] if owner_pid else [])])
    _admin_ids_cache[game_id] = (now + _ADMIN_IDS_TTL_SECONDS, ids)
    return ids


async def pool_admin_personas(db: AsyncSession, game_id: int, *, fresh: bool = False) -> list[int]:
    """号池里是这台服服主或管理员的启用账号。卡行动借走的号不算；Blaze 正在用的排最后，
    它的 Gateway 登录态可能没缓存，完整登录会把生产 Blaze 会话挤掉"""
    reserved = reserved_personas()
    usable = [pid for pid in await EAAccountService(db).enabled_personas() if pid not in reserved]
    if not usable:
        return []
    admin_ids = await server_admin_ids(db, game_id, fresh=fresh)
    blaze = blaze_persona()
    pids = [pid for pid in usable if pid in admin_ids]
    return sorted(pids, key=lambda pid: pid == blaze)


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
        self.probe_error: EAGatewayError | None = None

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
            probe = await self._probe_rsp(client)
            if probe is not True:
                if isinstance(probe, EAGatewayError):
                    self.probe_error = probe
                    logger.warning(
                        "发起者 persona_id={} 探测服务器 game_id={} 失败，降级账号池: {!r}",
                        binding.persona_id,
                        self.game_id,
                        probe,
                    )
                else:
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

    async def _probe_rsp(self, client: BF1GatewayClient) -> bool | EAGatewayError:
        return await _probe_rsp(client, self.game_id)


class ExecutorUnavailableError(ForbiddenError):
    """群组服务账号和发起者自己的凭据都用不了（不是这台服的管理员、登录失败或根本没有）"""

    def __init__(self) -> None:
        super().__init__(
            "没有能执行服管操作的 EA 账号：请群主把这台服挂到群上并指定一个是本服管理员的服务账号"
        )


async def _probe_rsp(client: BF1GatewayClient, game_id: int) -> bool | EAGatewayError:
    """rspInfo.server.serverId 存在才算这个凭据是本服 RSP 管理员（serverInfo 里的非管理员也能看到）。

    EA 暂时不可用时返回那个错误：分不清是不是管理员，调用方别把它当成「不是」。
    """
    try:
        res = await client.getFullServerDetails(game_id)
    except Exception as exc:
        logger.warning("探测服务器详情异常 game_id={}: {}", game_id, exc)
        return False
    err = gateway_failure(res)
    if err is not None:
        return err if err.retryable else False
    raw = cast(dict[str, Any], res).get("result") or {}
    rsp_server = (raw.get("rspInfo") or {}).get("server") or {}
    return bool(rsp_server.get("serverId"))


def _probe_unavailable(err: EAGatewayError) -> EAApiError:
    return EAApiError(
        code="EA_EXECUTOR_PROBE_FAILED",
        message=f"EA 暂时不可用，没能确认执行账号的管理员身份：{err}",
        details={"kind": err.kind, "ea_code": err.code, "ea_message": err.ea_message},
        retryable=True,
    )


class GroupFirstBF1ClientProvider:
    """服管操作的凭据：群组服务账号优先，其次发起者 binding 留存的老凭据。

    1. 发起者所在、且挂着这台服的群给这台服指定的服务账号（可能有多个群，正常的排前面），
       逐个登录并探测是不是本服 RSP 管理员；
    2. 发起者自己的 binding 凭据（只有 remid 时代留下来的老凭据才有）；
    3. 号池里恰好是这台服服主或管理员的账号（按 EA 公开的管理员名单认，不逐个登录探测）；
    4. pool_fallback=True 时走号池（只给不需要管理员身份的调用方留着），否则抛
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
        # 探测时遇到的暂时性故障：没有账号可用时据此报「EA 暂时不可用」而不是「没有管理员账号」
        self._probe_error: EAGatewayError | None = None
        # 查本服管理员名单时 EA 暂时不可用，用途同上
        self._pool_error: EAApiError | None = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BF1GatewayClient]:
        self._probe_error = None
        self._pool_error = None
        entered = await self._try_group_accounts()
        if entered is not None:
            self.credential_source = "group_account"
        else:
            binding_provider = BindingFirstBF1ClientProvider(
                self.db, user=self.user, game_id=self.game_id, pool_fallback=False
            )
            via_binding = await binding_provider._try_enter_binding()
            self._probe_error = self._probe_error or binding_provider.probe_error
            if via_binding is not None:
                cm, client = via_binding
                entered = (cm, client, int(client.pid or 0))
                self.credential_source = "binding"
        if entered is None:
            entered = await self._try_pool_admin_accounts()
            if entered is not None:
                self.credential_source = "pool_admin"
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
            if self._probe_error is not None:
                raise _probe_unavailable(self._probe_error)
            if self._pool_error is not None:
                raise self._pool_error
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
                probe = await _probe_rsp(client, self.game_id)
                if isinstance(probe, EAGatewayError):
                    logger.warning(
                        "服务账号 {} 探测服务器 game_id={} 失败，换下一个: {!r}",
                        account.persona_id,
                        self.game_id,
                        probe,
                    )
                    self._probe_error = probe
                    await cm.__aexit__(None, None, None)
                    continue
                if not probe:
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

    async def _try_pool_admin_accounts(
        self,
    ) -> tuple[AbstractAsyncContextManager[BF1GatewayClient], BF1GatewayClient, int] | None:
        try:
            candidates = await pool_admin_personas(self.db, self.game_id)
        except EAApiError as exc:
            logger.warning("查服务器 game_id={} 的管理员名单失败: {!r}", self.game_id, exc)
            if exc.retryable:
                self._pool_error = exc
            return None
        for persona_id in candidates:
            cm = get_bf1_client_for_pool_account(self.db, persona_id)
            try:
                client = await cm.__aenter__()
            except Exception as exc:
                logger.warning("号池账号 {} 登录异常: {!r}", persona_id, exc)
                continue
            if not client.access_token:
                logger.warning("号池账号 {} 登录失败，换下一个", persona_id)
                await cm.__aexit__(None, None, None)
                continue
            return cm, client, persona_id
        return None

    async def _record_failure(self, account: GroupEaAccount, error: str) -> None:
        """登录失败计数马上提交：这次请求多半以 403 收场，跟着请求回滚的话永远攒不到失效阈值。
        取执行账号发生在服管操作之前，此时会话里只有鉴权顺手写的数据，一并提交无妨"""
        await group_server_service.record_account_result(self.db, account, False, error)
        await self.db.commit()
