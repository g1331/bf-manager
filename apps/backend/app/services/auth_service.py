"""用户认证服务：EA Cookie 登录链路"""

from __future__ import annotations

import contextlib

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, EAApiError, UnauthorizedError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import User
from app.services.user_service import UserService


class AuthService:
    """EA Cookie → persona → JWT 的登录编排"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserService(db)

    async def login_with_cookie(self, remid: str, sid: str) -> User:
        """
        1. 用 remid/sid 调 EA accounts.ea.com 拿 access_token + 刷新后的 sid
        2. 调 EA Gateway 拿 persona_id + displayName
        3. AES-GCM 加密凭据，upsert users 表
        4. 返回 User
        """
        # 临时构造一个 client，pid=0 表示尚未知晓 persona
        client = BF1GatewayClient(pid=0, remid=remid, sid=sid)
        try:
            # gateway.login 内部完成 cookie → token → authcode → session 全流程
            session = await client.login(remid, sid)
            if session is None or not isinstance(session, str) or not client.check_login:
                raise UnauthorizedError("EA 凭据无效，请检查 remid / sid")

            persona_id = int(client.pid)

            # 取 persona 详情。拿不到不影响登录，下次刷新。
            display_name: str | None = None
            avatar_url: str | None = None
            try:
                personas = await client.getPersonasByIds([persona_id])
                if isinstance(personas, dict):
                    persona_map = personas.get("result", {}).get("personas", {})
                    persona_info = persona_map.get(str(persona_id), {})
                    display_name = persona_info.get("displayName")
                    avatar_url = persona_info.get("avatar")
            except Exception as e:
                logger.debug("fetch persona detail failed: {}", e)

            return await self.users.upsert_after_login(
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                remid=client.remid or remid,
                sid=client.sid or sid,
                session=session,
                access_token=client.access_token,
            )
        except AppError:
            raise
        except Exception as e:
            raise EAApiError(
                code="EA_LOGIN_FAILED",
                message="EA 登录失败，请稍后重试",
                details={"reason": str(e)[:200]},
            ) from e
        finally:
            with contextlib.suppress(Exception):
                http_session = getattr(client, "http_session", None)
                if http_session is not None:
                    await http_session.close()
