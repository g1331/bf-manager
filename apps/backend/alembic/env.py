"""Alembic 环境配置（async）"""

from __future__ import annotations

import asyncio
import re
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.models import Base  # 触发所有模型注册
from sqlalchemy import JSON, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

# alembic.ini 里的 sqlalchemy.url 仅作占位，运行时从 Settings 拿
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _json_literal(default: str) -> str:
    return re.sub(r"::json$", "", default).strip("'")


def compare_server_default(
    context, inspected_column, metadata_column, inspected_default, metadata_default, rendered
):
    """JSON 列的默认值按文本比，其余交给 alembic

    PG 把默认值读回来时带类型转换（'{}'::json），alembic 默认会在库里跑
    SELECT '{}'::json = '{}' 来比，而 json 没有 = 运算符，check 直接报错。
    """
    if isinstance(inspected_column.type, JSON) and inspected_default and rendered:
        return _json_literal(inspected_default) != _json_literal(rendered)
    return None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=compare_server_default,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=compare_server_default,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
