"""卡行动用的 Blaze 进服会话：操作账号（服主或管理员）单独建一条连接，不碰生产连接池。

进服只为唤醒空服、让服务器重新分配图池，每轮停留几秒。报文照搬 CardTool（纯 Blaze 直连，
不发 Gateway reserveSlot）：登录后先报 setClientState + updateNetworkInfo，进服前用
getFullGameData 取协议版本和角色，joinGame 后补发一组「真客户端」状态包，再轮询名单
（PROS）直到出现自己。

同一 EA 账号只能有一个 Blaze 会话：这里登录会把这个账号正在玩的游戏挤下线，它的
Gateway 令牌刷新也可能注销这条会话，调用方发现断线就重建。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from loguru import logger

from app.api.errors import EAApiError
from app.domain.ea.account_pool import EACredentials
from app.domain.ea.blaze_protocol.socket import BlazeServerREQ, BlazeSocket

REQUEST_TIMEOUT = 15
JOIN_CONFIRM_SECONDS = 12
JOIN_POLL_SECONDS = 0.5
DEFAULT_PROTOCOL_VERSION = "3779779"

# CardTool 进服前上报的伪网络信息与机房延迟
_NETWORK_INFO = {
    "EXIP 3": {"IP   0": 1910937373, "MACI 0": 0, "PORT 0": 3659},
    "INIP 3": {"IP   0": 167772163, "MACI 0": 0, "PORT 0": 3659},
    "MACI 0": 546825851,
}
_PING_SITES = {
    "aws-bom": 118, "aws-brz": 370, "aws-cdg": -1601963046, "aws-cmh": 255,
    "aws-dub": 240, "aws-dxb": 340, "aws-fra": -1601963046, "aws-hkg": 105,
    "aws-iad": 260, "aws-icn": -1601963046, "aws-lhr": 210, "aws-nrt": 78,
    "aws-pdx": 230, "aws-sin": -1601963046, "aws-sjc": 200, "aws-syd": 150,
    "m3d-hkg": 130, "m3d-jnb": 390,
}  # fmt: skip
_EMPTY_USER = {
    "AID  0": 0, "ALOC 0": 0, "CNTY 0": 0, "EXBB 2": "", "EXID 0": 0,
    "ID   0": 0, "NAME 1": "", "NASP 1": "", "ORIG 0": 0, "PIDI 0": 0,
}  # fmt: skip


def join_packet(
    game_id: int, persona_id: int, nucleus_id: int, group: list[int], version: str, role: str
) -> dict[str, Any]:
    return {
        "CMGD 3": {"GGTY 0": 0, "GVER 1": version, "PNET 62": {"VALU 3": _NETWORK_INFO}},
        "GID  0": game_id,
        "JMET 0": 1,
        "PLJD 3": {
            "BTPL 9": group,
            "DFRL 1": "",
            "GENT 0": 0,
            "PLDL 43": [
                {
                    "ENCR 1": "",
                    "IREP 0": 0,
                    "PLYA 511": {"latency": "-1"},
                    "RLNM 1": role,
                    "SLOT 0": 1,
                    "TID  0": 65535,
                    "TIDX 0": 65535,
                    "USID 3": {**_EMPTY_USER, "EXID 0": nucleus_id, "ID   0": persona_id},
                }
            ],
            "SLOT 0": 0,
            "TID  0": 65534,
            "TIDX 0": 65535,
        },
        "SLID 0": 255,
        "USER 3": dict(_EMPTY_USER),
    }


def _entity_id(value: Any) -> int:
    """ObjectId 解码成 (组件, 类型, id)，也兼容直接给数字"""
    if isinstance(value, (list, tuple)) and value:
        value = value[-1]
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class CardBlazeSession:
    def __init__(self, persona_id: int, remid: str, sid: str) -> None:
        self.persona_id = persona_id
        self._creds = EACredentials(persona_id=persona_id, display_name=None, remid=remid, sid=sid)
        self._socket: BlazeSocket | None = None
        self._nucleus_id = 0
        self._group: list[int] = []
        self._version = DEFAULT_PROTOCOL_VERSION
        self._role = "soldier"

    @property
    def alive(self) -> bool:
        s = self._socket
        return s is not None and s.connect

    async def _send(
        self, method: str, data: dict[str, Any], timeout: float = REQUEST_TIMEOUT
    ) -> dict:
        if self._socket is None:
            raise ConnectionError("Blaze 未连接")
        res = await self._socket.send(
            {"method": method, "type": "Command", "data": data}, timeout=timeout
        )
        return res if isinstance(res, dict) else {}

    async def open(self) -> None:
        """取 authcode → 连接 → 登录 → 上报客户端状态和网络信息"""
        from app.services.bf1.blaze_service import _fetch_blaze_authcode  # noqa: PLC0415

        await self.close()
        code = await _fetch_blaze_authcode(self._creds)
        host, port = await BlazeServerREQ.get_server_address()
        self._socket = await BlazeSocket.create(host, port)
        try:
            res = await self._send(
                "Authentication.login", {"AUTH 1": code, "EXTB 2": "", "EXTI 0": 0}
            )
        except Exception as exc:
            await self.close()
            raise EAApiError(code="BLAZE_LOGIN_FAILED", message="Blaze 登录失败") from exc
        if res.get("type") != "Result":
            await self.close()
            raise EAApiError(code="BLAZE_LOGIN_FAILED", message="Blaze 登录返回异常")
        self._socket.authenticated = True
        data = res.get("data") or {}
        sess = data.get("SESS") or {}
        self._nucleus_id = int(sess.get("UID") or 0)
        cgid = _entity_id(data.get("CGID") or sess.get("CGID"))
        self._group = [30722, 2, cgid]
        for method, body in (
            ("Util.setClientState", {"MODE 0": 1, "STAT 0": 0}),
            (
                "UserSessions.updateNetworkInfo",
                {
                    "INFO 3": {
                        "ADDR 62": {"VALU 3": _NETWORK_INFO},
                        "NLMP 510": _PING_SITES,
                        "NQOS 3": {"BWHR 0": 0, "DBPS 0": 0, "NAHR 0": 0, "NATT 0": 3, "UBPS 0": 0},
                    },
                    "OPTS 0": 4,
                },
            ),
        ):
            try:
                await self._send(method, body, timeout=8)
            except Exception as exc:
                logger.warning("卡行动 Blaze {} 失败: {!r}", method, exc)
        logger.info("卡行动 Blaze 登录成功，账号 {}", self.persona_id)

    async def _game_data(self, game_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        res = await self._send("GameManager.getFullGameData", {"GIDL 40": [game_id]})
        if res.get("type") != "Result":
            return {}, []
        lgam = (res.get("data") or {}).get("LGAM") or []
        block = lgam[0] if lgam and isinstance(lgam[0], dict) else {}
        return block.get("GAME") or {}, [p for p in block.get("PROS") or [] if isinstance(p, dict)]

    async def join(self, game_id: int) -> str | None:
        """进服并确认已在名单里；成功返回 None，失败返回原因"""
        if not self.alive:
            return "Blaze 连接已断开"
        try:
            game, _ = await self._game_data(game_id)
        except (TimeoutError, ConnectionError) as exc:
            return f"查询服务器失败：{exc}"
        if game.get("VSTR"):
            self._version = str(game["VSTR"])
        roles = list(((game.get("RNFO") or {}).get("CRIT") or {}).keys())
        if roles:
            self._role = "soldier" if "soldier" in roles else str(roles[0])
        try:
            res = await self._send(
                "GameManager.joinGame",
                join_packet(
                    game_id,
                    self.persona_id,
                    self._nucleus_id,
                    self._group,
                    self._version,
                    self._role,
                ),
            )
        except (TimeoutError, ConnectionError) as exc:
            return f"进服请求失败：{exc}"
        if res.get("type") != "Result":
            return f"进服被拒：{str(res.get('data'))[:120]}"
        await self._post_join(game_id, game)
        return await self._confirm(game_id)

    async def _confirm(self, game_id: int) -> str | None:
        """轮询名单直到出现自己"""
        deadline = time.monotonic() + JOIN_CONFIRM_SECONDS
        while time.monotonic() < deadline:
            with contextlib.suppress(TimeoutError, ConnectionError):
                _, players = await self._game_data(game_id)
                if any(int(p.get("PID") or 0) == self.persona_id for p in players):
                    return None
            if not self.alive:
                return "Blaze 连接已断开"
            await asyncio.sleep(JOIN_POLL_SECONDS)
        return "进服确认超时"

    async def _post_join(self, game_id: int, game: dict[str, Any]) -> None:
        """进服后照 CardTool 补发 mesh / 玩家属性 / 客户端状态 / 链路质量，失败不影响进服判定"""
        local = self._group[-1] if self._group else 0
        groups = [g for g in [local] if g]
        for key in ("PHST", "THST", "DHST"):
            cong = _entity_id((game.get(key) or {}).get("CONG"))
            if cong and cong not in groups:
                groups.append(cong)
        packets: list[tuple[str, dict[str, Any]]] = [
            (
                "GameManager.meshEndpointsConnected",
                {
                    "FLGS 0": 0,
                    "GID  0": game_id,
                    "QOSI 3": {"LOSS a": 0.0, "PING 0": 0},
                    "TCG  9": [30722, 2, g],
                },
            )
            for g in groups
        ]
        packets.append(
            (
                "GameManager.updateMeshConnection",
                {
                    "GID  0": game_id,
                    "TARG 43": [{"FLGS 0": 0, "PID  0": self.persona_id, "STAT 0": 0}],
                },
            )
        )
        for k, v in (
            ("latency", "40"),
            ("InGame", "true"),
            ("OriginalPartyLeader", "false"),
            ("UserState", "Loading"),
            ("UserState", "Playing"),
        ):
            packets.append(
                (
                    "GameManager.setPlayerAttributes",
                    {"ATTR 511": {k: v}, "GID  0": game_id, "PID  0": self.persona_id},
                )
            )
        packets.append(("Util.setClientState", {"MODE 0": 3, "STAT 0": 0}))
        for g in [g for g in groups if g != local] or groups:
            packets.append(
                (
                    "GameManager.reportTelemetry",
                    {
                        "GID  0": game_id,
                        "LCID 0": local,
                        "NTOP 0": 1,
                        "RPTS 43": [
                            {"LATC 0": 40, "PKTL 0": 0, "RCID 0": g, "RCVD 0": 24, "SENT 0": 24}
                        ],
                    },
                )
            )
        for method, body in packets:
            try:
                await self._send(method, body, timeout=8)
            except (TimeoutError, ConnectionError, ValueError) as exc:
                logger.debug("卡行动 Blaze {} 失败: {!r}", method, exc)
                if not self.alive:
                    return

    async def close(self) -> None:
        if self._socket is not None:
            with contextlib.suppress(Exception):
                await self._socket.close()
            self._socket = None
