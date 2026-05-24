"""应用配置：从环境变量与 .env 文件加载"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(path_env: str) -> str | None:
    """读取 Docker secret 文件（生产环境用 secrets:/run/secrets/<name>）"""
    p = os.getenv(path_env)
    if p and Path(p).exists():
        return Path(p).read_text(encoding="utf-8").strip()
    return None


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== 应用基础 =====
    app_name: str = "BF-Manager"
    app_version: str = "0.0.0"
    environment: str = Field(
        default="development", description="development / staging / production"
    )
    debug: bool = False
    log_level: str = "INFO"

    # ===== 数据库 =====
    database_url: str = "postgresql+asyncpg://bf:bf@postgres:5432/bf_manager"

    # ===== Redis =====
    redis_url: str = "redis://redis:6379/0"

    # ===== EA 凭据加密密钥 =====
    # 优先从 EA_CRED_ENCRYPTION_KEY_FILE 读 Docker secret
    # 退回到环境变量 EA_CRED_ENCRYPTION_KEY
    ea_cred_encryption_key: str = ""

    # ===== JWT =====
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 7 * 24 * 60  # 7 天

    # ===== HTTP 代理（EA API 部分网络环境需要）=====
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1,postgres,redis,backend,web"

    # ===== CORS =====
    allowed_origins: str = "http://localhost:3000"

    # ===== 启用的游戏 =====
    enabled_games: str = "bf1"

    @field_validator("ea_cred_encryption_key", mode="before")
    @classmethod
    def _load_ea_key(cls, v: str | None) -> str:
        if v:
            return v
        from_secret = _read_secret_file("EA_CRED_ENCRYPTION_KEY_FILE")
        return from_secret or ""

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def _load_jwt_secret(cls, v: str | None) -> str:
        if v:
            return v
        from_secret = _read_secret_file("JWT_SECRET_KEY_FILE")
        return from_secret or ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def games(self) -> list[str]:
        return [g.strip() for g in self.enabled_games.split(",") if g.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
