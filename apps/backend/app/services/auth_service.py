"""用户认证服务：本地管理员账号登录 + 绑定 EA 时的 cookie 校验"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError, EAApiError, UnauthorizedError
from app.domain.games.bf1.gateway import BF1GatewayClient
from app.models import User
from app.services.user_service import UserService


@dataclass(frozen=True)
class EaIdentity:
    persona_id: int
    display_name: str | None
    avatar_url: str | None


class AuthService:
    """本地账号登录，以及绑定 EA 时校验 remid / sid"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserService(db)

    async def verify_ea_cookie(self, remid: str, sid: str) -> EaIdentity:
        """用 remid / sid 登录 EA，确认凭据有效并拿到 persona。不保存凭据。"""
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
            return EaIdentity(
                persona_id=persona_id, display_name=display_name, avatar_url=avatar_url
            )
        except AppError:
            raise
        except Exception as e:
            # 原始异常只进日志，不随响应返回给客户端
            logger.warning("EA cookie 校验失败: {!r}", e)
            raise EAApiError(code="EA_LOGIN_FAILED", message="EA 登录失败，请稍后重试") from e
        finally:
            with contextlib.suppress(Exception):
                http_session = getattr(client, "http_session", None)
                if http_session is not None:
                    await http_session.close()

    async def login_with_local_password(self, username: str, password: str) -> User:
        """本地账号 username + password 登录。失败统一 401，不区分原因。

        同步对齐 deps.get_current_user 的拒绝条件（is_active=false 或 is_frozen=true），
        避免登录颁发出来的 JWT 在所有后续请求被中间件拒绝、前端陷入死循环。
        """
        user = await self.users.verify_local_password(username, password)
        if user is None or not user.is_active or user.is_frozen:
            raise UnauthorizedError("用户名或密码错误")
        await self.users.mark_login(user)
        return user
