"""计时 VIP 的纯计算：授予、移除、对账、生效（checkvip）只依赖记录快照、EA 名单和当前时间。

普通服随时可以上下 V：授予立即加进 EA 名单并开始计时，到期由后台任务下掉。

行动服在没人时上下 V 会掉回普通服（v3 服管多年的经验），所以行动服的单条操作只改记录：
- 新加的 VIP 进待生效队列，剩余时长冻结，不扣天数；
- 已生效的下 V 只把到期时间改成现在；
- 管理员在有人时手动 checkvip：先下掉过期的，再按排队顺序补空位，补上的那一刻开始计时，
  没补上的继续排队。

一条记录只描述平台托管的 VIP；EA 名单里没有记录的 VIP 视为永久、由别处管理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

ACTIVE = "active"
PENDING = "pending"

DAY = timedelta(days=1)
# EA 每台服的 VIP 位
VIP_CAPACITY = 50
# 行动服待生效队列上限（与 v3 一致）
QUEUE_LIMIT = 100


@dataclass(frozen=True)
class Entry:
    status: str
    # active 必有：到期时刻
    expires_at: datetime | None = None
    # pending：冻结的剩余时长，None 表示永久
    remaining: timedelta | None = None
    queued_at: datetime | None = None


@dataclass(frozen=True)
class Change:
    """操作后的记录（None 表示删掉记录）及需要对 EA 发出的调用。"""

    entry: Entry | None
    add: bool = False
    remove: bool = False


class VipRuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_permanent(entry: Entry | None, on_list: bool) -> bool:
    """在 EA 名单里但没有托管记录，或者排队中的永久 VIP"""
    if entry is None:
        return on_list
    return entry.status == PENDING and entry.remaining is None


def _queued(entry: Entry | None, now: datetime) -> datetime:
    return entry.queued_at if entry and entry.queued_at else now


def _check_queue(entry: Entry | None, queue_size: int) -> None:
    if entry is None and queue_size >= QUEUE_LIMIT:
        raise VipRuleError("VIP_QUEUE_FULL", f"待生效队列已满（{QUEUE_LIMIT} 人）")


def _grant_permanent(
    entry: Entry | None, *, on_list: bool, now: datetime, operation: bool, queue_size: int
) -> Change:
    if on_list:
        # 已在名单里：去掉期限即永久，不碰 EA
        return Change(None)
    if operation:
        _check_queue(entry, queue_size)
        return Change(Entry(PENDING, remaining=None, queued_at=_queued(entry, now)))
    return Change(None, add=True)


def grant(
    entry: Entry | None,
    *,
    on_list: bool,
    days: int | None,
    now: datetime,
    operation: bool,
    queue_size: int = 0,
    allow_permanent_to_timed: bool = False,
) -> Change:
    """加 V / 改期。days 为空表示永久；可以为负，用来缩短期限。

    已生效未过期的在原到期时间上加减，已过期的从现在算；排队中的加减在冻结的剩余时长上。
    """
    if days is None:
        return _grant_permanent(
            entry, on_list=on_list, now=now, operation=operation, queue_size=queue_size
        )
    if days == 0:
        raise VipRuleError("VIP_INVALID_DAYS", "天数不能为 0")
    if is_permanent(entry, on_list) and not allow_permanent_to_timed:
        raise VipRuleError("VIP_IS_PERMANENT", "该玩家目前是永久 VIP，确认后才能改为限时")
    delta = days * DAY

    if on_list:
        base = now
        if entry is not None and entry.status == ACTIVE and entry.expires_at:
            base = max(entry.expires_at, now)
        expires_at = base + delta
        if expires_at <= now:
            raise VipRuleError("VIP_EXPIRES_IN_PAST", "调整后的到期时间早于现在")
        return Change(Entry(ACTIVE, expires_at=expires_at, queued_at=_queued(entry, now)))

    remaining = delta
    if entry is not None and entry.status == PENDING and entry.remaining is not None:
        remaining += entry.remaining
    if remaining <= timedelta(0):
        raise VipRuleError("VIP_EXPIRES_IN_PAST", "调整后的待生效时长不足 0")
    if operation:
        _check_queue(entry, queue_size)
        return Change(Entry(PENDING, remaining=remaining, queued_at=_queued(entry, now)))
    return Change(
        Entry(ACTIVE, expires_at=now + remaining, queued_at=_queued(entry, now)), add=True
    )


def revoke(entry: Entry | None, *, on_list: bool, now: datetime, operation: bool) -> Change:
    """下 V。行动服已生效的只标记为到期，等 checkvip 统一下掉。"""
    if not on_list:
        if entry is None:
            raise VipRuleError("VIP_NOT_FOUND", "该玩家不在 VIP 名单和待生效队列里")
        return Change(None)
    if operation:
        return Change(Entry(ACTIVE, expires_at=now, queued_at=_queued(entry, now)))
    return Change(None, remove=True)


def activate(entry: Entry, now: datetime) -> Entry | None:
    """排队中的 VIP 进了 EA 名单：从现在开始计时；永久的不再需要记录"""
    if entry.remaining is None:
        return None
    return Entry(ACTIVE, expires_at=now + entry.remaining, queued_at=entry.queued_at)


def reconcile(entries: dict[int, Entry], on_list: set[int], now: datetime) -> dict[int, Change]:
    """按 EA 名单修正记录：已生效却不在名单的被别人下了 V，删掉；排队中却已在名单的被别人
    加上了，按生效处理。只返回需要变更的项。"""
    changes: dict[int, Change] = {}
    for pid, entry in entries.items():
        if entry.status == ACTIVE and pid not in on_list:
            changes[pid] = Change(None)
        elif entry.status == PENDING and pid in on_list:
            changes[pid] = Change(activate(entry, now))
    return changes


def is_expired(entry: Entry, now: datetime) -> bool:
    return entry.status == ACTIVE and entry.expires_at is not None and entry.expires_at <= now


def queue_order(entries: dict[int, Entry]) -> list[int]:
    pending = [
        (e.queued_at.timestamp() if e.queued_at else float("inf"), pid)
        for pid, e in entries.items()
        if e.status == PENDING
    ]
    return [pid for _, pid in sorted(pending)]


@dataclass
class ApplyPlan:
    remove: list[int] = field(default_factory=list)
    add: list[int] = field(default_factory=list)
    waiting: int = 0


def plan_apply(
    entries: dict[int, Entry], on_list: set[int], now: datetime, capacity: int = VIP_CAPACITY
) -> ApplyPlan:
    """checkvip：先下掉过期的，再按排队顺序补空位。entries 须已与 EA 名单对过账。

    空位要算上名单里所有人，包括平台不托管的永久 VIP。
    """
    remove = sorted(pid for pid, e in entries.items() if is_expired(e, now) and pid in on_list)
    free = max(capacity - len(on_list) + len(remove), 0)
    queue = queue_order(entries)
    return ApplyPlan(remove=remove, add=queue[:free], waiting=max(len(queue) - free, 0))
