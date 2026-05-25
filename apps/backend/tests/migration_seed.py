"""为 alembic 迁移回环验证灌入假数据

使用场景：CI 在 alembic upgrade 20260524_0001（初始 schema）之后调用本脚本，
插入若干 user / server_membership / audit_log，然后再 alembic upgrade head 触发
20260525_0002（身份与凭据解耦）的数据搬运逻辑。downgrade 时验证能反向重建。

不依赖 ORM，直接 raw SQL，避免被「当前代码 model 不含旧字段」干扰。
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)

    async with engine.begin() as conn:
        # 三条 user：两条普通 + 一条「将被升为 admin」
        await conn.execute(
            text(
                """
                INSERT INTO users (
                    persona_id, display_name, avatar_url,
                    encrypted_remid, encrypted_sid, encrypted_session, encrypted_access_token,
                    role, is_active, last_login_at
                ) VALUES
                    (1003517866915, 'PlayerA', 'https://example.com/a.png',
                     'enc-remid-a', 'enc-sid-a', 'enc-sess-a', 'enc-tok-a',
                     'user', true, now() - interval '1 day'),
                    (1004198901469, 'PlayerB', NULL,
                     'enc-remid-b', 'enc-sid-b', NULL, NULL,
                     'user', true, now() - interval '2 days'),
                    (1005000000001, 'AdminPlayer', 'https://example.com/admin.png',
                     'enc-remid-c', 'enc-sid-c', 'enc-sess-c', 'enc-tok-c',
                     'admin', true, now())
                """
            )
        )

        # 一条 server + 一条 membership，验证 user_id 外键在迁移后仍指向同一行
        await conn.execute(
            text(
                """
                INSERT INTO servers (game, server_id, name)
                VALUES ('bf1', 12345, 'TestServer')
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO server_memberships (user_id, server_pk, role)
                SELECT u.id, s.id, 'owner'
                FROM users u, servers s
                WHERE u.persona_id = 1005000000001 AND s.server_id = 12345
                """
            )
        )

        # 一条 audit_log，验证 acting_persona_id 字段保持原值
        await conn.execute(
            text(
                """
                INSERT INTO audit_logs (
                    user_id, acting_persona_id, game, action, payload, result
                )
                SELECT id, persona_id, 'bf1', 'test.action', '{}'::json, 'success'
                FROM users WHERE persona_id = 1005000000001
                """
            )
        )

    await engine.dispose()
    print("seed: inserted 3 users + 1 server + 1 membership + 1 audit_log")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
