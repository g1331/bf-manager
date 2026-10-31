"""生成 BF1 Blaze 武器 / 载具目录（Blaze 统计代号 → 名称 / 分类 / 图片 / GUID）

Blaze ``Stats.getStats`` 只给统计代号（如 ``c_wHSColt__kw_g``）和英文描述，没有中文名和图片；
Gateway ``Progression.get*ByPersonaId`` 有名称、分类、图片和 GUID（皮肤按 GUID 关联）。
两边是同一份生涯数据：拿一批玩家，把每个 Blaze 代号在各玩家身上的（击杀、秒数…）向量
与 Gateway 条目逐一对上，就得到对照表。Gateway 没有的代号（维和者、防毒面具等）用
本文件 ``EXTRA_NAMES`` 手工补名。分两步：

1. 拉取（需要号池账号，生产容器内执行）。Blaze 同一账号只能有一个会话，``--persona`` 必须
   填生产当前没在用的账号（看后端日志「Blaze 登录成功，账号 X」）：

    docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend \
        python tools/export_bf1_blaze_catalog.py fetch /tmp/blaze_sample.json --persona <pid>

2. 生成（本地 apps/backend 目录下）：

    uv run python tools/export_bf1_blaze_catalog.py build /tmp/blaze_sample.json

   写 data/blaze_catalog.json，并打印没对上的代号，补进 EXTRA_NAMES 后重跑。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "domain" / "games" / "bf1" / "data"
) / "blaze_catalog.json"

WEAPON_CATEGORIES = [f"player_weapons{i}" for i in range(1, 6)]
# 载具的击杀 / 乘坐秒数 / 摧毁数分散在这三个类别里
VEHICLE_CATEGORIES = ["player_statcategory", "player_statcategory3", "player_statcategory4"]
SAMPLE_SIZE = 160

# Gateway 没有、只在 Blaze 里有的条目：英文描述 → (繁体名, 分类)。分类沿用 Gateway 的分类名。
# Blaze 标签 → 名称、分类，可选 image / image_from（借另一个 Blaze 标签的图）/ guid。
# Gateway 里同名同分类的条目（样本里没人用过、对不上数值）自动沿用它的图片与 GUID。
# 2018 年夏季更新后加的武器（维和者、伯顿）Gateway 和 EA CDN 都没有：图标是游戏文件里的原图
# （BF1ServerTools 解包，md5 前 8 位与文件名哈希一致），放在前端 public/bf1/weapons；GUID 同样取自它。
# 防毒面具、SK45 岸防炮游戏里没有武器图标。
_BB = "[BB_PREFIX]/gamedata"
EXTRA_NAMES: dict[str, dict[str, str]] = {
    "Handgun - Revolver - Colt SAA": {
        "name": "維和者", "category": "佩槍",
        "image": "/bf1/weapons/Colt_SAA-ef15294c.png",
        "guid": "B9333E7C-3D7D-4147-A569-9FC9BB2B4F5D",
    },
    "Handgun - Semi - Colt 1911 Triforce": {
        "name": "Triforce M1911", "category": "佩槍",
        "image_from": "Handgun - Semi - Colt 1911",
        "guid": "F7CED576-7629-402A-8598-4A4998C02E0A",
    },
    "MG - LMG - Burton LMG Optical": {
        "name": "伯頓 LMR（瞄準鏡）", "category": "輕機槍",
        "image": "/bf1/weapons/WinchesterBurton-ce3988cc.png",
        "guid": "708392C1-38F7-4CFA-81E3-04FC90434021",
    },
    "MG - LMG - Burton LMG Trench": {
        "name": "伯頓 LMR（壕溝）", "category": "輕機槍",
        "image": "/bf1/weapons/WinchesterBurton-ce3988cc.png",
        "guid": "6C8284DF-9CEC-4391-9E1B-0E355C2D1310",
    },
    "MG - SMG - Thompson Annihilator Storm": {
        "name": "Annihilator（衝鋒）", "category": "衝鋒槍",
        "image_from": "MG - SMG - Thompson Annihilator Trench",
    },
    # Gateway 只列玩家拥有的武器，样本 160 人没人有金碎棒；名称、图片、GUID 取自一名拥有者的 Gateway 数据
    "Melee - Ararebo": {
        "name": "金碎棒", "category": "近戰武器",
        "image": f"{_BB}/Tunguska/79/111/ArareboClub-4f916d72.png",
        "guid": "5BCDA8AE-E088-4106-B4D6-1AEC26B7F140",
    },
    "Melee - Arditi Dagger": {"name": "敢死隊匕首", "category": "近戰武器"},
    "Melee - Lance Cavalry Charge": {
        "name": "騎兵長槍（衝鋒）", "category": "近戰武器", "image_from": "Melee - Lance Cavalry",
    },
    # 精英兵「渗透者」专用的信号枪（呼叫炮击），和它的马提尼·亨利榴弹发射器同归「戰場裝備」
    "Special - Flare Gun Signal": {
        "name": "信號槍（信號）", "category": "戰場裝備",
        "image_from": "Special - Flash Flare",
        "guid": "9D1BEE08-C101-4FF3-8ECA-244240171801",
    },
    "Special - Gas Mask": {"name": "防毒面具", "category": "配備"},
    "Explosives - Mortar (Only for Custom Games)": {
        "name": "迫擊砲（自訂遊戲）", "category": "配備", "image_from": "Equipment - Mortars - HE",
    },
    "Rifle - Single - Martini Henry Standard Issue": {
        "name": "馬提尼·亨利步槍", "category": "制式步槍",
        "image_from": "Rifle - Single - Martini Henry",
    },
    "Stationary Weapons - SK45 Coastal Cannon": {"name": "SK45 岸防砲", "category": "定點武器"},
}  # fmt: skip
# Gateway 自己分错类的条目：Gateway GUID → 正确分类。2018 年 Weapons Crate 更新加的三把「巡逻」型
# 被 Gateway 挂到了别的兵种：三八式（巡逻）在「佩槍」、卡尔卡诺 M91 卡宾枪（巡逻）在「半自動步槍」，
# 两把都是侦察兵的栓动步枪；M1917 卡宾枪（巡逻）是突击兵 M1917 战壕卡宾枪的瞄准镜型，Gateway 放进了
# 「半自動步槍」。勒贝尔 M1886 是各兵种通用的制式步枪，Gateway 却放在「步槍」。
# 按 GUID 而不是 Blaze 标签：样本里没人用过的武器走「无统计条目」路径，没有标签。
# tests/test_bf1_blaze_catalog.py 按 Blaze 英文标签核对全部武器的分类，重新生成后跑一遍。
CATEGORY_FIXES: dict[str, str] = {
    "BB20B711-EF98-4708-998A-D78780B8B8C4": "步槍",  # 三八式步槍（巡邏）
    "4E317627-F7F8-4014-BB22-B0ABEB7E9141": "步槍",  # 卡爾卡諾 M91 卡賓槍（巡邏）
    "245A23B1-53BA-4AB2-A416-224794F15FCB": "衝鋒槍",  # M1917 卡賓槍（巡邏）
    "E1B701B5-0E4B-40C3-A61B-CE639A4B18A0": "制式步槍",  # 勒貝爾 M1886
}
# 不是玩家能挑的武器：遥控类与突破模式的炮击支援
IGNORED_LABELS = {"Remote", "Artillery - Rush Artillery"}


def _label(desc: str) -> str:
    """'Global All Time Kill With X, ParamX (Handgun - Semi - Colt 1911) ' → 'Handgun - Semi - Colt 1911'"""
    m = re.search(r"Param[XY] \((.*)\)\s*$", desc or "")
    return m.group(1).strip() if m else (desc or "").strip()


def _slim(kind: str, result: Any) -> Any:
    """只留 build 用得到的字段：160 人的原始武器 JSON 会撑爆生产容器的内存上限"""
    if not result:
        return result
    if kind == "detailed":
        return {k: v for k, v in result.items() if not isinstance(v, (dict, list))} | {
            k: result.get(k) for k in ("basicStats", "kitStats", "vehicleStats")
        }
    return [
        {
            "name": cat.get("name"),
            "sortOrder": cat.get("sortOrder"),
            kind: [
                {k: it.get(k) for k in ("guid", "name", "imageUrl")}
                | {"stats": {"values": (it.get("stats") or {}).get("values") or {}}}
                for it in cat.get(kind) or []
            ],
        }
        for cat in result
    ]


async def fetch(out: Path, persona: int, sample: int) -> None:
    from app.core.security import get_cipher
    from app.db.session import get_sessionmaker
    from app.domain.ea.account_pool import EACredentials
    from app.domain.games.bf1.gateway import BF1GatewayClient
    from app.models.ea_account import EAAccount
    from app.services.bf1.blaze_service import _BlazeConnectionPool
    from app.services.bf1.server_snapshot_cache import read_server_snapshot
    from sqlalchemy import select

    async with get_sessionmaker()() as db:
        acc = await db.scalar(select(EAAccount).where(EAAccount.persona_id == persona))
        if acc is None:
            raise SystemExit(f"号池里没有账号 {persona}")
        c = get_cipher()
        creds = EACredentials(
            persona_id=acc.persona_id,
            display_name=acc.display_name,
            remid=c.decrypt(acc.encrypted_remid),
            sid=c.decrypt(acc.encrypted_sid),
            session=c.decrypt(acc.encrypted_session) if acc.encrypted_session else None,
            access_token=None,
        )
    s = await _BlazeConnectionPool()._connect_and_login(creds)

    async def call(method: str, data: dict[str, Any]) -> dict[str, Any]:
        r = await asyncio.wait_for(s.send({"method": method, "type": "Command", "data": data}), 30)
        if r.get("type") != "Result":
            raise RuntimeError(f"{method} 失败: {r.get('data')}")
        await asyncio.sleep(0.5)
        return r["data"]

    try:
        # 从最热闹的几台私服里取在队玩家当样本，覆盖面比随手挑的几个人广
        servers = sorted(
            (x for x in (await read_server_snapshot() or []) if x.game_id and x.player_count >= 40),
            key=lambda x: -x.player_count,
        )[:4]
        games = await call(
            "GameManager.getGameDataFromId",
            {"DNAM 1": "csFullGameList", "GLST 40": [x.game_id for x in servers]},
        )
        pids: list[int] = []
        for g in games.get("GDAT") or []:
            pids += [int(p["PID"]) for p in g.get("ROST") or [] if p.get("TIDX") in (0, 1)]
        pids = pids[:sample]

        descs: dict[str, list[dict[str, Any]]] = {}
        blaze: dict[str, dict[str, list[str]]] = {}
        for cat in ["player_core", *VEHICLE_CATEGORIES, *WEAPON_CATEGORIES]:
            stats = (await call("Stats.getStatDescs", {"CAT  1": cat, "STAT 41": []}))["STAT"]
            descs[cat] = [{"name": x["NAME"], "desc": x.get("LDSC") or ""} for x in stats]
            names = [x["NAME"] for x in stats]
            values: dict[str, list[str]] = {}
            for i in range(0, len(pids), 32):
                data = await call(
                    "Stats.getStats", {"CAT  1": cat, "EID  40": pids[i : i + 32], "NAME 41": names}
                )
                for e in data["KSSV"]["No_Scope_Defined"]["STAT"]:
                    values[str(e["EID"])] = e["STAT"]
            blaze[cat] = values
    finally:
        await s.close()

    # Gateway 也用这个账号：同一账号的 Gateway 重新登录会顶掉它的 Blaze 会话，不能碰生产在用的号
    gateway: dict[str, dict[str, Any]] = {}
    client = BF1GatewayClient(
        pid=creds.persona_id, remid=creds.remid, sid=creds.sid, session=creds.session
    )
    try:
        await client.login(creds.remid, creds.sid)
        for pid in pids:
            row: dict[str, Any] = {}
            for key, fn in (
                ("detailed", client.detailedStatsByPersonaId),
                ("weapons", client.getWeaponsByPersonaId),
                ("vehicles", client.getVehiclesByPersonaId),
            ):
                res = await fn(pid)
                row[key] = _slim(key, res.get("result") if isinstance(res, dict) else None)
                await asyncio.sleep(0.3)
            gateway[str(pid)] = row
    finally:
        with contextlib.suppress(Exception):
            await client.http_session.close()  # type: ignore[union-attr]
    out.write_text(
        json.dumps(
            {"pids": pids, "descs": descs, "blaze": blaze, "gateway": gateway}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}: {len(pids)} players")


def _blaze_matrix(sample: dict[str, Any], cats: list[str]) -> dict[str, dict[str, float]]:
    """统计名 → {pid: 数值}"""
    out: dict[str, dict[str, float]] = {}
    for cat in cats:
        names = [d["name"] for d in sample["descs"][cat]]
        for pid, vals in sample["blaze"][cat].items():
            for name, v in zip(names, vals, strict=True):
                out.setdefault(name, {})[pid] = float(v)
    return out


# 合计行：同枪各型号之和（... Generic）、分类之和（... - All）与这些分组，不对应单个条目
AGGREGATES = {
    "All Weapons", "Primary Weapons", "Special", "Explosives", "Melee - Bladed", "Melee - Blunts",
    "Explosives - Grenades", "Explosives - Mines", "Explosives - Rifle Grenades",
    "Explosives - Tripwire Bombs", "Explosives - Crossbow", "Rifle - Single - Standard Issue Rifles",
    "Special - Field Kit", "Equipment - Mortars",
}  # fmt: skip


def _is_aggregate(label: str, labels: set[str]) -> bool:
    return (
        label in AGGREGATES
        or label.endswith(("Generic", "All"))
        or label.startswith("All ")
        or any(other.startswith(label + " - ") for other in labels)
    )


def _candidates(
    sample: dict[str, Any],
    desc: dict[str, str],
    cats: list[str],
    kills_re: str,
    fields: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """按击杀统计名找出候选代号，fields 是 {字段: 统计名模板}，模板里的 {} 是代号。"""
    cat_of = {d["name"]: cat for cat in cats for d in sample["descs"][cat]}
    out = {}
    for name, cat in cat_of.items():
        m = re.fullmatch(kills_re, name)
        if not m:
            continue
        code = m.group(1)
        label = _label(desc.get(name, ""))
        stats = {f: t.format(code) for f, t in fields.items() if t.format(code) in cat_of}
        out[code] = {"label": label, "cat": cat, "stats": stats}
    return out


def _vals(
    values: dict[str, dict[str, float]], stats: dict[str, str], keys: list[str], pids: list[str]
):
    """{pid: (各字段 ×100 取整)}，只含有数据的玩家"""
    out = {}
    for p in pids:
        t = tuple(round(values.get(stats.get(k, ""), {}).get(p, 0.0) * 100) for k in keys)
        if any(t):
            out[p] = t
    return out


def _gw_items(
    sample: dict[str, Any], pids: list[str], kind: str, keys: list[str]
) -> dict[str, dict[str, Any]]:
    """Gateway 条目：键为 GUID（载具没有 GUID 时用 分类/名称），附带各玩家的数值和展示顺序。

    Gateway 只给玩家「拥有」的条目：用别人的枪、捡的枪拿到的击杀，这个人的列表里就没有那把枪，
    所以 vals 只覆盖 Gateway 返回了该条目的玩家。
    """
    items: dict[str, dict[str, Any]] = {}
    for pid in pids:
        for ci, cat in enumerate(sample["gateway"][pid][kind] or []):
            for ii, it in enumerate(cat.get(kind) or []):
                key = it.get("guid") or f"{cat.get('name')}/{it['name']}"
                entry = items.setdefault(
                    key,
                    {
                        "name": it["name"],
                        "category": cat.get("name"),
                        "image": it.get("imageUrl"),
                        "order": ci * 1000 + ii,
                        "sort_order": cat.get("sortOrder"),
                        "vals": {},
                    },
                )
                v = it["stats"]["values"]
                entry["vals"][pid] = tuple(round((v.get(k) or 0) * 100) for k in keys)
    return items


def _score(bvals: dict[str, tuple[int, ...]], gvals: dict[str, tuple[int, ...]], n: int) -> int:
    """两边数值完全相同的人数；不够可信时返回 0。

    (击杀, 秒数, 射击数) 整组相同几乎不可能是巧合，但两次拉取隔了几分钟，常用武器（手榴弹等）
    会有一批人刚打完一局而对不上，所以只要求相同的人多于不同的人。
    """
    zero = (0,) * n
    agree = sum(1 for p, t in gvals.items() if any(t) and bvals.get(p) == t)
    conflicts = sum(1 for p, t in gvals.items() if bvals.get(p, zero) != t)
    if (agree >= 1 and conflicts == 0) or (agree >= 3 and agree > conflicts):
        return agree
    return 0


def _match_kind(
    cands: dict[str, dict[str, Any]],
    values: dict[str, dict[str, float]],
    gw: dict[str, dict[str, Any]],
    keys: list[str],
    pids: list[str],
) -> tuple[dict[str, str], list[str]]:
    """在 Gateway 返回了该条目的玩家上，两边数值全部相同、且至少一人有数据，才算对上。

    返回 (代号 → Gateway 键, 有数据却没对上的代号)。单型号分组（如「重型坦克」只有 A7V）与型号
    本身数值相同，多个代号对上同一条目时保留最具体的那个。
    """
    index: dict[tuple[str, tuple[int, ...]], set[str]] = {}
    for key, it in gw.items():
        for p, t in it["vals"].items():
            if any(t):
                index.setdefault((p, t), set()).add(key)
    matched: dict[str, str] = {}
    unmatched: list[str] = []
    labels = {c["label"] for c in cands.values()}
    for code, c in cands.items():
        if _is_aggregate(c["label"], labels):
            continue
        bvals = _vals(values, c["stats"], keys, pids)
        if not bvals:
            continue
        hits = set().union(*(index.get((p, t), set()) for p, t in bvals.items()))
        scored = sorted(((_score(bvals, gw[k]["vals"], len(keys)), k) for k in hits), reverse=True)
        scored = [(agree, k) for agree, k in scored if agree]
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            matched[code] = scored[0][1]
        else:
            unmatched.append(code)
    by_key: dict[str, list[str]] = {}
    for code, key in matched.items():
        by_key.setdefault(key, []).append(code)
    for key, codes in by_key.items():
        if len(codes) == 1:
            continue
        labels = {c: cands[c]["label"] for c in codes}
        best = max(codes, key=lambda c: len(labels[c]))
        others = [c for c in codes if c != best]
        if all(labels[best].startswith(labels[c]) for c in others):
            for c in others:
                del matched[c]
        else:
            print(f"!! Gateway {gw[key]['name']} 被多个代号对上，全部丢弃：", list(labels.values()))
            for c in codes:
                del matched[c]
                unmatched.append(c)
    return matched, unmatched


def build(sample_path: Path) -> None:
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    pids = [str(p) for p in sample["pids"] if (sample["gateway"].get(str(p)) or {}).get("weapons")]
    desc = {d["name"]: d["desc"] for cat in sample["descs"].values() for d in cat}
    values = _blaze_matrix(sample, ["player_core", *VEHICLE_CATEGORIES, *WEAPON_CATEGORIES])

    weapon_fields = {
        "kills": "c_{}__kw_g", "seconds": "c_{}__sw_g", "shots": "c_{}__sfw_g",
        "hits": "c_{}__shw_g", "headshots": "c__{}_hsh_g",
    }  # fmt: skip
    vehicle_fields = {"kills": "c_{}__ki_g", "seconds": "c_{}__si_g", "destroyed": "c__{}_di_g"}
    weapons = _candidates(sample, desc, WEAPON_CATEGORIES, r"c_(\w+?)__kw_g", weapon_fields)
    vehicles = _candidates(sample, desc, VEHICLE_CATEGORIES, r"c_(\w+?)__ki_g", vehicle_fields)
    # 迫击炮在 Gateway 归在武器的「配備」里，Blaze 却按载具记（Equipment - Mortars - HE / AIR）
    for code in [c for c, v in vehicles.items() if v["label"].startswith("Equipment - ")]:
        weapons[code] = vehicles.pop(code)

    catalog: dict[str, dict[str, Any]] = {"weapons": {}, "vehicles": {}}
    for kind, cands, bkeys, gkeys in (
        ("weapons", weapons, ["kills", "seconds", "shots"], ["kills", "seconds", "shots"]),
        (
            "vehicles",
            vehicles,
            ["kills", "seconds", "destroyed"],
            ["kills", "seconds", "destroyed"],
        ),
    ):
        gw = _gw_items(sample, pids, kind, gkeys)
        matched, unmatched = _match_kind(cands, values, gw, bkeys, pids)
        if kind == "weapons":
            # 迫击炮那两项 Blaze 没有开火数，按 (击杀, 秒数) 再对一次
            gw2 = _gw_items(sample, pids, kind, ["kills", "seconds"])
            rest = {c: cands[c] for c in unmatched if "shots" not in cands[c]["stats"]}
            m2, _ = _match_kind(rest, values, gw2, ["kills", "seconds"], pids)
            matched.update(m2)
            unmatched = [c for c in unmatched if c not in m2]
        out = catalog[kind]
        for code, key in matched.items():
            it, c = gw[key], cands[code]
            entry = {
                "name": it["name"], "category": it["category"], "image": it["image"],
                "order": it["order"], "label": c["label"], "cat": c["cat"], "stats": c["stats"],
            }  # fmt: skip
            if "/" not in key:
                entry["guid"] = key
            if kind == "vehicles" and it["sort_order"] is not None:
                entry["sort_order"] = it["sort_order"]
            out[code] = entry
        missing = []
        by_name = {(it["name"], it["category"]): k for k, it in gw.items()}
        for code, c in cands.items():
            if code in matched or c["label"] in IGNORED_LABELS:
                continue
            if c["label"] not in EXTRA_NAMES:
                if code in unmatched:
                    missing.append(c["label"])
                continue
            extra = EXTRA_NAMES[c["label"]]
            key = by_name.get((extra["name"], extra["category"]))
            it = gw[key] if key else {"image": None, "order": 99000 + len(out)}
            out[code] = {
                "name": extra["name"], "category": extra["category"],
                "image": extra.get("image") or it["image"], "order": it["order"],
                "label": c["label"], "cat": c["cat"], "stats": c["stats"],
            }  # fmt: skip
            guid = extra.get("guid") or (key if key and "/" not in key else None)
            if guid:
                out[code]["guid"] = guid
        by_label = {e["label"]: e for e in out.values()}
        for e in out.values():
            src = EXTRA_NAMES.get(e["label"], {}).get("image_from")
            if src and not e["image"]:
                e["image"] = by_label[src]["image"]
        used = set(matched.values())
        guids = {e.get("guid") for e in out.values()}
        listed = {(e["name"], e["category"]) for e in out.values()}
        # 绷带包、弹药包、潜望镜等配备 Blaze 没有单项统计，Gateway 也一直全是 0：照样列出，不带统计
        for k, it in gw.items():
            if k in used or k in guids or (it["name"], it["category"]) in listed:
                continue
            # 同一配备在两个兵种下各有一个 GUID（如绷带包），没有统计可分，只列一条
            listed.add((it["name"], it["category"]))
            if not any(any(t) for t in it["vals"].values()):
                out[k] = {
                    "name": it["name"], "category": it["category"], "image": it["image"],
                    "order": it["order"], "label": None, "cat": None, "stats": {},
                }  # fmt: skip
                if "/" not in k:
                    out[k]["guid"] = k
                print(f"[{kind}] 无统计条目：", it["name"], it["category"])
        # 三条路径（对上的、补名的、无统计的）都生成完再校正，哪条路径来的都不漏
        for e in out.values():
            if e.get("guid") in CATEGORY_FIXES:
                e["category"] = CATEGORY_FIXES[e["guid"]]
        lost = [
            (it["name"], it["category"])
            for k, it in gw.items()
            if k not in used and any(any(t) for t in it["vals"].values())
        ]
        print(
            f"[{kind}] 对上 {len(matched)}，补名 {len(out) - len(matched)}；有数据没对上、也没补名 {len(missing)}："
        )
        for label in missing:
            print("    ", label)
        print(f"[{kind}] Gateway 有数据但 Blaze 没对上 {len(lost)}：", lost)

    DATA_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {DATA_PATH}: {len(catalog['weapons'])} weapons, {len(catalog['vehicles'])} vehicles"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("out", type=Path)
    f.add_argument("--persona", type=int, required=True)
    f.add_argument("--sample", type=int, default=SAMPLE_SIZE)
    b = sub.add_parser("build")
    b.add_argument("sample", type=Path)
    args = parser.parse_args()
    if args.cmd == "fetch":
        asyncio.run(fetch(args.out, args.persona, args.sample))
    else:
        build(args.sample)


if __name__ == "__main__":
    main()
