"""把前端服务器筛选条件构造为 EA searchServers 的 filter_dict。

EA filterJson 的语义经部署机实测确认：类别内未列出的 key 默认按 off 处理，因此只需
列出被选中的项设 "on"，未选中的维度整体省略即等于不约束该维度。基于此，构造结果只
包含用户实际勾选的维度，每个维度只列选中项。

空位（emptySlots）经实测不可下推：EA searchServers 不按实时空位过滤（空位是服务器的
实时人数状态而非配置属性），无论 slots 档位如何设置返回集都与无筛选一致，故不在此构造，
由前端对已加载结果二次过滤。
"""

from __future__ import annotations

from typing import Any

from app.api.errors import ValidationError
from app.domain.games.bf1.maps import MapData

# 服务器规模档位（gameSizes 数值 key 全集），与游戏「遊戲規模」筛选项一致
VALID_SIZES: frozenset[int] = frozenset({10, 16, 24, 32, 40, 48, 64})
# 地图 / 模式 / 地区代号全集，复用翻译字典的 key，避免重复维护一份清单
VALID_MAPS: frozenset[str] = frozenset(MapData.MapTeamDict)
VALID_MODES: frozenset[str] = frozenset(MapData.ModeDict)
VALID_REGIONS: frozenset[str] = frozenset(MapData.RegionDict)


def _reject_unknown(values: list[Any], allowed: frozenset[Any], field: str) -> None:
    """拼错或越界的取值直接拒绝，避免静默返回与预期不符的结果。"""
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise ValidationError(
            f"{field} 含非法取值: {unknown}",
            details={"field": field, "unknown": unknown},
        )


def build_search_filter(
    *,
    name: str | None = None,
    maps: list[str] | None = None,
    modes: list[str] | None = None,
    regions: list[str] | None = None,
    sizes: list[int] | None = None,
) -> dict[str, Any]:
    """构造 EA filter_dict。仅含被选中的维度，每个维度只列选中项设 "on"。

    未选中的维度不写入，等价于不约束。name 始终写入（空串表示不按名称过滤）。
    """
    filter_dict: dict[str, Any] = {"name": name or ""}
    if maps:
        _reject_unknown(maps, VALID_MAPS, "maps")
        filter_dict["maps"] = dict.fromkeys(maps, "on")
    if modes:
        _reject_unknown(modes, VALID_MODES, "modes")
        filter_dict["gameModes"] = dict.fromkeys(modes, "on")
    if regions:
        _reject_unknown(regions, VALID_REGIONS, "regions")
        filter_dict["regions"] = dict.fromkeys(regions, "on")
    if sizes:
        _reject_unknown(sizes, VALID_SIZES, "sizes")
        filter_dict["gameSizes"] = {str(size): "on" for size in sizes}
    return filter_dict
