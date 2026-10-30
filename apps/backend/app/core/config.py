"""应用配置：从环境变量、.env 文件、Docker secrets 加载"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 生产环境 Docker secrets 挂载点。dev/本地无此目录时传 None，让 pydantic-settings 跳过此 source。
# 字段名 → /run/secrets/<field_name>：
#   database_url, ea_cred_encryption_key, jwt_secret_key, resend_api_key, turnstile_secret_key
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
    jwt_access_token_expire_minutes: int = 30 * 24 * 60  # 30 天，/auth/session 会滑动续期

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
    # 对局跟踪：每轮快照后批量查进出服玩家的核心生涯，差分出每局战绩。会占用 Blaze 连接
    # （约每分钟几十个请求），EA 侧有异常时可关掉，关掉后已有对局仍可查询
    bf1_match_tracking: bool = True
    # 对局里同时记武器载具：核心变了的人再读 5 个武器类别（冷门载具类别看哨兵），约每分钟多 20 个
    # 请求。关掉后回到只记核心战绩，已存的武器载具数据仍可查询
    bf1_round_weapons: bool = True

    # ===== 外部封禁查询 =====
    # BFEAC 案件查询按 EA 昵称发起，需要 API key；BFBAN（gametools）按 persona id
    # 查询，无需 key。未配置 bfeac_api_key 时，BFEAC 一律降级为 unknown，不影响
    # BFBAN 查询与主战绩展示。
    bfeac_api_key: str = ""

    # ===== 公共查询限流与 EA 预算 =====
    # 按 IP（IPv6 按 /64）计数，登录用户按账号计数并乘以倍数。限流只防脚本和爬虫，
    # 数值定得让正常查询碰不到：打开一个玩家页约 9 个请求。
    rate_limit_enabled: bool = True
    rate_limit_lookup_per_minute: int = 60
    rate_limit_lookup_per_day: int = 2000
    rate_limit_avatar_per_minute: int = 20
    # 只读库或缓存的公开接口（人数曲线、对局、交换等）不占 EA 号，额度放宽，只防整站爬取。
    # 开着服务器页一整天约 4000 次
    rate_limit_read_per_minute: int = 120
    rate_limit_read_per_day: int = 20000
    rate_limit_ea_login_per_10min: int = 10
    # 一键卡行动：预检每小时、开始每小时（每次开始会占用服务器几分钟到半小时）
    rate_limit_card_check_per_hour: int = 30
    rate_limit_card_start_per_hour: int = 3
    rate_limit_user_multiplier: int = 2
    # 开放 API Key：默认额度倍数和登录用户一样，管理员可以给单个 key 调高；每人最多几个有效 key。
    # 号池小，全站 EA 预算对 key 同样生效，倍数调得再高也挤不爆号池
    rate_limit_api_key_multiplier: int = 2
    api_key_max_per_user: int = 5
    # 全站公共查询每分钟最多占用多少次 EA 账号池 / Blaze 连接；管服操作和后台任务不计入。
    # 0 表示不限
    ea_public_budget_per_minute: int = 120

    # ===== 账号与发信 =====
    # 邮件里链接指向的站点地址
    public_site_url: str = "http://localhost:3000"
    # resend：走 Resend HTTP API；log：只把信件写进日志（开发、测试用）
    mail_backend: str = "log"
    mail_from: str = "BF Manager <no-reply@umrbotech.com>"
    # 生产从 /run/secrets/resend_api_key 读取
    resend_api_key: str = ""
    # Cloudflare Turnstile 人机验证（注册、找回密码、补邮箱）。没配 secret 就不校验；
    # 生产从 /run/secrets/turnstile_secret_key 读取，site key 给前端用
    turnstile_secret_key: str = ""
    # 公开值，经 /auth/config 下发给前端；和 secret 都配上才启用人机验证
    turnstile_site_key: str = ""
    # 注册是否必须填邀请码；EA 号本身已经一号一账号，邀请码只用来控制增长速度
    registration_invite_required: bool = True
    invite_quota_per_user: int = 5
    invite_ttl_days: int = 7
    # 验证链接有效期
    verify_link_ttl_hours: int = 4
    reset_link_ttl_hours: int = 1
    # 用非 EA 邮箱注册、迟迟没绑 EA 的账号，多久后清理
    pending_binding_ttl_hours: int = 24
    # 注册、找回密码、重发验证信：同一 IP 每小时、同一邮箱每天的请求上限，
    # 同一邮箱两封信之间至少隔多少秒
    rate_limit_account_mail_per_hour: int = 10
    # 打开、提交验证链接（每用一次链接调两次）
    rate_limit_account_link_per_10min: int = 30
    account_mail_per_email_per_day: int = 5
    account_mail_cooldown_seconds: int = 60
    # 同一个邀请码每天最多触发几次注册信：邀请码要到设置密码时才算用掉，防止拿一个码反复刷信
    account_mail_per_invite_per_day: int = 3

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
