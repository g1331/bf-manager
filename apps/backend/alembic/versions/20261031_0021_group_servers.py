"""group_servers：群组服务账号、挂在群上的服、审计记执行账号

Revision ID: 20261031_0021
Revises: 20261031_0020
Create Date: 2026-10-31 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0021"
down_revision: str | None = "20261031_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_ea_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("encrypted_remid", sa.Text(), nullable=False),
        sa.Column("encrypted_sid", sa.Text(), nullable=False),
        sa.Column("encrypted_session", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("group_id", "persona_id", name="uq_group_ea_accounts_group_persona"),
    )
    op.create_index("ix_group_ea_accounts_group_id", "group_ea_accounts", ["group_id"])

    op.create_table(
        "group_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_pk",
            sa.Integer(),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bound_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bound_via", sa.String(16), nullable=False),
        sa.Column(
            "executor_account_id",
            sa.Integer(),
            sa.ForeignKey("group_ea_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("status_reason", sa.String(255), nullable=True),
        sa.Column("executor_problem", sa.String(255), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("group_id", "server_pk", name="uq_group_servers_group_server"),
    )
    op.create_index("ix_group_servers_group_id", "group_servers", ["group_id"])
    op.create_index("ix_group_servers_server_pk", "group_servers", ["server_pk"])

    op.add_column("audit_logs", sa.Column("executor_persona_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "executor_persona_id")
    op.drop_index("ix_group_servers_server_pk", table_name="group_servers")
    op.drop_index("ix_group_servers_group_id", table_name="group_servers")
    op.drop_table("group_servers")
    op.drop_index("ix_group_ea_accounts_group_id", table_name="group_ea_accounts")
    op.drop_table("group_ea_accounts")
