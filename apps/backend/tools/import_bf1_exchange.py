"""把 umrbot 存档的历史交换（data/battlefield/exchange/YYYY年MM月DD日.json）导入 bf1_exchange_snapshots

    python tools/import_bf1_exchange.py /path/to/exchange

文件名是北京时间日期，记为当天 0 点。按日期顺序导入，与上一期物品相同的跳过；已导入的日期
不会重复写入，可重复执行。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_sessionmaker
from app.services.bf1.exchange_service import CN_TZ, save_exchange_if_changed


def load_archive(directory: Path) -> list[tuple[datetime, list[dict]]]:
    periods = []
    for f in directory.glob("*.json"):
        try:
            day = datetime.strptime(f.stem, "%Y年%m月%d日").replace(tzinfo=CN_TZ)
            items = json.loads(f.read_text(encoding="utf-8"))["result"]["items"]
        except (ValueError, KeyError, TypeError) as e:
            print(f"skip {f.name}: {e!r}")
            continue
        if items:
            periods.append((day, items))
    return sorted(periods, key=lambda p: p[0])


async def main(directory: Path) -> None:
    periods = load_archive(directory)
    written = 0
    async with get_sessionmaker()() as db:
        for day, items in periods:
            written += await save_exchange_if_changed(db, items, day)
    print(f"{len(periods)} files, {written} periods written")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    asyncio.run(main(parser.parse_args().directory))
