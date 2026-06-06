"""访问运维统计的纯函数单测

覆盖 classify_path 的接口分组归类与 user_id_from_token 的会话解析，不依赖 Redis 与网络。
"""

from __future__ import annotations

from app.core.security import create_access_token
from app.services.metrics_service import classify_path, user_id_from_token


def test_classify_path_groups_by_resource() -> None:
    # 数字 id 段不计入分组，同一资源下不同 id 归入同一组
    assert classify_path("/api/v1/bf1/stats/123") == "bf1/stats"
    assert classify_path("/api/v1/bf1/stats/456/weapons") == "bf1/stats"
    assert classify_path("/api/v1/bf1/servers") == "bf1/servers"
    assert classify_path("/api/v1/bf1/overview") == "bf1/overview"
    assert classify_path("/api/v1/auth/login") == "auth/login"
    assert classify_path("/api/v1/me") == "me"
    assert classify_path("/api/v1/ea-accounts") == "ea-accounts"
    assert classify_path("/api/v1/admin/metrics") == "admin/metrics"


def test_classify_path_excludes_non_business_paths() -> None:
    assert classify_path("/api/v1/health") is None
    assert classify_path("/api/v1/openapi.json") is None
    assert classify_path("/docs") is None
    assert classify_path("/") is None
    assert classify_path("/api/v1/") is None


def test_user_id_from_token_roundtrip() -> None:
    token = create_access_token(subject="42")
    assert user_id_from_token(token) == 42


def test_user_id_from_token_invalid_or_missing() -> None:
    assert user_id_from_token(None) is None
    assert user_id_from_token("") is None
    assert user_id_from_token("not-a-jwt") is None
