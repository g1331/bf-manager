"""一键卡行动的纯逻辑（不做 I/O，便于单测）。

私服没有行动模式选项，行动服是「抽」出来的：把轮换设成全是无效组合（地图配它没有的模式，
俗称 BUG 图），服务器被唤醒时过滤掉无效图、发现没有可用地图，就随机分配一个图池，其中一种
结果是以察里津为首的 24 图行动。抽中后把轮换「锚定」成同一批地图、模式统一写 AA0，之后
改设置才不会掉回征服，chooseLevel 的下标也和实际图池一一对应。

流程照搬 CardTool（acdc-awa/BF1AdminTool）：种 3 张相同的 BUG 图 → 循环 [Blaze 进服唤醒 →
updateServer → 2 秒 → 查 mapMode 和图数]，没中就离开、连发两次 updateServer 再来。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TARGET_MODE = "BreakthroughLarge"
# 抽中的行动图池是 24 张图
MIN_MAPS = 24
# 锚定用的模式：行动图池里每张图都没有空中突击，写 AA0 不会被当成另一个有效图池
ANCHOR_MODE = "AA0"
# 按服务器人数选 BUG 图（CardTool 的 map 表）；不在表里的按 64 人处理
SEED_BY_SLOTS: dict[int, tuple[str, str]] = {
    64: ("CQ0", "MP_Alps"),
    40: ("AA0", "MP_Naval"),
    32: ("TOW0", "MP_Naval"),
    24: ("TDM0", "MP_Naval"),
}
SEED_COUNT = 3
# 更新轮换时用的扩展包掩码，与 CardTool 一致
SEED_MOD = "32"
EVENT_LIMIT = 300

_MAP_CODE = re.compile(r"(MP_[A-Za-z0-9]+)")


@dataclass
class ServerState:
    """GameServer.getServerDetails 的摘要"""

    mode: str
    maps: list[str]  # 轮换的地图代号，下标即 levelIndex
    occupied: int  # 士兵 + 观战 + 排队
    soldier_max: int
    guid: str
    map: str = ""

    @property
    def summary(self) -> str:
        return f"{self.mode or '未知模式'}，{len(self.maps)} 张图，{self.occupied} 人"


@dataclass
class Snapshot:
    """开始前的服务器设置与轮换，恢复时原样写回"""

    settings: dict[str, Any]
    rotation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"settings": self.settings, "rotation": self.rotation}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            settings=dict(data.get("settings") or {}), rotation=dict(data.get("rotation") or {})
        )


def seed_maps(soldier_max: int) -> list[dict[str, str]]:
    mode, name = SEED_BY_SLOTS.get(soldier_max, SEED_BY_SLOTS[64])
    return [{"gameMode": mode, "mapName": name} for _ in range(SEED_COUNT)]


def map_code(map_image: str) -> str:
    """从 rotation 的 mapImage（.../MP_Tsaritsyn_LandscapeLarge-xxx.jpg）取地图代号"""
    name = map_image.rsplit("/", 1)[-1]
    m = _MAP_CODE.search(name)
    code = m.group(1) if m else ""
    # EA 图片文件名的大小写和地图代号不一致
    return "MP_ShovelTown" if code == "MP_Shoveltown" else code


def anchor_maps(maps: list[str]) -> list[dict[str, str]]:
    return [{"gameMode": ANCHOR_MODE, "mapName": m} for m in maps]


def parse_state(result: dict[str, Any]) -> ServerState:
    slots = result.get("slots") or {}

    def cur(key: str) -> int:
        return int((slots.get(key) or {}).get("current") or 0)

    return ServerState(
        mode=str(result.get("mapMode") or ""),
        maps=[map_code(str(r.get("mapImage") or "")) for r in result.get("rotation") or []],
        occupied=cur("Soldier") + cur("Spectator") + cur("Queue"),
        soldier_max=int((slots.get("Soldier") or {}).get("max") or 0),
        guid=str(result.get("guid") or ""),
        map=str(result.get("mapName") or ""),
    )


def is_hit(state: ServerState, min_maps: int = MIN_MAPS) -> bool:
    return state.mode == TARGET_MODE and len(state.maps) >= min_maps


def is_anchored(state: ServerState, rsp_maps: list[dict[str, Any]]) -> bool:
    """RSP 轮换已经是当前图池的同名同序 AA0"""
    return [m.get("mapName") for m in rsp_maps] == state.maps and all(
        m.get("gameMode") == ANCHOR_MODE for m in rsp_maps
    )


def snapshot_from_rsp(result: dict[str, Any]) -> Snapshot:
    """RSP.getServerDetails 的 result → 快照（含密码，只给服主和管理员看得到）"""
    s = result.get("serverSettings") or {}
    settings = {
        "name": s.get("name") or "",
        "description": s.get("description") or "",
        "message": s.get("message") or "",
        "password": s.get("password") or "",
        "bannerUrl": s.get("bannerUrl") or "",
        "mapRotationId": str(s.get("mapRotationId") or "100"),
        "customGameSettings": s.get("customGameSettings") or "",
    }
    rotations = result.get("mapRotations") or []
    rot = next(
        (r for r in rotations if str(r.get("mapRotationId")) == settings["mapRotationId"]),
        rotations[0] if rotations else {},
    )
    rotation = {
        "maps": [
            {"gameMode": m.get("gameMode") or "", "mapName": m.get("mapName") or ""}
            for m in rot.get("maps") or []
        ],
        "mod": str(rot.get("mod") or SEED_MOD),
        "name": str(rot.get("name") or "0"),
        "description": rot.get("description") or "",
        "rotationType": rot.get("rotationType") or "",
        "id": str(rot.get("mapRotationId") or settings["mapRotationId"]),
    }
    return Snapshot(settings=settings, rotation=rotation)


def update_params(
    server_id: int | str,
    snapshot: Snapshot,
    maps: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """RSP.updateServer 的 params：设置原样回填；maps 为空时写回快照里的原轮换"""
    rot = snapshot.rotation
    rotation_id = rot.get("id") or snapshot.settings.get("mapRotationId") or "100"
    if maps is None:
        rotation = {
            "maps": rot.get("maps") or [],
            "rotationType": rot.get("rotationType") or "",
            "mod": rot.get("mod") or SEED_MOD,
            "name": rot.get("name") or "0",
            "description": rot.get("description") or "",
            "id": rotation_id,
        }
    else:
        rotation = {
            "maps": maps,
            "rotationType": "",
            "mod": SEED_MOD,
            "name": "0",
            "description": "",
            "id": rotation_id,
        }
    s = snapshot.settings
    return {
        "game": "tunguska",
        "serverId": str(server_id),
        "deviceIdMap": {"machash": "1"},
        "bannerSettings": {"bannerUrl": "", "clearBanner": True},
        "mapRotation": rotation,
        "serverSettings": {
            "name": s.get("name") or "",
            "description": s.get("description") or "",
            "message": s.get("message") or "",
            "password": s.get("password") or "",
            "bannerUrl": "",
            "mapRotationId": rotation_id,
            "customGameSettings": s.get("customGameSettings") or "",
        },
    }


def update_error(res: Any) -> str | None:
    """updateServer 的返回值 → 错误描述；成功或只是 banner 噪音时返回 None"""
    if isinstance(res, dict):
        return None
    text = str(res)
    if "updateServerBanner" in text or "ERR_AUTHORIZATION_REQUIRED" in text:
        return None
    return text[:200] or "未知错误"


def is_permission_error(text: str) -> bool:
    return "无权限" in text or "-35160" in text


def append_events(
    events: list[dict[str, Any]], new: list[tuple[str, str]], now: float
) -> list[dict[str, Any]]:
    """新的在前，最多 EVENT_LIMIT 条"""
    fresh = [{"ts": now, "kind": k, "message": m} for k, m in reversed(new)]
    return (fresh + list(events))[:EVENT_LIMIT]
