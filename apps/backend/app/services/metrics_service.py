"""平台访问运维统计

请求计数中间件在每个请求结束后调用 :func:`record_request`，把请求量、按接口分组的
调用次数与去重活跃用户写入 Redis；管理端通过 :func:`read_metrics` 只读汇总。

口径说明：
- 请求量按天分桶（``YYYYMMDD``），并维护一个全局累计总数。
- 接口分组取路径 ``/api/v1/`` 之后的前两段非数字片段，数字 id 段不计入分组，
  从而把 ``/bf1/stats/123`` 与 ``/bf1/stats/456`` 归入同一组 ``bf1/stats``。
- 活跃用户按天用 HyperLogLog 去重统计，跨天合并即得多日去重数。
- Redis 在本项目属可选依赖，写入与读取全程吞掉 ``RedisError`` 降级，绝不影响主流程。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError
from loguru import logger

from app.core.cache import get_redis
from app.core.security import decode_access_token
from app.schemas.admin import AdminMetrics, DailyCount, EndpointCount

# 键统一挂在 bfm:metrics 命名空间下，与 Cache 的 bfm 前缀保持一致。
PREFIX = "bfm:metrics"
# 按天分桶的键保留时长：覆盖 7 天窗口仍有余量，避免无限增长。
DAY_TTL_SECONDS = 60 * 60 * 24 * 40
# 趋势窗口与热门接口展示条数
WINDOW_DAYS = 7
TOP_ENDPOINT_LIMIT = 10


def classify_path(path: str) -> str | None:
    """把请求路径归类为接口分组。非 ``/api/v1`` 业务路径或健康检查返回 None（不计数）。"""
    prefix = "/api/v1/"
    if not path.startswith(prefix):
        return None
    parts = [p for p in path[len(prefix) :].split("/") if p]
    if not parts or parts[0] in {"health", "openapi.json", "docs", "redoc"}:
        return None
    labels: list[str] = []
    for segment in parts:
        if segment.isdigit():
            break
        labels.append(segment)
        if len(labels) == 2:
            break
    if not labels:
        return None
    return "/".join(labels)


def user_id_from_token(token: str | None) -> int | None:
    """从会话 cookie 解出用户 id；缺失或无效一律返回 None（按匿名计）。"""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


def _day_key(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y%m%d")


def _recent_days(n: int) -> list[str]:
    """返回最近 n 天的日期键，今天在前。"""
    now = datetime.now(UTC)
    return [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


def _fmt_date(day_key: str) -> str:
    return f"{day_key[0:4]}-{day_key[4:6]}-{day_key[6:8]}"


async def record_request(*, path: str, user_id: int | None) -> None:
    """登记一次请求。最佳努力写入，Redis 不可用时静默降级。"""
    group = classify_path(path)
    if group is None:
        return
    today = _day_key()
    req_day_key = f"{PREFIX}:req:day:{today}"
    user_day_key = f"{PREFIX}:users:day:{today}"
    try:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.incr(f"{PREFIX}:req:total")
        pipe.incr(req_day_key)
        pipe.expire(req_day_key, DAY_TTL_SECONDS)
        pipe.hincrby(f"{PREFIX}:req:group", group, 1)
        if user_id is not None:
            pipe.pfadd(user_day_key, str(user_id))
            pipe.expire(user_day_key, DAY_TTL_SECONDS)
        await pipe.execute()
    except Exception as e:
        # 埋点处于请求响应热路径，任何失败都不得把成功的业务响应变成 500。Redis 为可选依赖，
        # get_redis() 在 redis_url 配置非法时抛 ValueError（非 RedisError），故捕获放宽到
        # Exception，统一静默降级。
        logger.debug("metrics record skipped: {}", e)


async def read_metrics() -> AdminMetrics:
    """读取并汇总访问运维快照。Redis 不可用时返回 available=False 的空快照。

    所有读取合并进单个 pipeline 一次往返：总量、当日各天请求、接口分组、各天去重活跃用户、
    以及 7 天合并去重活跃用户。各命令结果按入队顺序对应 pipeline 返回列表。
    """
    days = _recent_days(WINDOW_DAYS)
    user_keys = [f"{PREFIX}:users:day:{d}" for d in days]
    try:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.get(f"{PREFIX}:req:total")
        pipe.mget(*[f"{PREFIX}:req:day:{d}" for d in days])
        pipe.hgetall(f"{PREFIX}:req:group")
        for key in user_keys:
            pipe.pfcount(key)
        pipe.pfcount(*user_keys)
        res = await pipe.execute()
    except Exception as e:
        # 读取同样静默降级：Redis 不可用或 redis_url 配置非法时返回空快照而非 500。
        logger.warning("metrics read failed, serving empty snapshot: {}", e)
        return AdminMetrics(available=False)

    n = len(days)
    total = int(res[0] or 0)
    req_vals = res[1] or []
    group_map = res[2] or {}
    daily_active = res[3 : 3 + n]
    active_7d = int(res[3 + n] or 0)

    daily: list[DailyCount] = [
        DailyCount(date=_fmt_date(day), requests=int(raw or 0), active_users=int(active or 0))
        for day, raw, active in zip(days, req_vals, daily_active, strict=True)
    ]

    requests_today = daily[0].requests if daily else 0
    active_today = daily[0].active_users if daily else 0
    requests_7d = sum(d.requests for d in daily)

    top_endpoints = sorted(
        (EndpointCount(group=g, count=int(c)) for g, c in group_map.items()),
        key=lambda x: x.count,
        reverse=True,
    )[:TOP_ENDPOINT_LIMIT]

    # 前端按日期从左到右画趋势，故返回升序
    daily.reverse()

    return AdminMetrics(
        available=True,
        total_requests=total,
        requests_today=requests_today,
        requests_7d=requests_7d,
        active_users_today=active_today,
        active_users_7d=active_7d,
        top_endpoints=top_endpoints,
        daily=daily,
    )
