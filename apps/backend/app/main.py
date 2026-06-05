"""FastAPI 应用入口"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import AppError
from app.api.v1.router import api_router
from app.core.cache import close_redis, get_redis
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import close_engine
from app.domain.ea.login.task_manager import close_task_manager, init_task_manager

# 触发游戏 profile 注册
from app.domain.games import GameRegistry  # noqa: F401
from app.services.ea_login_finalizer import EALoginFinalizer


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

    yield

    logger.info("Shutting down")
    await close_task_manager()
    await close_redis()
    await close_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
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

    # 统一错误响应
    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 已是结构化 detail 直接透传
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
