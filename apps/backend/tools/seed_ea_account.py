"""向 ea_accounts 表写入一个 EA 代查询账号

本地开发用法（apps/backend 目录下）：

    uv run python tools/seed_ea_account.py \
        --persona-id 1234567890 \
        --remid <REMID> --sid <SID>

生产容器用法：

    docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend \
        python tools/seed_ea_account.py --persona-id 1234567890 \
        --remid <REMID> --sid <SID>

会自动 AES-GCM 加密入库，已存在则更新 remid/sid。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 脚本被 `python tools/xxx.py` 启动时，sys.path[0] 是 tools/ 自身，
# 需要把仓库根（含 app/ 包的目录）显式加进去才能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import get_cipher
from app.db.session import get_sessionmaker
from app.models import EAAccount
from sqlalchemy import select


async def seed(persona_id: int, remid: str, sid: str, display_name: str | None) -> None:
    cipher = get_cipher()
    session_local = get_sessionmaker()
    async with session_local() as db:
        existing = await db.scalar(select(EAAccount).where(EAAccount.persona_id == persona_id))
        if existing is None:
            account = EAAccount(
                persona_id=persona_id,
                display_name=display_name,
                encrypted_remid=cipher.encrypt(remid),
                encrypted_sid=cipher.encrypt(sid),
                enabled=True,
            )
            db.add(account)
            print(f"created EAAccount persona_id={persona_id}")
        else:
            existing.encrypted_remid = cipher.encrypt(remid)
            existing.encrypted_sid = cipher.encrypt(sid)
            if display_name:
                existing.display_name = display_name
            existing.enabled = True
            existing.failure_count = 0
            print(f"updated EAAccount persona_id={persona_id}")
        await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona-id", type=int, required=True)
    parser.add_argument("--remid", required=True)
    parser.add_argument("--sid", required=True)
    parser.add_argument("--display-name", default=None)
    args = parser.parse_args()
    asyncio.run(
        seed(
            persona_id=args.persona_id,
            remid=args.remid,
            sid=args.sid,
            display_name=args.display_name,
        )
    )


if __name__ == "__main__":
    main()
