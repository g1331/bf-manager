"""BF1 图鉴数据导出：把 EA Companion 的原始 JSON 转成前端静态数据与自托管图片。

BF1 已停止更新，这些内容不会再变。导出一次、随前端发布，运行时不再请求 EA；
以后 EA 的 CDN 或接口停掉，图鉴页面照样能打开。

数据来源（繁体中文原始响应，保存在 raw/，已剥掉抓取账号的个人进度字段）：
  codex.json        Progression 百科（旧 bot data/battlefield/百科）
  dogtags.json      Progression.getDogtagsByPersonaId（旧 bot data/battlefield/狗牌）
  ribbons.json      勋带（旧 bot data/battlefield/勋带）
  assignments.json  勤务小任务（旧 bot data/battlefield/勤务小任务）
  medals.json       Progression.getMedalsByPersonaId（2026-10-30 用号池账号补拉）
  gamedata.json     Gamedata.getGameData：模式、地图、战争故事章节、阵营（旧 bot data/battlefield/游戏模式）
  tips.json         载入画面小贴士（旧 bot data/battlefield/小标语）

用法（在仓库根目录）：
  # 从旧 bot 目录导入并清洗原始数据（一次性，结果提交到 raw/）
  uv run --no-project --with zhconv --with pillow python tools/bf1-codex/build.py import \\
      --bot-data /srv/umrbot/data/battlefield --medals path/to/medals.json
  # 生成 apps/web 下的数据与图片（图片下载缓存在 tools/bf1-codex/.cache/）
  uv run --no-project --with zhconv --with pillow python tools/bf1-codex/build.py build
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from zhconv import convert

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
CACHE = HERE / ".cache"
WEB = HERE.parent.parent / "apps" / "web"
DATA_OUT = WEB / "lib" / "bf1" / "codex" / "data"
IMG_OUT = WEB / "public" / "bf1" / "codex"

BB_PREFIX = "https://eaassets-a.akamaihd.net/battlelog/battlebinary"

# 抓取账号的个人进度：导入时剥掉，只保留公共内容
PERSONAL_KEYS = {"progression", "equipped", "timesTaken"}

# 资料片：expansions[].name → 简体名（与游戏内中文一致）
EXPANSIONS = {
    "XPACK1": "誓死坚守",
    "XPACK2": "以沙皇之名",
    "XPACK3": "力挽狂澜",
    "XPACK4": "启示录",
}

# 武器百科的枪械类型：从解锁条件代号推出来（如 c_c003_wSMGBergG__kw_g → 冲锋枪）。
# 按顺序匹配，123 件武器全部能归类。
WEAPON_CLASSES = [
    (r"_wSMG", "冲锋枪"),
    (r"_wLMG", "轻机枪"),
    (r"_wRSem", "半自动步枪"),
    (r"_wRSi", "栓动步枪"),
    (r"_wShot", "霰弹枪"),
    (r"_wHS|_wHB", "手枪"),
    (r"_wPC", "手枪卡宾枪"),
    (r"_wM", "近战"),
    (r"_wX|_wSP|_aeqm", "配备"),
    (r"_(fl|st|at|tr)_", "精英兵"),
    (r"_sw", "定点武器"),
    (r"horse", "骑兵"),
]


def zh(text: str | None) -> str:
    return convert(text or "", "zh-cn").strip()


def bb(url: str | None) -> str:
    return (url or "").replace("[BB_PREFIX]", BB_PREFIX)


def expansion(item: dict) -> str:
    """资料片代号（XPACK1–4）；本体返回空串。"""
    for e in item.get("expansions") or []:
        if e.get("name") in EXPANSIONS:
            return e["name"]
    return ""


# ---------------------------------------------------------------- import


def sanitize(node):
    if isinstance(node, dict):
        return {k: sanitize(v) for k, v in node.items() if k not in PERSONAL_KEYS}
    if isinstance(node, list):
        return [sanitize(v) for v in node]
    return node


def cmd_import(args: argparse.Namespace) -> None:
    bot = Path(args.bot_data)
    sources = {
        "codex.json": bot / "百科" / "data.json",
        "dogtags.json": bot / "狗牌" / "data.json",
        "ribbons.json": bot / "勋带" / "data.json",
        "assignments.json": bot / "勤务小任务" / "data.json",
        "medals.json": Path(args.medals),
        "gamedata.json": bot / "游戏模式" / "data.json",
        "tips.json": bot / "小标语" / "data.json",
    }
    RAW.mkdir(parents=True, exist_ok=True)
    for name, src in sources.items():
        result = json.loads(src.read_text(encoding="utf-8"))["result"]
        out = RAW / name
        out.write_text(
            json.dumps(sanitize(result), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"{name}: {src} → {out.relative_to(HERE.parent.parent)}")


# ---------------------------------------------------------------- build


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def build_codex() -> tuple[list, dict, list]:
    entries, texts, images = [], {}, []
    for cat in load("codex.json"):
        for a in cat["awards"]:
            e = a["codexEntry"]
            crit = a["criterias"][0]
            category = zh(e["category"])
            weapon_class = ""
            if category == "武器":
                weapon_class = next(
                    (label for pat, label in WEAPON_CLASSES if re.search(pat, crit["code"])), ""
                )
                if not weapon_class:
                    sys.exit(f"武器 {a['code']} 无法归类：{crit['code']}")
            entries.append(
                {
                    "code": a["code"],
                    "category": category,
                    "weaponClass": weapon_class,
                    "expansion": expansion(a),
                    "name": zh(a["name"]),
                    "header": zh(e["header"]),
                    "subHeader": zh(e.get("subHeader")),
                    "unlock": zh(crit["name"]),
                }
            )
            # 长条目的正文分两段存：description + text2（26 条）
            paragraphs = (zh(e["description"]), zh(e.get("text2")))
            texts[a["code"]] = "\n\n".join(p for p in paragraphs if p)
            images.append((bb(e["images"]["Png640xANY"]), "entries", a["code"], [640, 480]))
    return entries, texts, images


def build_dogtags() -> tuple[list, list]:
    tags, images = [], []
    for cat in load("dogtags.json"):
        for t in cat["dogtags"]:
            tags.append(
                {
                    "id": t["unlockId"],
                    "category": zh(cat["name"]),
                    # 基本狗牌是正面（df*），高级狗牌是背面（db*）
                    "side": "front" if t["tagType"]["name"] == "Basic" else "back",
                    "expansion": expansion(t),
                    "name": zh(t["name"]),
                    "description": zh(t["description"]),
                    "index": t["index"],
                }
            )
            images.append((bb(t["images"]["Png300xANY"]), "dogtags", t["unlockId"], [300]))
    return tags, images


# 狗牌描述里还在用的勋章旧名 → 现名（兵种勋章改过名，狗牌没跟着改）
MEDAL_ALIASES = {"优异医疗勋章": "希波克拉底勋章", "优异钢铁之星勋章": "钢铁之星勋章"}


def build_medals(dogtags: list) -> tuple[list, list]:
    # 奖励狗牌的描述固定是「取得 X 时的奖励」，分散在勋章、兵种等多个分类里
    by_name: dict[str, list[str]] = {}
    for t in dogtags:
        m = re.match(r"^取得(.+?)时的奖励", t["description"])
        if m:
            name = m.group(1).strip()
            by_name.setdefault(MEDAL_ALIASES.get(name, name), []).append(t["id"])
    medals, images = [], []
    for cat in load("medals.json"):
        for a in cat["awards"]:
            name = zh(a["name"])
            medals.append(
                {
                    "code": a["code"],
                    "category": zh(cat["name"]),
                    "expansion": expansion(a),
                    "name": name,
                    "description": zh(a["description"]),
                    "score": a["score"],
                    "stages": [{"name": zh(s["name"]), "score": s["score"]} for s in a["stages"]],
                    "dogtags": sorted(set(by_name.get(name, []))),
                }
            )
            images.append((bb(a["imageUrl"]), "medals", a["code"], [256]))
    known = {m["name"] for m in medals}
    orphan = sorted(n for n in by_name if n not in known)
    if orphan:
        sys.exit(f"奖励狗牌没对上勋章：{orphan}")
    return medals, images


def build_ribbons() -> tuple[list, list]:
    ribbons, images = [], []
    for cat in load("ribbons.json"):
        for a in cat["awards"]:
            ribbons.append(
                {
                    "code": a["code"],
                    "category": zh(cat["name"]),
                    "expansion": expansion(a),
                    "name": zh(a["name"]),
                    "description": zh(a["description"]),
                    "score": a["score"],
                }
            )
            images.append((bb(a["imageUrl"]), "ribbons", a["code"], [256]))
    return ribbons, images


def build_assignments() -> tuple[list, list]:
    items, images = [], []
    for group in load("assignments.json"):
        for a in group["awards"]:
            items.append(
                {
                    "code": a["code"],
                    "group": zh(group["name"]),
                    "name": zh(a["name"]),
                    "description": zh(a["description"]),
                    "criteria": [zh(c["name"]) for c in a["criterias"]],
                    "requires": [d["code"] for d in a.get("dependencies") or []],
                    "image": Path(bb(a["imageUrl"])).stem.rsplit("-", 1)[0],
                }
            )
            images.append((bb(a["imageUrl"]), "assignments", items[-1]["image"], [256]))
    return items, images


# 战争故事 → 章节（gamedata 里只有章节，没有归属）。按游戏菜单顺序排列，
# 章节归属对照 IGN 攻略的任务列表核对过，也和百科条目的解锁条件一一对得上
# （例如「至上权威」的 4 章都出现在空战相关条目里）。completion 是「完成某故事」解锁的百科条目。
STORIES = [
    {"id": "prologue", "name": "破晓", "en": "Storm of Steel", "kind": "prologue",
     "completion": "c157", "chapters": ["SP_Prologue"]},
    {"id": "mud-and-blood", "name": "浴血之战", "en": "Through Mud and Blood", "kind": "story",
     "completion": "c174",
     "chapters": ["SP_TankAssault", "SP_FogOfWar", "SP_OutOfGas", "SP_SteelOnSteel"]},
    {"id": "high-places", "name": "至上权威", "en": "Friends in High Places", "kind": "story",
     "completion": "c172",
     "chapters": ["SP_FlightSchool", "SP_TotalWar", "SP_CarryYourFriend", "SP_Blitz"]},
    {"id": "avanti-savoia", "name": "萨伏依万岁！", "en": "Avanti Savoia!", "kind": "story",
     "completion": "c175", "chapters": ["SP_Arditi", "SP_SearchRescue"]},
    {"id": "the-runner", "name": "传令兵", "en": "The Runner", "kind": "story",
     "completion": "c176", "chapters": ["SP_Gallipoli", "SP_TheRunaround", "SP_SavingALife"]},
    {"id": "nothing-is-written", "name": "事在人为", "en": "Nothing Is Written", "kind": "story",
     "completion": "c173",
     "chapters": ["SP_HiddenInPlainSight", "SP_YoungMensWork", "SP_HearTheDesert"]},
    {"id": "epilogue", "name": "勿忘我们", "en": "Epilogue", "kind": "epilogue",
     "completion": "", "chapters": ["SP_Epilogue"]},
]  # fmt: skip

# 地图资料片里多了一个 XPACK0：免费地图「庞然暗影」
MAP_EXPANSIONS = {"XPACK0": "庞然暗影", **EXPANSIONS}


def build_battlefield(codex: list) -> tuple[dict, list, list]:
    """模式、多人地图、战争故事、阵营，顺带把百科条目和小贴士按名称、代号串上。"""
    gd = load("gamedata.json")
    # 「在 X 赢得 1 场游戏」「在 X 模式中赢得…」「扮演 X 赢得…」→ 对应的百科条目
    win: dict[str, str] = {}
    for e in codex:
        m = re.match(r"^(?:在|扮演)(.+?)(?:模式)?中?赢得 1 场游戏$", e["unlock"])
        if m:
            win[m.group(1)] = e["code"]
    # 「在“章节名”中……」→ 该章节解锁的百科条目；「完成“故事名”」是故事通关奖励，另算
    by_chapter: dict[str, list[str]] = {}
    for e in codex:
        m = re.search(r"“(.+?)”", e["unlock"])
        if m and not e["unlock"].startswith("完成"):
            by_chapter.setdefault(m.group(1), []).append(e["code"])

    tips_raw = load("tips.json")
    tips = [
        {
            "text": zh(t["name"]),
            "type": "map" if t["tipType"]["name"] == "Level" else "mode",
            "tags": t.get("tags") or [],
        }
        for t in tips_raw
    ]

    images = []
    modes = []
    for m in gd["gameModes"]:
        name = zh(m["prettyName"])
        modes.append(
            {
                "id": m["name"],
                "name": name,
                "header": zh(m["header"]),
                "body": zh(m["body"]),
                # 「行动模式」的解锁条件写作「在行动模式中」，正则把「模式」当后缀去掉了
                "codex": win.get(name) or win.get(name.removesuffix("模式"), ""),
            }
        )
        images.append((bb(m["images"]["Jpg1000xANY"]), "modes", m["name"], [1000, 480]))

    maps, chapters = [], {}
    for m in gd["maps"]:
        asset, name = m["assetName"], zh(m["name"])
        if m["levelType"] == "MP":
            xp = next((e["name"] for e in m["expansions"] if e["name"] in MAP_EXPANSIONS), "")
            maps.append({"id": asset, "expansion": xp, "codex": win.get(name, "")})
            images.append((bb(m["images"]["Jpg1000xANY"]), "maps", asset, [1000, 480]))
        elif asset.startswith("SP_"):
            # 章节在 gamedata 里只有占位图，页面改用章节解锁的百科条目配图
            chapters[asset] = {"id": asset, "name": name, "codex": by_chapter.get(name, [])}

    stories = []
    for s in STORIES:
        missing = [c for c in s["chapters"] if c not in chapters]
        if missing:
            sys.exit(f"战争故事 {s['name']} 的章节不在 gamedata 里：{missing}")
        stories.append({**s, "chapters": [chapters.pop(c) for c in s["chapters"]]})
    if chapters:
        sys.exit(f"有章节没归到任何战争故事：{sorted(chapters)}")

    # 同名阵营在数据里有重复（如两个鄂图曼帝国），按全称去重
    factions, seen = [], set()
    for f in gd["factions"]:
        name = zh(f["name"])
        if name in seen:
            continue
        seen.add(name)
        factions.append(
            {
                "id": f["key"],
                "name": name,
                "short": zh(f["shortName"]),
                "codex": win.get(name, ""),
            }
        )
        images.append((bb(f["images"]["Png160xANY"]), "factions", f["key"], [160]))

    unknown = sorted(
        {t for tip in tips for t in tip["tags"]}
        - {m["id"] for m in maps}
        - {m["id"] for m in modes}
    )
    if unknown:
        sys.exit(f"小贴士标签对不上地图或模式：{unknown}")

    data = {"modes": modes, "maps": maps, "stories": stories, "factions": factions}
    return data, tips, images


def fetch(url: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / re.sub(r"[^\w.-]", "_", url.removeprefix(BB_PREFIX))
    if cached.exists():
        return cached.read_bytes()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
            cached.write_bytes(data)
            return data
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError


def save_image(job: tuple[str, str, str, list[int]]) -> int:
    url, folder, name, widths = job
    img = Image.open(io.BytesIO(fetch(url)))
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    total = 0
    for i, width in enumerate(widths):
        sub = folder if i == 0 else f"{folder}-{width}"
        out = IMG_OUT / sub / f"{name}.webp"
        out.parent.mkdir(parents=True, exist_ok=True)
        im = (
            img
            if img.width == width
            else img.resize(
                (width, round(img.height * width / img.width)), Image.Resampling.LANCZOS
            )
        )
        im.save(out, "WEBP", quality=82 if i == 0 else 78, method=6)
        total += out.stat().st_size
    return total


def excerpt(text: str, limit: int = 90) -> str:
    """正文开头的几句：按句号截，凑到 limit 字左右；第一句就太长时硬截加省略号"""
    para = text.split("\n")[0].strip()
    out = ""
    for sentence in re.findall(r"[^。！？]+[。！？]?", para):
        if out and len(out) + len(sentence) > limit:
            break
        out += sentence
    return out if len(out) <= limit * 1.5 else out[:limit].rstrip("，、；") + "…"


def build_map_intros(battlefield: dict, codex: list, texts: dict) -> dict:
    """服务器页地图说明用的小摘要：百科标题 + 开头几句，避免为了一句简介加载整份百科正文"""
    headers = {e["code"]: e["header"] for e in codex}
    return {
        m["id"]: {"header": headers[m["codex"]], "excerpt": excerpt(texts[m["codex"]])}
        for m in battlefield["maps"]
        if m["codex"]
    }


def write(name: str, data) -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    path = DATA_OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    print(f"  {path.relative_to(WEB)}  {path.stat().st_size / 1024:.0f} KB")


def cmd_build(_: argparse.Namespace) -> None:
    codex, texts, img_codex = build_codex()
    dogtags, img_tags = build_dogtags()
    medals, img_medals = build_medals(dogtags)
    ribbons, img_ribbons = build_ribbons()
    assignments, img_assign = build_assignments()
    battlefield, tips, img_field = build_battlefield(codex)

    print("数据：")
    write("codex.json", codex)
    write("codex-text.json", texts)
    write("dogtags.json", dogtags)
    write("medals.json", medals)
    write("ribbons.json", ribbons)
    write("assignments.json", assignments)
    write("battlefield.json", battlefield)
    write("tips.json", tips)
    write("map-intros.json", build_map_intros(battlefield, codex, texts))
    # 前端 CI 会对 json 跑 prettier --check，写完按仓库的格式排一遍
    subprocess.run(
        ["pnpm", "exec", "prettier", "--write", "--log-level", "warn", str(DATA_OUT)],
        cwd=WEB,
        check=True,
    )

    jobs = img_codex + img_tags + img_medals + img_ribbons + img_assign + img_field
    # 勤务小任务有几项共用同一张图
    jobs = list({(j[1], j[2]): j for j in jobs}.values())
    print(f"图片：{len(jobs)} 张原图")
    with ThreadPoolExecutor(8) as pool:
        total = sum(pool.map(save_image, jobs))
    print(f"  public/bf1/codex/  {total / 1024 / 1024:.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(required=True)
    p_import = sub.add_parser("import", help="从旧 bot 目录导入并清洗原始数据")
    p_import.add_argument("--bot-data", required=True)
    p_import.add_argument("--medals", required=True)
    p_import.set_defaults(func=cmd_import)
    sub.add_parser("build", help="生成前端数据与图片").set_defaults(func=cmd_build)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
