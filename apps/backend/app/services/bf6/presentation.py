"""在响应时补图鉴信息，已有缓存和历史对局也使用当前名称表。"""

from collections.abc import Sequence

from app.domain.games.bf6.catalog import Section, metadata
from app.schemas.bf6.catalog import Bf6NamedItem
from app.schemas.bf6.matches import Bf6MatchList
from app.schemas.bf6.player import Bf6PlayerStats


def _enrich(section: Section, items: Sequence[Bf6NamedItem]) -> None:
    for item in items:
        item.name, item.image = metadata(section, item.id)


def player_stats(stats: Bf6PlayerStats) -> Bf6PlayerStats:
    _enrich("weapons", stats.weapons)
    _enrich("weapon_categories", stats.weapon_categories)
    _enrich("vehicles", stats.vehicles)
    _enrich("vehicle_categories", stats.vehicle_categories)
    _enrich("gadgets", stats.gadgets)
    _enrich("kits", stats.kits)
    _enrich("modes", stats.modes)
    _enrich("maps", stats.maps)
    return stats


def matches(listing: Bf6MatchList) -> Bf6MatchList:
    for match in listing.matches:
        _enrich("weapons", match.weapons)
        _enrich("vehicles", match.vehicles)
        _enrich("modes", match.modes)
        _enrich("maps", match.maps)
        match.kit_name = metadata("kits", match.kit)[0] if match.kit else None
    return listing
