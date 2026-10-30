"""FastAPI 应用入口"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.client_ip import client_ip
from app.api.errors import AppError
from app.api.request_id import RequestIdMiddleware, get_request_id
from app.api.v1.router import api_router
from app.core import ea_metrics
from app.core.cache import close_redis, get_redis
from app.core.config import get_settings
from app.core.ea_metrics import ea_metrics_flusher
from app.core.logging import setup_logging
from app.db.session import close_engine, get_sessionmaker
from app.domain.ea.login.task_manager import close_task_manager, init_task_manager

# 触发游戏 profile 注册
from app.domain.games import GameRegistry  # noqa: F401
from app.services.account_service import account_cleanup_poller
from app.services.bf1.auto_switch_service import auto_switch_poller
from app.services.bf1.blaze_service import close_blaze_pool
from app.services.bf1.card_service import mark_interrupted_jobs, shutdown_card_jobs
from app.services.bf1.exchange_service import exchange_poller
from app.services.bf1.overview_service import overview_poller
from app.services.bf1.round_service import restore_tracker_state, save_tracker_state
from app.services.bf1.timed_vip_service import timed_vip_poller
from app.services.ea_login_finalizer import EALoginFinalizer
from app.services.metrics_service import classify_path, record_request, user_id_from_token


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    logger.info(
        "Starting {} v{} (env={}, games={})",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.games,
    )
    # 预热 Redis 连接
    try:
        r = await get_redis()
        await r.ping()
        logger.info("Redis ping ok")
    except Exception as e:
        logger.warning("Redis init failed: {}", e)

    # EA 邮箱密码登录任务管理器：注入 finalizer 后纳入进程级单例
    init_task_manager(EALoginFinalizer().finalize)

    # BF1 后台轮询：仅在启用 bf1 时启动。全服统计写 Redis 供 /bf1/overview 只读；
    # 交换每小时检查一次换期，入库后供历史查询；行动服自动换图每 5 秒检查开启的服；
    # 计时 VIP 每分钟下掉普通服上到期的 VIP
    pollers: list[asyncio.Task[None]] = [
        asyncio.create_task(ea_metrics_flusher()),
        # 清理超时没绑 EA 的账号、过期的验证链接
        asyncio.create_task(account_cleanup_poller(get_sessionmaker())),
    ]
    if "bf1" in settings.games:
        if settings.bf1_match_tracking:
            await restore_tracker_state()
        await mark_interrupted_jobs()
        pollers += [
            asyncio.create_task(overview_poller()),
            asyncio.create_task(exchange_poller()),
            asyncio.create_task(auto_switch_poller()),
            asyncio.create_task(timed_vip_poller()),
        ]

    yield

    logger.info("Shutting down")
    await shutdown_card_jobs()
    for task in pollers:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if "bf1" in settings.games and settings.bf1_match_tracking:
        await save_tracker_state()
    await close_task_manager()
    await close_blaze_pool()
    await close_redis()
    await close_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    # 生产不公开接口文档：完整的 OpenAPI 等于把全部接口（含号池管理）的地图交给爬虫。
    # 前端类型由 tools/generate-types.sh 从本地开发后端生成，不受影响
    expose_docs = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        openapi_url="/api/v1/openapi.json" if expose_docs else None,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 访问运维埋点：响应产出后最佳努力登记请求量与活跃用户，Redis 不可用时静默降级，
    # 不影响主流程。仅对成功返回的请求计数，避免 OPTIONS 预检与异常半截请求污染统计。
    @app.middleware("http")
    async def _metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # EA 调用计数按接口分组记来源；call_next 在子任务里跑，创建时继承这里设的值
        ea_metrics.set_source(f"api:{classify_path(request.url.path) or 'other'}")
        response = await call_next(request)
        # 仅对成功返回（2xx/3xx）的非 OPTIONS 请求计数，避免预检与 4xx/5xx 错误流量
        # （含未授权探测）污染访问量与活跃用户统计。
        if request.method != "OPTIONS" and response.status_code < 400:
            user_id = user_id_from_token(request.cookies.get("bfm_access_token"))
            await record_request(
                path=request.url.path, user_id=user_id, client_ip=client_ip(request)
            )
        return response

    # 最后注册即最外层：编号在 CORS 与埋点之前生成，整条请求链路的日志都带上它
    app.add_middleware(RequestIdMiddleware)

    # 统一错误响应：错误体都带 request_id，用户反馈时报这个编号即可在日志里定位
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": get_request_id(request),
                }
            },
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 已是结构化 detail 直接透传
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {**exc.detail, "request_id": get_request_id(request)}},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": str(exc.detail),
                    "details": None,
                    "request_id": get_request_id(request),
                }
            },
        )

    # 未处理异常：堆栈只进日志，响应体给固定文案，不把内部异常文本带给客户端
    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.opt(exception=exc).bind(request_id=request_id).error(
            "Unhandled error on {} {}", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请稍后重试",
                    "details": None,
                    "request_id": request_id,
                }
            },
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
