"""BF1 交换换期判定、按日期取期与行动规整"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from app.api.errors import NotFoundError
from app.services.bf1.exchange_service import (
    get_exchange,
    list_exchange_periods,
    save_exchange_if_changed,
    to_campaign,
    to_exchange_item,
)


def _offer(key: str, price: int = 300, owned: int = 0) -> dict:
    return {
        "price": price,
        "ownedQuantity": owned,
        "item": {
            "key": key,
            "name": "奧特朗托海峽戰役",
            "parentName": "M1917 戰壕卡賓槍",
            "category": "衝鋒槍",
            "rarenessLevel": {"name": "Superior"},
            "images": {"Png300xANY": "[BB_PREFIX]/gamedata/a.png"},
        },
    }


async def test_saves_only_when_offers_change(test_session):
    t1 = datetime(2025, 6, 2, 16, tzinfo=UTC)  # 北京时间 6 月 3 日 0 点
    t2 = datetime(2025, 6, 9, 16, tzinfo=UTC)
    assert await save_exchange_if_changed(test_session, [_offer("A")], t1)
    # 同一时间重复导入、仅拥有数量不同都不算换期
    assert not await save_exchange_if_changed(test_session, [_offer("A")], t1)
    assert not await save_exchange_if_changed(test_session, [_offer("A", owned=1)], t2)
    assert await save_exchange_if_changed(test_session, [_offer("A", price=500)], t2)
    assert len(await list_exchange_periods(test_session)) == 2


async def test_get_exchange_by_cn_date(test_session):
    await save_exchange_if_changed(
        test_session, [_offer("A")], datetime(2025, 6, 2, 16, tzinfo=UTC)
    )
    await save_exchange_if_changed(
        test_session, [_offer("B")], datetime(2025, 6, 9, 16, tzinfo=UTC)
    )

    latest = await get_exchange(test_session)
    assert [i.key for i in latest.items] == ["B"]
    assert [i.key for i in (await get_exchange(test_session, date(2025, 6, 9))).items] == ["A"]
    item = (await get_exchange(test_session, date(2025, 6, 10))).items[0]
    assert (item.key, item.name, item.parent_name, item.category) == (
        "B",
        "奥特朗托海峡战役",
        "M1917 战壕卡宾枪",
        "冲锋枪",
    )
    assert item.image_url and item.image_url.startswith("https://")
    assert (
        to_exchange_item({"price": 1, "item": {"key": "k", "category": "ID_P_CAT_MELEE"}}).category
        == "近战武器"
    )
    assert (
        to_exchange_item({"price": 1, "item": {"key": "k", "category": "ID_P_CAT_X"}}).category
        is None
    )
    with pytest.raises(NotFoundError):
        await get_exchange(test_session, date(2025, 6, 2))


def test_to_campaign():
    now = datetime(2026, 10, 25, tzinfo=UTC)
    c = to_campaign(
        {
            "name": "帝國隕落",
            "shortDesc": "色當 ",
            "minutesRemaining": 60,
            "minutesToDailyReset": 30,
            "op1": {"name": "銅牆鐵壁", "imageUrl": "[BB_PREFIX]/x.png"},
            "op2": None,
        },
        now,
    )
    assert (c.name, c.description) == ("帝国陨落", "色当")
    assert c.ends_at.hour == 1 and c.daily_reset_at.minute == 30
    assert [o.name for o in c.operations] == ["铜墙铁壁"]
