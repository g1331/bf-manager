"""player_name_lower_index：按名字（不分大小写）找人

Revision ID: 20261105_0026
Revises: 20261104_0025
Create Date: 2026-11-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0026"
down_revision: str | None = "20261104_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_bf1_player_names_name_lower", "bf1_player_names", [sa.text("lower(name)")])


def downgrade() -> None:
    op.drop_index("ix_bf1_player_names_name_lower", table_name="bf1_player_names")
