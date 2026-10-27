"""BF1 特定数据表"""

from app.models.bf1.auto_switch import Bf1AutoSwitch
from app.models.bf1.exchange import Bf1ExchangeSnapshot
from app.models.bf1.game_instance import Bf1GameInstance
from app.models.bf1.match_cache import Bf1Match, Bf1MatchIdCache
from app.models.bf1.rounds import Bf1PlayerRoundDay, Bf1Round
from app.models.bf1.server_admins import (
    Bf1ServerAdmin,
    Bf1ServerBan,
    Bf1ServerManagerVip,
    Bf1ServerOwner,
    Bf1ServerVip,
)
from app.models.bf1.server_player_count import Bf1ServerPlayerCount
from app.models.bf1.server_roster import Bf1PlayerName, Bf1ServerPlayerDay

__all__ = [
    "Bf1AutoSwitch",
    "Bf1ExchangeSnapshot",
    "Bf1GameInstance",
    "Bf1Match",
    "Bf1MatchIdCache",
    "Bf1PlayerName",
    "Bf1PlayerRoundDay",
    "Bf1Round",
    "Bf1ServerAdmin",
    "Bf1ServerBan",
    "Bf1ServerManagerVip",
    "Bf1ServerOwner",
    "Bf1ServerPlayerCount",
    "Bf1ServerPlayerDay",
    "Bf1ServerVip",
]
