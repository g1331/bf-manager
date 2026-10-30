"""站点级开关的读写。目前只有注册方式。

注册方式三选一：
- open：开放注册，不要邀请码；
- invite：邀请注册，要邀请码或群邀请链接（原来的默认行为）；
- closed：暂停注册，不再新建账号。remid 时代旧账号的认领照常（他们本来就是用户），
  已登录用户不受影响。

值存在 site_settings 表里，每次直接读库（注册、注册页配置都是低频请求，一次主键查询），
所以后台一改，下一个请求就生效。库里没有这一行时按环境变量 REGISTRATION_INVITE_REQUIRED 推默认值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.config import get_settings
from app.models import AuditLog, EaBinding, SiteSetting, User

RegistrationMode = Literal["open", "invite", "closed"]
REGISTRATION_MODES: tuple[RegistrationMode, ...] = ("open", "invite", "closed")
REGISTRATION_KEY = "registration_mode"
# 审计表里站点配置变更的 game 值
AUDIT_GAME = "site"


def default_registration_mode() -> RegistrationMode:
    return "invite" if get_settings().registration_invite_required else "open"


@dataclass(frozen=True)
class RegistrationSetting:
    mode: RegistrationMode
    # 库里没有设置过、用的是环境变量推出来的默认值
    is_default: bool
    updated_at: datetime | None
    updated_by: int | None


async def get_registration(db: AsyncSession) -> RegistrationSetting:
    row = await db.get(SiteSetting, REGISTRATION_KEY, populate_existing=True)
    if row is None or row.value not in REGISTRATION_MODES:
        return RegistrationSetting(default_registration_mode(), True, None, None)
    return RegistrationSetting(
        cast(RegistrationMode, row.value), False, row.updated_at, row.updated_by
    )


async def get_registration_mode(db: AsyncSession) -> RegistrationMode:
    return (await get_registration(db)).mode


async def set_registration_mode(
    db: AsyncSession, mode: str, actor: User, ip: str | None = None
) -> RegistrationSetting:
    if mode not in REGISTRATION_MODES:
        raise AppError(422, "SETTING_INVALID", "注册方式无效")
    before = await get_registration_mode(db)
    row = await db.get(SiteSetting, REGISTRATION_KEY, with_for_update=True)
    if row is None:
        db.add(SiteSetting(key=REGISTRATION_KEY, value=mode, updated_by=actor.id))
    else:
        row.value = mode
        row.updated_by = actor.id
    persona = await db.scalar(
        select(EaBinding.persona_id).where(
            EaBinding.user_id == actor.id, EaBinding.is_primary.is_(True)
        )
    )
    db.add(
        AuditLog(
            user_id=actor.id,
            acting_persona_id=persona or 0,
            game=AUDIT_GAME,
            action="site_registration_mode",
            payload={"from": before, "to": mode},
            result="success",
            ip=ip,
        )
    )
    await db.commit()
    return await get_registration(db)
