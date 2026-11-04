"""库里按字符串存、取值固定的字段

模型（``Mapped[...]``）和 schema 共用这些类型，查询结果直接填进响应模型时不用再 cast。
列的类型由 ``mapped_column(String(...))`` 显式给出，这里的 Literal 只影响类型检查，
不会让 SQLAlchemy 把列建成 Enum。
"""

from __future__ import annotations

from typing import Literal

UserRole = Literal["user", "admin"]
UserStatus = Literal["legacy", "pending_binding", "active"]
# 服务器服管权限：管理员能做全部服管操作，服主另可增删游戏内管理员、管这台服挂的群
MembershipRole = Literal["admin", "owner"]
GroupRole = Literal["owner", "admin"]
# 链接上的角色要低于发链接的群主，所以只能是 admin；保留字段，以后加角色时接口不用改
InviteRole = Literal["admin"]
GroupAccountStatus = Literal["ok", "invalid"]
GroupServerVia = Literal["owner", "admin"]
GroupServerStatus = Literal["active", "revoked"]
VerificationKind = Literal["register", "claim", "reset", "set_email"]
RegisterMode = Literal["ea", "plain"]
CardJobKind = Literal["card", "anchor"]
CardJobStatus = Literal["running", "succeeded", "failed", "cancelled", "interrupted"]
VipStatus = Literal["active", "pending"]
RosterSlot = Literal["team1", "team2", "queue", "spectator"]
InviteCodeStatus = Literal["unused", "used", "expired", "revoked"]
