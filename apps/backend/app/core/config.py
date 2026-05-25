"""应用配置：从环境变量、.env 文件、Docker secrets 加载"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 生产环境 Docker secrets 挂载点。dev/本地无此目录时传 None，让 pydantic-settings 跳过此 source。
# 字段名 → /run/secrets/<field_name>：
#   database_url, ea_cred_encryption_key, jwt_secret_key
# pydantic-settings 会自动把文件内容做 strip 后填入字段。
_SECRETS_DIR = "/run/secrets" if os.path.isdir("/run/secrets") else None


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=_SECRETS_DIR,
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
