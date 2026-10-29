"""SQLAlchemy 模型聚合导出"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.bf1 import (
    Bf1AutoSwitch,
    Bf1CardJob,
    Bf1ExchangeSnapshot,
    Bf1GameInstance,
    Bf1Match,
    Bf1MatchIdCache,
    Bf1PlayerName,
    Bf1PlayerRoundDay,
    Bf1Round,
    Bf1ServerAdmin,
    Bf1ServerBan,
    Bf1ServerManagerVip,
    Bf1ServerOwner,
    Bf1ServerPlayerCount,
    Bf1ServerPlayerDay,
    Bf1ServerVip,
)
from app.models.ea_account import EAAccount
from app.models.ea_binding import EaBinding
from app.models.server import Server, ServerMembership
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Bf1AutoSwitch",
    "Bf1CardJob",
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
    "EAAccount",
    "EaBinding",
    "Server",
    "ServerMembership",
    "User",
]
