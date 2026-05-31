"""玩家外部封禁状态查询（BFBAN / BFEAC）

两个数据源都是外部公开服务，作为玩家页的补充信息。任何网络错误、超时、HTTP
非 2xx、JSON 解析失败或返回结构异常，一律降级为 unknown，既不向上抛错也不
阻断主战绩展示。BFBAN 按 persona id 查询、无需凭据；BFEAC 按 EA 昵称查询、
需要 API key（未配置或无昵称时直接返回 unknown）。

BFBAN 的返回结构以现行 gametools 接口实测为准（personaids[pid].hacker 布尔，
true 即实锤），同时兼容旧形态的 status 字符串。BFEAC 需 API key 方能取样，解析
按其公开约定（data[0].current_status==1 为已封禁，案件页由 case_id 拼接）实现，
对未知结构一律容错为 unknown，首次接入生产前应做一次带 key 的真实冒烟核对。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger

from app.core.config import get_settings
from app.schemas.bf1.ban import BanSourceState, BanStatus

# gametools 的 BFBAN 校验接口：?personaids=<pid>，无需鉴权
_BFBAN_URL = "https://api.gametools.network/bfban/checkban"
# BFEAC 案件查询：按 EA 昵称，需在 header 携带 apikey
_BFEAC_URL = "https://api.bfeac.com/case/EAID/{name}"
_TIMEOUT = 6.0


def _parse_bfban(payload: Any, persona_id: int) -> tuple[BanSourceState, str | None]:
    """从 gametools checkban 响应提取某 pid 的封禁态与案件链接。

    各 pid 结果挂在 personaids 字典下（部分形态直接平铺在顶层）。现行接口用
    hacker 布尔标记是否实锤（实测 {"personaids":{"<pid>":{"hacker":false}}}），
    旧形态用 status 字符串（"1"=实锤）；两者都兼容。命中返回 ("hit", url)，明确
    无记录返回 ("clean", None)，结构不符返回 ("unknown", None)。
    """
    if not isinstance(payload, dict):
        return "unknown", None
    bucket = payload.get("personaids")
    if not isinstance(bucket, dict):
        bucket = payload
    entry = bucket.get(str(persona_id))
    if not isinstance(entry, dict):
        return "unknown", None
    url = entry.get("url") if isinstance(entry.get("url"), str) else None
    if isinstance(entry.get("hacker"), bool):
        return ("hit", url) if entry["hacker"] else ("clean", None)
    # 回退到旧形态：status "1" 为实锤，"0" 及其它已知态视为无记录
    status = entry.get("status")
    if status is None:
        return "unknown", None
    return ("hit", url) if str(status) == "1" else ("clean", None)


def _parse_bfeac(payload: Any) -> tuple[BanSourceState, str | None]:
    """从 BFEAC case 响应提取封禁态。

    案件列表挂在 data 下，current_status == 1 为已封禁，案件页由 case_id 拼接为
    https://bfeac.com/#/case/<id>。命中返回 ("hit", url)，data 为空列表（查无案件）
    返回 ("clean", None)，结构不符或 status 不可解析返回 ("unknown", None)。
    """
    if not isinstance(payload, dict):
        return "unknown", None
    data = payload.get("data")
    if not isinstance(data, list):
        return "unknown", None
    if not data:
        return "clean", None  # data 为空列表表示查无案件
    case = data[0] if isinstance(data[0], dict) else {}
    # current_status 缺失/为 0/其它假值统一按未封禁处理；非数字字符串走 except 降级
    try:
        is_banned = int(case.get("current_status") or 0) == 1
    except (TypeError, ValueError):
        return "unknown", None
    if not is_banned:
        return "clean", None
    case_id = case.get("case_id")
    return "hit", f"https://bfeac.com/#/case/{case_id}" if case_id else None


class BF1BanService:
    """外部封禁状态查询，不依赖数据库与 EA 账号池，纯外部 HTTP。"""

    async def get_ban_status(self, persona_id: int, name: str | None = None) -> BanStatus:
        bfban_state, bfban_url = await self._check_bfban(persona_id)
        bfeac_state, bfeac_url = await self._check_bfeac(name)
        return BanStatus(
            persona_id=persona_id,
            bfban=bfban_state,
            bfeac=bfeac_state,
            bfban_url=bfban_url,
            bfeac_url=bfeac_url,
        )

    async def _check_bfban(self, persona_id: int) -> tuple[BanSourceState, str | None]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BFBAN_URL, params={"personaids": persona_id})
                resp.raise_for_status()
                return _parse_bfban(resp.json(), persona_id)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(f"BFBAN 查询失败 pid={persona_id}: {exc}")
            return "unknown", None

    async def _check_bfeac(self, name: str | None) -> tuple[BanSourceState, str | None]:
        api_key = get_settings().bfeac_api_key
        if not name or not api_key:
            return "unknown", None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _BFEAC_URL.format(name=quote(name)),
                    headers={"apikey": api_key},
                )
                resp.raise_for_status()
                return _parse_bfeac(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(f"BFEAC 查询失败 name={name}: {exc}")
            return "unknown", None
