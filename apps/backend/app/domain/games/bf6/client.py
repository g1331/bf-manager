"""BF6 上游调用：EA 换 token、客户端网关 viaJWT / getStats。

链路（凭据怎么存、什么时候刷新在 ``services/bf6/credential_service``）::

    GLACIER refresh token ──/connect/token──▶ GLACIER access token（约 3 天，refresh token 同时轮换）
        ──viaJWT──▶ BF6 会话 JWT（约 4 小时）──getStats──▶ 战绩

这里只做协议，不碰数据库，也不打印任何 token。
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

import grpc
import grpc.aio
import httpx

from app.domain.games.bf6.wire import (
    Player,
    PlayerStats,
    WireError,
    decode_get_stats_response,
    decode_via_jwt_response,
    encode_dimensions_filter,
    encode_get_stats_request,
    encode_via_jwt_request,
)

CLIENT_ID = "GLACIER_PC_CLIENT"
TOKEN_URL = "https://accounts.ea.com/connect/token"
GATEWAY_HOST = "bf6-mp-cgw.ops.dice.se:443"
TENANCY = "prod_default-prod_default-santiago-common"
STATS_CATEGORY = "glacier_mp"
# viaJWT 要带一个平台值；getStats 不看它
PLATFORM = 7

_VIA_JWT = "/santiago.client.authentication.ClientAuthentication/viaJWT"
_GET_STATS = "/santiago.client.stats.ClientStats/getStats"
# 不带维度过滤时重度玩家单人约 1.5 MB
_MAX_RECEIVE = 32 * 1024 * 1024


class Bf6Error(Exception):
    """BF6 上游失败。retryable 表示网络、超时这类暂时性故障。"""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class Bf6CredentialError(Bf6Error):
    """凭据被 EA 拒绝：client secret 不对、refresh token 失效或被轮换掉。重试没用，要管理员重新填。"""


class Bf6SessionExpiredError(Bf6Error):
    """会话 JWT 被网关拒绝，换一个新会话再试。"""


@dataclass(frozen=True)
class TokenGrant:
    access_token: str
    access_expires_at: int
    # EA 每次刷新都会返回新的 refresh token，旧的随即作废
    refresh_token: str
    refresh_expires_at: int | None


def jwt_claims(token: str) -> dict[str, Any]:
    """读 JWT 载荷，不验签（只用来看过期时间和签发对象）。不是 JWT 时返回空字典。"""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def jwt_exp(token: str) -> int | None:
    exp = jwt_claims(token).get("exp")
    return int(exp) if isinstance(exp, int | float) else None


def _parse_grant(response: httpx.Response, refresh_token: str, now: int) -> TokenGrant:
    try:
        payload = response.json()
    except ValueError as e:
        raise Bf6Error("EA 换 token 的响应不是 JSON") from e
    if not isinstance(payload, dict):
        raise Bf6Error("EA 换 token 的响应结构不对")
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise Bf6Error("EA 换 token 的响应里没有 access_token")
    new_refresh = payload.get("refresh_token") or refresh_token
    if not isinstance(new_refresh, str):
        raise Bf6Error("EA 换 token 的响应里 refresh_token 不是字符串")
    try:
        expires_in = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError) as e:
        raise Bf6Error("EA 换 token 的响应里 expires_in 不是数字") from e
    return TokenGrant(
        access_token=access,
        access_expires_at=jwt_exp(access) or now + expires_in,
        refresh_token=new_refresh,
        refresh_expires_at=jwt_exp(new_refresh),
    )


async def refresh_access_token(
    client_secret: str, refresh_token: str, *, now: int, http: httpx.AsyncClient | None = None
) -> TokenGrant:
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "token_format": "JWS",
    }
    try:
        if http is None:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(TOKEN_URL, data=data)
        else:
            response = await http.post(TOKEN_URL, data=data)
    except httpx.HTTPError as e:
        raise Bf6Error(f"EA 换 token 请求失败：{type(e).__name__}", retryable=True) from e

    if response.status_code != 200:
        error = ""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            error = str(body.get("error") or "")
        if error == "invalid_client":
            raise Bf6CredentialError(
                "EA 拒绝了 client secret（invalid_client），需要换成当前可用的值"
            )
        if error == "invalid_grant":
            raise Bf6CredentialError(
                "refresh token 已失效或已被轮换（invalid_grant），需要重新签发"
            )
        raise Bf6Error(
            f"EA 换 token 失败：HTTP {response.status_code} {error}".strip(),
            retryable=response.status_code >= 500,
        )

    return _parse_grant(response, refresh_token, now)


# ---------------------------------------------------------------------------
# gRPC
# ---------------------------------------------------------------------------

_channel: tuple[asyncio.AbstractEventLoop, grpc.aio.Channel] | None = None


def _get_channel() -> grpc.aio.Channel:
    """长连接复用：每次新建通道都要重新 TLS 握手。aio 通道绑定事件循环，换了循环就重建。"""
    global _channel  # noqa: PLW0603
    loop = asyncio.get_running_loop()
    if _channel is None or _channel[0] is not loop:
        channel = grpc.aio.secure_channel(
            GATEWAY_HOST,
            grpc.ssl_channel_credentials(),
            options=[("grpc.max_receive_message_length", _MAX_RECEIVE)],
        )
        _channel = (loop, channel)
    return _channel[1]


async def close_channel() -> None:
    global _channel  # noqa: PLW0603
    if _channel is not None:
        channel = _channel[1]
        _channel = None
        await channel.close()


async def _call(
    path: str, payload: bytes, metadata: list[tuple[str, str]], timeout: float
) -> bytes:
    method = _get_channel().unary_unary(
        path,
        request_serializer=lambda value: value,
        response_deserializer=lambda value: value,
    )
    try:
        result = await method(
            payload, metadata=[("x-dice-tenancy", TENANCY), *metadata], timeout=timeout
        )
    except grpc.aio.AioRpcError as e:
        code = e.code()
        name = code.name if code else "UNKNOWN"
        if code == grpc.StatusCode.UNAUTHENTICATED:
            raise Bf6SessionExpiredError(f"BF6 网关拒绝认证（{name}）") from e
        retryable = code in {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.INTERNAL,
        }
        raise Bf6Error(f"BF6 网关调用失败（{name}）", retryable=retryable) from e
    if not isinstance(result, bytes):
        raise Bf6Error("BF6 网关返回了非二进制响应")
    return result


async def via_jwt(access_token: str, *, now: int) -> tuple[str, int]:
    """GLACIER access token 换 BF6 会话 JWT，返回 (jwt, 过期时间戳)。"""
    try:
        raw = await _call(_VIA_JWT, encode_via_jwt_request(access_token, PLATFORM), [], 30)
    except Bf6SessionExpiredError as e:
        # 这里的 UNAUTHENTICATED 说明 access token 本身不被认，不是会话过期
        raise Bf6CredentialError("BF6 网关不认这个 access token") from e
    try:
        token, _player = decode_via_jwt_response(raw)
    except WireError as e:
        raise Bf6Error("viaJWT 响应无法解析") from e
    if not token:
        raise Bf6Error("viaJWT 返回了空会话")
    return token, jwt_exp(token) or now + 3600


# 只要 global 维度（生涯）：重度玩家从约 1.5 MB 降到约 120 KB。按模式、按赛季的行不在其中
_GLOBAL_ONLY = encode_dimensions_filter("", [("global", "global")])


async def get_stats(session_jwt: str, nucleus_ids: list[int]) -> list[PlayerStats]:
    """生涯统计（global 维度）。响应随人数线性增长，一次别超过十几个人。"""
    request = encode_get_stats_request(
        [STATS_CATEGORY],
        [Player(nucleus_id=nid, platform=PLATFORM) for nid in nucleus_ids],
        [_GLOBAL_ONLY],
    )
    raw = await _call(_GET_STATS, request, [("authorization", f"Bearer {session_jwt}")], 60)
    try:
        return decode_get_stats_response(raw)
    except WireError as e:
        raise Bf6Error("getStats 响应无法解析") from e
