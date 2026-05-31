"""EA 邮箱密码登录任务的「成功后回填」实现。

职责
----

将 :class:`EALoginEngine` 抓到的 ``remid / sid / gatewaySessionId`` 接力给现有的
:class:`BF1GatewayClient.login`，拿到 BF1 sparta 链路所需的 ``access_token``、
``session``、``persona_id`` 与 persona 详情，最终按 actor 类型加密回填到：

- ``user`` 路径 → :class:`EaBindingService` 写入 ``ea_bindings``。
- ``admin`` 路径 → :class:`EAAccountService` 写入 ``ea_accounts``。

实例由 :func:`init_task_manager` 注入到 ``task_manager``。每次 finalize 独立创建一
个新的 ``AsyncSession``，与 FastAPI 请求生命周期解耦，保证后台 runner 在请求结束
后仍能完成落库。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from loguru import logger

from app.db.session import get_sessionmaker
from app.domain.ea.login.exceptions import UpstreamError
from app.domain.ea.login.login_engine import LoginCookies
from app.domain.ea.login.schemas import EALoginTaskResultData
from app.domain.ea.login.task_manager import ActorKind
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.services.ea_account_service import EAAccountService
from app.services.ea_binding_service import EaBindingService


@contextlib.contextmanager
def _silence_gateway_logs() -> Iterator[None]:
    """临时禁用 ``BF1GatewayClient`` 模块的日志输出。

    现状：``app.domain.games.bf1.gateway`` 内部多处用 ``logger.debug`` /
    ``logger.success`` 打印明文 ``remid`` / ``sid`` / ``access_token`` / ``authcode``，
    该文件在 ``pyproject.toml`` 的 ruff per-file-ignores 中被列入「保留原貌」名单。
    EA 邮箱密码登录链路在调用前后用本上下文临时静音，与阶段 6 的全局 PII redact
    filter 形成双重保险，避免任何明文写入日志。

    注意：``logger.disable`` 是进程全局生效的，会同时影响其他并发的 gateway 调用。
    考虑到 EA 邮箱密码登录是用户偶发操作且静音持续仅数百毫秒，这个副作用可接受。
    """
    logger.disable("app.domain.games.bf1.gateway")
    try:
        yield
    finally:
        logger.enable("app.domain.games.bf1.gateway")


class EALoginFinalizer:
    """task_manager 注入用的回填回调宿主。"""

    async def finalize(
        self,
        actor_kind: ActorKind,
        actor_id: int,
        cookies: LoginCookies,
    ) -> EALoginTaskResultData:
        """``FinalizerFunc`` 的标准入口。

        独立 ``AsyncSession`` 内执行；任何异常都回滚并向上抛，由 task_manager 统一
        映射成 ``EA_LOGIN_FINALIZE_FAILED``。
        """
        async with get_sessionmaker()() as db:
            try:
                return await self._run(db, actor_kind, actor_id, cookies)
            except Exception:
                await db.rollback()
                raise

    async def _run(
        self,
        db,
        actor_kind: ActorKind,
        actor_id: int,
        cookies: LoginCookies,
    ) -> EALoginTaskResultData:
        client = BF1GatewayClient(pid=0, remid=cookies.remid, sid=cookies.sid)
        try:
            (
                persona_id,
                display_name,
                avatar_url,
                session,
                refreshed_remid,
                refreshed_sid,
                access_token,
            ) = await self._exchange_bf1_session(client, cookies)
        finally:
            with contextlib.suppress(Exception):
                http_session = getattr(client, "http_session", None)
                if http_session is not None:
                    await http_session.close()

        if actor_kind == "user":
            binding = await EaBindingService(db).upsert_after_ea_login(
                user_id=actor_id,
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                remid=refreshed_remid,
                sid=refreshed_sid,
                session=session,
                access_token=access_token,
            )
            return EALoginTaskResultData(
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                binding_id=binding.id,
            )

        # actor_kind == "admin"
        account = await EAAccountService(db).upsert_after_ea_login(
            persona_id=persona_id,
            display_name=display_name,
            remid=refreshed_remid,
            sid=refreshed_sid,
            session=session,
            access_token=access_token,
        )
        return EALoginTaskResultData(
            persona_id=persona_id,
            display_name=display_name,
            avatar_url=avatar_url,
            account_id=account.id,
        )

    async def _exchange_bf1_session(
        self, client: BF1GatewayClient, cookies: LoginCookies
    ) -> tuple[int, str | None, str | None, str, str, str, str | None]:
        """调用 ``BF1GatewayClient.login`` 并查询 persona 详情。

        Returns:
            ``(persona_id, display_name, avatar_url, session, remid, sid, access_token)``。
            其中 ``remid`` / ``sid`` 优先取 gateway 刷新后的新值，回退到 EA 登录链路
            原始 cookies；保证 ea_bindings / ea_accounts 落库的是最新有效凭据。
        """
        with _silence_gateway_logs():
            session = await client.login(cookies.remid, cookies.sid)
        if (
            session is None
            or not isinstance(session, str)
            or not client.check_login
            or not client.pid
        ):
            raise UpstreamError(
                "BF1 session 获取失败，EA 凭据可能在最终阶段被拒",
                stage="finalize",
            )

        persona_id = int(client.pid)
        display_name: str | None = None
        avatar_url: str | None = None
        try:
            with _silence_gateway_logs():
                personas = await client.getPersonasByIds([persona_id])
            if isinstance(personas, dict):
                pmap = personas.get("result", {}).get("personas", {})
                info = pmap.get(str(persona_id), {})
                display_name = info.get("displayName")
                avatar_url = info.get("avatar")
        except Exception as e:
            # persona 详情查询失败不致命：binding/account 仍可以无 display_name 落库，
            # 后续 verify 流程会重试。把异常用 debug 落日志做诊断即可。
            logger.bind(component="ea_login", persona_id=persona_id).debug(
                "ea_login.persona_detail_failed: {}", e
            )

        return (
            persona_id,
            display_name,
            avatar_url,
            session,
            client.remid or cookies.remid,
            client.sid or cookies.sid,
            client.access_token,
        )


__all__ = ["EALoginFinalizer"]
