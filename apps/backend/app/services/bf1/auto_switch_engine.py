"""行动服自动换图的判断逻辑（纯函数，不做 I/O，便于单测）。

编排是管理员自己的一串项：「战役」项打完整个战役算一次，「单图」项打完这一局算一次；每项
可打多次，整轮可循环多次。引擎只在两个时机出手（依据见 2026-10-25 私服观测）：

1. 攻方打满本图（progress 5）：本项到此算打完时，趁结算画面直接换到编排的下一项；
2. 发生落图（地图变化，或同一张图重新进入 waiting）：上一局已结束，按实际落到的图
   重新定位，不符合编排就在开局等待期换过去。守方守住没有可靠的结束信号，靠这一条兜底。

引擎不记「上次换到了哪」：每次落图都按实际地图重新判断，人工切图到编排内的某项时跟过去，
平台上的人工切图到编排外时本局不干预。自己换图后核对结果，超时重试一次仍失败就报错停止；
换过去后很快又被别人换走则判定与其它机器人冲突并停止。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.games.bf1.maps import operation_maps, translate_map_name

# 发出换图后等待落到目标图的时间（秒），超时重试一次
SWITCH_CONFIRM_SECONDS = 90
# 换到目标后这么短时间内又被换走、且本局没打完，判定与别的机器人冲突
CONFLICT_WINDOW_SECONDS = 60
EVENT_LIMIT = 50


@dataclass
class Observation:
    map: str
    full: bool  # 攻方已拿下本图全部区域（ATTR progress == "5"）
    state: str | None  # ATTR operationstate：waiting / new / running


@dataclass
class Choose:
    level_index: int
    map: str


@dataclass
class Decision:
    state: dict[str, Any]
    choose: Choose | None = None
    events: list[tuple[str, str]] = field(default_factory=list)  # (kind, message)
    stop: str | None = None  # 非空表示应关闭自动换图：finished / error / conflict


def _n(map_name: str) -> str:
    return translate_map_name(map_name) or map_name


def item_maps(item: dict[str, Any]) -> tuple[str, ...]:
    return operation_maps(item["map"]) if item["scope"] == "operation" else (item["map"],)


def initial_state() -> dict[str, Any]:
    return {"cursor": 0, "done": 0, "loop": 1, "last": None, "pending": None, "switched": None}


def _locate(plan: dict[str, Any], map_name: str, prefer: int) -> int | None:
    """map_name 在编排里属于哪一项：优先 prefer 起往后找该图是项的开头，其次被战役项包含"""
    items = plan["items"]
    order = [(prefer + i) % len(items) for i in range(len(items))]
    for k in order:
        if items[k]["map"] == map_name:
            return k
    for k in order:
        if map_name in item_maps(items[k]):
            return k
    return None


def _advance(plan: dict[str, Any], st: dict[str, Any]) -> bool:
    """当前项打完一次，移到下一项；返回 False 表示整个编排已跑完"""
    item = plan["items"][st["cursor"]]
    st["done"] += 1
    if st["done"] < item["repeat"]:
        return True
    st["done"] = 0
    st["cursor"] += 1
    if st["cursor"] >= len(plan["items"]):
        st["cursor"] = 0
        st["loop"] += 1
        if plan["loops"] and st["loop"] > plan["loops"]:
            st["loop"] = plan["loops"]
            st["cursor"] = len(plan["items"]) - 1
            return False
    return True


def _target(plan: dict[str, Any], st: dict[str, Any]) -> str:
    return plan["items"][st["cursor"]]["map"]


def decide(
    plan: dict[str, Any],
    rotation: list[str],
    state: dict[str, Any],
    obs: Observation,
    now: float,
    *,
    manual_recent: bool = False,
) -> Decision:
    """根据本次观测推进状态。rotation 是 RSP 轮换的地图代号（下标即 levelIndex）；
    manual_recent 表示最近有人通过平台手动换过图。"""
    return _Step(plan, rotation, state, obs, now, manual_recent).run()


class _Step:
    def __init__(
        self,
        plan: dict[str, Any],
        rotation: list[str],
        state: dict[str, Any],
        obs: Observation,
        now: float,
        manual_recent: bool,
    ) -> None:
        self.plan, self.rotation, self.obs, self.now = plan, rotation, obs, now
        self.manual_recent = manual_recent
        self.st = {**initial_state(), **state}
        self.d = Decision(state=self.st)
        self.prev = self.st["last"]
        self.st["last"] = {"map": obs.map, "full": obs.full, "state": obs.state}

    def event(self, kind: str, message: str) -> None:
        self.d.events.append((kind, message))

    def stop(self, kind: str, message: str) -> None:
        self.event(kind, message)
        self.d.stop = kind

    def choose(self, target: str) -> None:
        if target not in self.rotation:
            self.stop("error", f"图池里没有「{_n(target)}」，无法换图")
            return
        self.d.choose = Choose(self.rotation.index(target), target)
        self.st["pending"] = {
            "target": target,
            "at": self.now,
            "retried": self.st["pending"] is not None,
        }

    def advance_and_choose(self, reason: str) -> None:
        if not _advance(self.plan, self.st):
            self.stop("finished", f"{reason}，编排已跑完 {self.plan['loops']} 轮，停止自动换图")
            return
        target = _target(self.plan, self.st)
        if target == self.obs.map and self.obs.state == "waiting":
            self.event("ok", f"{reason}，已在编排下一项「{_n(target)}」")
            return
        self.event("switch", f"{reason} → 换到编排第 {self.st['cursor'] + 1} 项「{_n(target)}」")
        self.choose(target)

    def run(self) -> Decision:
        obs, prev = self.obs, self.prev
        if prev is None:
            # 开启后的首次观测只建立基线；当前图在编排里就从那一项开始
            k = _locate(self.plan, obs.map, 0)
            if k is not None:
                self.st["cursor"] = k
            self.event(
                "start", f"开始接管，当前「{_n(obs.map)}」，从编排第 {self.st['cursor'] + 1} 项起"
            )
            return self.d
        landed = obs.map != prev["map"] or (obs.state == "waiting" and prev["state"] != "waiting")
        if self.st["pending"]:
            self.on_pending(landed)
        elif not landed:
            if obs.full and not prev["full"]:
                self.on_attack_done()
        else:
            self.on_landed()
        return self.d

    def chain(self) -> tuple[str, ...]:
        return item_maps(self.plan["items"][self.st["cursor"]])

    def is_operation(self) -> bool:
        return self.plan["items"][self.st["cursor"]]["scope"] == "operation"

    def on_pending(self, landed: bool) -> None:
        pending, obs = self.st["pending"], self.obs
        if obs.map == pending["target"] and (landed or obs.state == "waiting"):
            self.st["pending"] = None
            self.st["switched"] = {"map": obs.map, "at": self.now}
            self.event("ok", f"已换到「{_n(obs.map)}」")
        elif self.now - pending["at"] < SWITCH_CONFIRM_SECONDS:
            pass  # 换图还没生效；期间游戏自己落的图不作判断
        elif not pending["retried"]:
            self.event(
                "retry", f"{SWITCH_CONFIRM_SECONDS} 秒内没换到「{_n(pending['target'])}」，重试一次"
            )
            self.choose(pending["target"])
        else:
            self.st["pending"] = None
            self.stop("error", f"两次都没能换到「{_n(pending['target'])}」，停止自动换图")

    def on_attack_done(self) -> None:
        chain, m = self.chain(), self.obs.map
        step = chain.index(m) if m in chain else -1
        if self.is_operation() and 0 <= step < len(chain) - 1:
            self.event("ok", f"攻破「{_n(m)}」，战役继续进入「{_n(chain[step + 1])}」")
            return
        self.advance_and_choose(f"「{_n(m)}」攻方打完")

    def on_landed(self) -> None:
        obs, prev, st = self.obs, self.prev, self.st
        switched, st["switched"] = st["switched"], None
        if (
            switched
            and prev["map"] == switched["map"]
            and not prev["full"]
            and self.now - switched["at"] < CONFLICT_WINDOW_SECONDS
            and not self.manual_recent
        ):
            self.stop(
                "conflict",
                f"刚换到「{_n(switched['map'])}」就被换成「{_n(obs.map)}」，"
                "可能有别的切图机器人，停止自动换图",
            )
            return
        chain = self.chain()
        prev_step = chain.index(prev["map"]) if prev["map"] in chain else -1
        if (
            self.is_operation()
            and 0 <= prev_step < len(chain) - 1
            and obs.map == chain[prev_step + 1]
        ):
            return  # 战役内自然推进（攻破那一刻可能没赶上观测）
        if self.manual_recent or not _natural_landing(self.rotation, prev["map"], obs.map):
            # 平台上有人换图，或落点不符合游戏自然换图规则（KAF 同款判断）：视为人工切图
            k = _locate(self.plan, obs.map, st["cursor"])
            if k is None:
                self.event("manual", f"有人换到编排外的「{_n(obs.map)}」，这一局不干预")
            else:
                st["cursor"], st["done"] = k, 0
                self.event("manual", f"有人换到「{_n(obs.map)}」，编排跟到第 {k + 1} 项")
            return
        # 游戏自己结束了这一局（守方守住，或攻方打满时没赶上观测），按编排推进
        self.advance_and_choose(f"「{_n(prev['map'])}」这一局结束")


def _natural_landing(rotation: list[str], prev_map: str, new_map: str) -> bool:
    """游戏自己换图时的落点：同图重开，或「战役起点 / 上一张图的轮换下标 + 战役长度」"""
    ops = operation_maps(prev_map)
    if new_map == prev_map or (prev_map in ops[:-1] and ops[ops.index(prev_map) + 1] == new_map):
        return True
    n = len(rotation)
    bases = {i for i, m in enumerate(rotation) if m in (ops[0], prev_map)}
    expected = {(b + len(ops)) % n for b in bases}
    return any(rotation[i] == new_map for i in expected)


def append_events(
    events: list[dict[str, Any]], new: list[tuple[str, str]], now: float
) -> list[dict[str, Any]]:
    merged = [{"ts": now, "kind": k, "message": m} for k, m in new] + events
    return merged[:EVENT_LIMIT]
