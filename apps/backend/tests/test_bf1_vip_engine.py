"""计时 VIP 规则（vip_engine 纯函数）

普通服随加随生效；行动服单条操作只改记录，checkvip 时先删过期、再按排队顺序补空位，
补上那一刻才开始计时（空服上下 V 会掉回普通服，见模块说明）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.services.bf1 import vip_engine as engine
from app.services.bf1.vip_engine import ACTIVE, DAY, PENDING, Entry, VipRuleError

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def active(days: float, queued: datetime = NOW) -> Entry:
    return Entry(ACTIVE, expires_at=NOW + timedelta(days=days), queued_at=queued)


def pending(days: float | None, queued: datetime = NOW) -> Entry:
    remaining = None if days is None else timedelta(days=days)
    return Entry(PENDING, remaining=remaining, queued_at=queued)


# ----------------------------------------------------------------------------- 普通服


def test_new_timed_vip_on_normal_server_adds_and_starts_clock() -> None:
    change = engine.grant(None, on_list=False, days=3, now=NOW, operation=False)
    assert change.add
    assert change.entry == Entry(ACTIVE, expires_at=NOW + 3 * DAY, queued_at=NOW)


def test_renew_extends_from_current_expiry() -> None:
    change = engine.grant(active(2), on_list=True, days=3, now=NOW, operation=False)
    assert not change.add
    assert change.entry is not None and change.entry.expires_at == NOW + 5 * DAY


def test_renew_after_expiry_starts_from_now() -> None:
    change = engine.grant(active(-4), on_list=True, days=3, now=NOW, operation=False)
    assert change.entry is not None and change.entry.expires_at == NOW + 3 * DAY


def test_negative_days_shorten_but_not_into_the_past() -> None:
    change = engine.grant(active(5), on_list=True, days=-2, now=NOW, operation=False)
    assert change.entry is not None and change.entry.expires_at == NOW + 3 * DAY
    with pytest.raises(VipRuleError) as e:
        engine.grant(active(1), on_list=True, days=-2, now=NOW, operation=False)
    assert e.value.code == "VIP_EXPIRES_IN_PAST"


def test_new_vip_needs_positive_days() -> None:
    with pytest.raises(VipRuleError):
        engine.grant(None, on_list=False, days=-1, now=NOW, operation=False)
    with pytest.raises(VipRuleError):
        engine.grant(None, on_list=False, days=0, now=NOW, operation=False)


def test_permanent_vip_needs_confirmation_to_become_timed() -> None:
    with pytest.raises(VipRuleError) as e:
        engine.grant(None, on_list=True, days=7, now=NOW, operation=False)
    assert e.value.code == "VIP_IS_PERMANENT"

    change = engine.grant(
        None, on_list=True, days=7, now=NOW, operation=False, allow_permanent_to_timed=True
    )
    assert not change.add
    assert change.entry is not None and change.entry.expires_at == NOW + 7 * DAY


def test_permanent_grant_drops_record() -> None:
    assert engine.grant(active(2), on_list=True, days=None, now=NOW, operation=False) == (
        engine.Change(None)
    )
    assert engine.grant(None, on_list=False, days=None, now=NOW, operation=False) == (
        engine.Change(None, add=True)
    )


def test_revoke_on_normal_server_removes_immediately() -> None:
    assert engine.revoke(active(2), on_list=True, now=NOW, operation=False) == engine.Change(
        None, remove=True
    )
    with pytest.raises(VipRuleError):
        engine.revoke(None, on_list=False, now=NOW, operation=False)


# ----------------------------------------------------------------------------- 行动服


def test_operation_grant_only_queues_with_frozen_clock() -> None:
    change = engine.grant(None, on_list=False, days=7, now=NOW, operation=True)
    assert not change.add
    assert change.entry == pending(7)


def test_operation_queued_vip_can_be_adjusted_anytime() -> None:
    later = NOW + 2 * DAY
    entry = pending(7)
    change = engine.grant(entry, on_list=False, days=3, now=later, operation=True)
    # 排队期间不扣天数，排队顺序不变
    assert change.entry == pending(10)
    change = engine.grant(entry, on_list=False, days=-2, now=later, operation=True)
    assert change.entry == pending(5)


def test_operation_active_vip_renew_only_touches_record() -> None:
    change = engine.grant(active(1), on_list=True, days=2, now=NOW, operation=True)
    assert not change.add
    assert change.entry is not None and change.entry.expires_at == NOW + 3 * DAY


def test_operation_queue_limit() -> None:
    with pytest.raises(VipRuleError) as e:
        engine.grant(None, on_list=False, days=1, now=NOW, operation=True, queue_size=100)
    assert e.value.code == "VIP_QUEUE_FULL"
    # 已在队里的改期不受上限影响
    engine.grant(pending(1), on_list=False, days=1, now=NOW, operation=True, queue_size=100)


def test_operation_permanent_grant_queues_when_not_on_list() -> None:
    change = engine.grant(None, on_list=False, days=None, now=NOW, operation=True)
    assert change.entry == pending(None)


def test_operation_revoke() -> None:
    # 排队中的直接撤掉
    assert engine.revoke(pending(3), on_list=False, now=NOW, operation=True) == engine.Change(None)
    # 已生效的（含平台没托管的永久 VIP）只标记到期，不碰 EA
    change = engine.revoke(None, on_list=True, now=NOW, operation=True)
    assert not change.remove
    assert change.entry == Entry(ACTIVE, expires_at=NOW, queued_at=NOW)


# ----------------------------------------------------------------------------- 对账与 checkvip


def test_reconcile_follows_ea_list() -> None:
    entries = {1: active(3), 2: pending(5), 3: pending(None), 4: active(3)}
    changes = engine.reconcile(entries, on_list={2, 3, 4}, now=NOW)
    # 1 被别人下了 V；2、3 被别人加上了，按生效处理；4 没变
    assert changes[1] == engine.Change(None)
    assert changes[2].entry == Entry(ACTIVE, expires_at=NOW + 5 * DAY, queued_at=NOW)
    assert changes[3] == engine.Change(None)
    assert 4 not in changes


def test_plan_apply_removes_expired_then_fills_free_slots_in_queue_order() -> None:
    t = [NOW - timedelta(hours=h) for h in range(5)]
    entries = {
        10: active(-1),
        11: active(0),  # 正好到期
        12: active(2),
        20: pending(3, queued=t[1]),
        21: pending(3, queued=t[3]),  # 排得最早
        22: pending(None, queued=t[2]),
    }
    # 名单 50 人已满，包括 47 个平台不托管的永久 VIP
    on_list = {10, 11, 12} | set(range(1000, 1047))
    plan = engine.plan_apply(entries, on_list, NOW)
    assert plan.remove == [10, 11]
    assert plan.add == [21, 22]
    assert plan.waiting == 1


def test_plan_apply_with_spare_slots_and_activate() -> None:
    entries = {20: pending(3), 21: pending(None)}
    plan = engine.plan_apply(entries, set(range(1000, 1010)), NOW)
    assert plan.add == [20, 21] and plan.waiting == 0
    assert engine.activate(entries[20], NOW) == Entry(
        ACTIVE, expires_at=NOW + 3 * DAY, queued_at=NOW
    )
    assert engine.activate(entries[21], NOW) is None
