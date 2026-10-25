"""导出 BF1 静态配置（Gateway ``Gamedata.getGameData``）到 app/domain/games/bf1/data/

EA 只提供繁体（zhtw）与英文，zhcn 等会退回英文，所以简体版由繁体转换得到：
OpenCC ``tw2sp``（台湾用语 → 大陆用语），地图 / 模式名再以 ``MapData`` 里的现有译名为准，
与站内其它地方保持一致。分两步，因为生产容器里没有 OpenCC：

1. 拉取（需要号池账号，生产容器内执行）：

    docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend \
        python tools/export_bf1_gamedata.py fetch /tmp/gamedata

   会临时切换会话语言拉 en，结束后恢复 zhtw。产出 gamedata.zh-TW.json / gamedata.en.json。

2. 转简体（本地 apps/backend 目录下）：

    uv run --with opencc python tools/export_bf1_gamedata.py simplify

   读 data/gamedata.zh-TW.json，写 data/gamedata.zh-CN.json。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# 脚本被 `python tools/xxx.py` 启动时，sys.path[0] 是 tools/ 自身，
# 需要把仓库根（含 app/ 包的目录）显式加进去才能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_sessionmaker
from app.domain.games.bf1.maps import MapData
from app.services.bf1.gateway_factory import get_bf1_client

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "domain" / "games" / "bf1" / "data"


def _dump(data: Any, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


async def fetch(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    async with get_sessionmaker()() as db, get_bf1_client(db) as client:
        try:
            for locale, suffix in (("zhtw", "zh-TW"), ("en", "en")):
                await client.setLocale(locale)
                resp = await client.getGameData()
                if not isinstance(resp, dict) or "result" not in resp:
                    raise RuntimeError(f"getGameData({locale}) 失败: {resp}")
                _dump(resp["result"], out_dir / f"gamedata.{suffix}.json")
        finally:
            # 会话被生产请求共用，必须切回登录时设置的 zhtw
            await client.setLocale("zhtw")


def simplify() -> None:
    # 只有转简体这一步需要 OpenCC，不进项目依赖，按 docstring 用 uv run --with 临时装
    import opencc  # noqa: PLC0415

    converter = opencc.OpenCC("tw2sp")

    def convert(node: Any) -> Any:
        if isinstance(node, str):
            # 图片地址、URL 与 key 都是 ASCII，原样保留
            return node if node.isascii() else converter.convert(node)
        if isinstance(node, list):
            return [convert(item) for item in node]
        if isinstance(node, dict):
            return {key: convert(value) for key, value in node.items()}
        return node

    data = convert(json.loads((DATA_DIR / "gamedata.zh-TW.json").read_text(encoding="utf-8")))
    for game_map in data["maps"]:
        name = (MapData.MapTeamDict.get(game_map["assetName"]) or {}).get("Chinese")
        if name:
            game_map["name"] = name
    for mode in data["gameModes"]:
        name = MapData.ModeDict.get(mode["name"])
        if name:
            mode["prettyName"] = name
    _dump(data, DATA_DIR / "gamedata.zh-CN.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch_parser = sub.add_parser("fetch", help="从 Gateway 拉取 zh-TW / en 原始数据")
    fetch_parser.add_argument("out_dir", type=Path, nargs="?", default=DATA_DIR)
    sub.add_parser("simplify", help="由 zh-TW 生成 zh-CN")
    args = parser.parse_args()
    if args.cmd == "fetch":
        asyncio.run(fetch(args.out_dir))
    else:
        simplify()


if __name__ == "__main__":
    main()
