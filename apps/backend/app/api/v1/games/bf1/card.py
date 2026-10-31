"""BF1 一键卡行动路由（不要求登录）

凭据是服主或管理员的 remid + sid（或登录用户的主绑定），这里只核对它确实是这台服的服主或
管理员。任务开始时返回一次性 token，匿名用户凭它查看、停止、恢复；登录用户自己的任务凭账号即可。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request

from app.api.client_ip import client_ip
from app.api.deps import CurrentUserOptional, DbDep
from app.api.rate_limit import rate_limit
from app.schemas.bf1.card import (
    CardJobView,
    CardPrecheck,
    CardPrecheckRequest,
    CardRestoreRequest,
    CardStartRequest,
    CardStartResult,
)
from app.services.bf1.card_service import CardService, resolve_credentials

router = APIRouter()

TokenHeader = Annotated[str | None, Header(alias="X-Card-Token")]
# 任务页每 2 秒轮询一次进度，用宽松的只读额度
_read = rate_limit("read")


@router.post("/precheck", response_model=CardPrecheck, dependencies=[rate_limit("card_check")])
async def precheck(
    payload: CardPrecheckRequest, db: DbDep, user: CurrentUserOptional
) -> CardPrecheck:
    creds = resolve_credentials(payload, user)
    return await CardService(db).precheck(creds, payload.game_id)


@router.post("/jobs", response_model=CardStartResult, dependencies=[rate_limit("card_start")])
async def start(
    payload: CardStartRequest, db: DbDep, user: CurrentUserOptional, request: Request
) -> CardStartResult:
    creds = resolve_credentials(payload, user)
    job, token = await CardService(db).start(
        creds, payload.game_id, payload.kind, user=user, ip=client_ip(request)
    )
    return CardStartResult(job=job, token=token)


@router.get("/jobs/{job_id}", response_model=CardJobView, dependencies=[_read])
async def get_job(
    job_id: int, db: DbDep, user: CurrentUserOptional, token: TokenHeader = None
) -> CardJobView:
    return await CardService(db).get(job_id, token, user)


@router.post("/jobs/{job_id}/cancel", response_model=CardJobView, dependencies=[_read])
async def cancel_job(
    job_id: int, db: DbDep, user: CurrentUserOptional, token: TokenHeader = None
) -> CardJobView:
    return await CardService(db).cancel(job_id, token, user)


@router.post(
    "/jobs/{job_id}/restore", response_model=CardJobView, dependencies=[rate_limit("card_check")]
)
async def restore_job(
    job_id: int,
    payload: CardRestoreRequest,
    db: DbDep,
    user: CurrentUserOptional,
    token: TokenHeader = None,
) -> CardJobView:
    creds = resolve_credentials(payload, user)
    return await CardService(db).restore(job_id, token, user, creds)
