"""用户认证服务：EA Cookie 登录链路 + 本地账号登录链路"""

from __future__ import annotations

import contextlib

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, EAApiError, UnauthorizedError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import EaBinding, User
from app.services.ea_binding_service import EaBindingService
from app.services.user_service import UserService


class AuthService:
    """EA Cookie → persona → user + binding → JWT 的登录编排"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserService(db)
        self.bindings = EaBindingService(db)

    async def login_with_cookie(self, remid: str, sid: str) -> tuple[User, EaBinding]:
        """
        1. 用 remid/sid 调 EA accounts.ea.com 拿 access_token + 刷新后的 sid
        2. 调 EA Gateway 拿 persona_id + displayName
        3. 用 persona_id 找/创建 user
        4. AES-GCM 加密凭据，写入或更新对应 ea_bindings 记录
        5. 返回 (user, binding)
        """
        client = BF1GatewayClient(pid=0, remid=remid, sid=sid)
        try:
            session = await client.login(remid, sid)
            if session is None or not isinstance(session, str) or not client.check_login:
                raise UnauthorizedError("EA 凭据无效，请检查 remid / sid")

            persona_id = int(client.pid)

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

            user, _created = await self.users.get_or_create_by_ea_login(persona_id)
            binding = await self.bindings.upsert_after_ea_login(
                user_id=user.id,
                persona_id=persona_id,
                display_name=display_name,
                avatar_url=avatar_url,
                remid=client.remid or remid,
                sid=client.sid or sid,
                session=session,
                access_token=client.access_token,
            )
            return user, binding
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

    async def login_with_local_password(self, username: str, password: str) -> User:
        """本地账号 username + password 登录。失败统一 401，不区分原因。"""
        user = await self.users.verify_local_password(username, password)
        if user is None or not user.is_active:
            raise UnauthorizedError("用户名或密码错误")
        await self.users.mark_login(user)
        return user
