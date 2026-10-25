"""行动服自动换图判断逻辑"""

from __future__ import annotations

from app.services.bf1.auto_switch_engine import (
    SWITCH_CONFIRM_SECONDS,
    Observation,
    decide,
    initial_state,
)

# 私服常见的打散轮换：下标即 levelIndex
ROTATION = [
    "MP_Forest",  # 0
    "MP_Offensive",  # 1
    "MP_Ridge",  # 2
    "MP_Verdun",  # 3
    "MP_Underworld",  # 4
    "MP_ShovelTown",  # 5
    "MP_Chateau",  # 6
    "MP_Scar",  # 7
]


def plan(*items: tuple[str, str, int], loops: int = 0) -> dict:
    return {"items": [{"map": m, "scope": s, "repeat": r} for m, s, r in items], "loops": loops}


def run(p: dict, steps: list[tuple[float, Observation]], **kw) -> tuple[dict, list]:
    """依次喂观测，返回最终状态和每一步的 Decision"""
    st = initial_state()
    out = []
    for now, obs in steps:
        d = decide(p, ROTATION, st, obs, now, **kw)
        st = d.state
        out.append(d)
    return st, out


def ob(m: str, full: bool = False, state: str = "running") -> Observation:
    return Observation(map=m, full=full, state=state)


def test_baseline_starts_from_current_item_without_switching():
    p = plan(("MP_Offensive", "map", 1), ("MP_Verdun", "operation", 1))
    st, (d,) = run(p, [(0, ob("MP_Underworld"))])
    assert st["cursor"] == 1  # 法乌克斯要塞属于第 2 项的凡尔登战役
    assert d.choose is None


def test_single_map_item_switches_at_attack_done_then_confirms():
    p = plan(("MP_Offensive", "map", 1), ("MP_ShovelTown", "map", 1))
    st, ds = run(
        p,
        [
            (0, ob("MP_Offensive")),
            (10, ob("MP_Offensive", full=True)),
            (25, ob("MP_ShovelTown", state="waiting")),
        ],
    )
    assert ds[1].choose.level_index == 5
    assert st["cursor"] == 1 and st["pending"] is None
    assert ds[2].events[0][0] == "ok"


def test_single_map_of_operation_is_intercepted_after_breakthrough():
    # 只打凡尔登：攻破后游戏会进法乌克斯要塞，编排器要换到下一项
    p = plan(("MP_Verdun", "map", 1), ("MP_Chateau", "operation", 1))
    _, ds = run(p, [(0, ob("MP_Verdun")), (10, ob("MP_Verdun", full=True))])
    assert ds[1].choose.map == "MP_Chateau"


def test_operation_item_lets_game_progress_and_switches_after_last_map():
    p = plan(("MP_Verdun", "operation", 1), ("MP_Offensive", "map", 1))
    st, ds = run(
        p,
        [
            (0, ob("MP_Verdun")),
            (10, ob("MP_Verdun", full=True)),
            (60, ob("MP_Underworld", state="waiting")),
            (900, ob("MP_Underworld", full=True)),
        ],
    )
    assert ds[1].choose is None and ds[2].choose is None
    assert ds[3].choose.map == "MP_Offensive"
    assert st["cursor"] == 1


def test_repeat_restarts_same_map_before_moving_on():
    p = plan(("MP_Offensive", "map", 2), ("MP_ShovelTown", "map", 1))
    st, ds = run(
        p,
        [
            (0, ob("MP_Offensive")),
            (10, ob("MP_Offensive", full=True)),
            (30, ob("MP_Offensive", state="waiting")),
            (40, ob("MP_Offensive", state="new")),
            (900, ob("MP_Offensive", full=True)),
        ],
    )
    assert ds[1].choose.map == "MP_Offensive"  # 第 1/2 次打完，重开
    assert ds[4].choose.map == "MP_ShovelTown"
    assert st["cursor"] == 1


def test_defender_win_natural_landing_advances_plan():
    # 凡尔登（下标 3）守方守住，游戏自然落到 3 + 2 = 5 攻占托尔；编排下一项是索姆河
    p = plan(("MP_Verdun", "operation", 1), ("MP_Offensive", "map", 1))
    st, ds = run(p, [(0, ob("MP_Verdun")), (900, ob("MP_ShovelTown", state="waiting"))])
    assert ds[1].choose.map == "MP_Offensive"
    assert st["cursor"] == 1


def test_manual_switch_into_plan_is_followed():
    # 落到下标 7 的圣康坦，不符合自然落点 → 人工切图；它是第 3 项，编排跟过去
    p = plan(("MP_Verdun", "operation", 1), ("MP_Offensive", "map", 1), ("MP_Scar", "operation", 1))
    st, ds = run(p, [(0, ob("MP_Verdun")), (300, ob("MP_Scar", state="waiting"))])
    assert ds[1].choose is None
    assert st["cursor"] == 2


def test_platform_manual_switch_off_plan_is_left_alone():
    p = plan(("MP_Verdun", "operation", 1), ("MP_Offensive", "map", 1))
    st, ds = run(
        p, [(0, ob("MP_Verdun")), (300, ob("MP_ShovelTown", state="waiting"))], manual_recent=True
    )
    assert ds[1].choose is None
    assert st["cursor"] == 0


def test_switch_not_taking_effect_retries_once_then_stops():
    p = plan(("MP_Offensive", "map", 1), ("MP_ShovelTown", "map", 1))
    t = SWITCH_CONFIRM_SECONDS + 1
    _, ds = run(
        p,
        [
            (0, ob("MP_Offensive")),
            (10, ob("MP_Offensive", full=True)),
            (10 + t, ob("MP_Chateau", state="waiting")),
            (10 + 2 * t, ob("MP_Chateau", state="new")),
        ],
    )
    assert ds[2].choose.map == "MP_ShovelTown"
    assert ds[3].stop == "error"


def test_switched_away_right_after_our_switch_is_a_conflict():
    p = plan(("MP_Offensive", "map", 1), ("MP_ShovelTown", "map", 1))
    _, ds = run(
        p,
        [
            (0, ob("MP_Offensive")),
            (10, ob("MP_Offensive", full=True)),
            (25, ob("MP_ShovelTown", state="waiting")),
            (45, ob("MP_Ridge", state="waiting")),
        ],
    )
    assert ds[3].stop == "conflict"


def test_loops_finish_stops():
    p = plan(("MP_Offensive", "map", 1), loops=1)
    _, ds = run(p, [(0, ob("MP_Offensive")), (10, ob("MP_Offensive", full=True))])
    assert ds[1].stop == "finished" and ds[1].choose is None
