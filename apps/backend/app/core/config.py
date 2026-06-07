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

    # ===== Blaze 协议（服务器实时玩家列表）=====
    # Blaze 是与 EA 后端通信的二进制长连接协议，用于拉取 Gateway 拿不到的实时房间名单
    # （队伍/延迟/等级/语言）。开启 mock 后玩家列表接口直接返回内置 fixture，不建立真实
    # 连接，便于本地无凭据时在浏览器预览前端效果；生产默认关闭。
    blaze_mock_mode: bool = False

    # ===== 外部封禁查询 =====
    # BFEAC 案件查询按 EA 昵称发起，需要 API key；BFBAN（gametools）按 persona id
    # 查询，无需 key。未配置 bfeac_api_key 时，BFEAC 一律降级为 unknown，不影响
    # BFBAN 查询与主战绩展示。
    bfeac_api_key: str = ""

    # ===== EA 邮箱密码登录链路 =====
    # 任务整体生命周期上限：从创建到终态的最长时间，超过则自动作废，避免内存中残留 aiohttp
    # session 与未消费 asyncio.Queue。默认 600 秒（10 分钟），覆盖一次正常的人工 2FA。
    ea_login_task_ttl_seconds: int = 600
    # 等待用户输入（选择 2FA 方式或填写验证码）的单步超时。EA 的 2FA 验证码自带 5 分钟
    # 有效期，沿用该值；超时即视为任务失败，需用户重新发起。
    ea_login_2fa_wait_seconds: int = 300
    # HTTP 长轮询的单次窗口。必须明显小于反向代理（nginx / Caddy）默认 60 秒空闲超时，
    # 到点后服务端返回当前状态而非继续 hold 连接；前端基于 since_version 自行续轮询。
    ea_login_long_poll_seconds: int = 25

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
