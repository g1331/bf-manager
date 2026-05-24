"""initial schema: shared core tables + bf1 specific tables

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24 15:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260524_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== users =====
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("encrypted_remid", sa.Text(), nullable=True),
        sa.Column("encrypted_sid", sa.Text(), nullable=True),
        sa.Column("encrypted_session", sa.Text(), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("persona_id", name="uq_users_persona_id"),
    )
    op.create_index("ix_users_persona_id", "users", ["persona_id"])

    # ===== ea_accounts =====
    op.create_table(
        "ea_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("encrypted_remid", sa.Text(), nullable=False),
        sa.Column("encrypted_sid", sa.Text(), nullable=False),
        sa.Column("encrypted_session", sa.Text(), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ea_accounts"),
        sa.UniqueConstraint("persona_id", name="uq_ea_accounts_persona_id"),
    )
    op.create_index("ix_ea_accounts_persona_id", "ea_accounts", ["persona_id"])

    # ===== servers =====
    op.create_table(
        "servers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game", sa.String(length=16), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("persisted_game_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_servers"),
        sa.UniqueConstraint("game", "server_id", name="uq_servers_game_server_id"),
    )
    op.create_index("ix_servers_game", "servers", ["game"])
    op.create_index("ix_servers_server_id", "servers", ["server_id"])
    op.create_index("ix_servers_persisted_game_id", "servers", ["persisted_game_id"])

    # ===== server_memberships =====
    op.create_table(
        "server_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("server_pk", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_server_memberships_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["server_pk"],
            ["servers.id"],
            ondelete="CASCADE",
            name="fk_server_memberships_server_pk_servers",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_server_memberships_granted_by_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_server_memberships"),
        sa.UniqueConstraint("user_id", "server_pk", name="uq_server_memberships_user_server"),
    )
    op.create_index("ix_server_memberships_user_id", "server_memberships", ["user_id"])
    op.create_index("ix_server_memberships_server_pk", "server_memberships", ["server_pk"])

    # ===== audit_logs =====
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("acting_persona_id", sa.BigInteger(), nullable=False),
        sa.Column("game", sa.String(length=16), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_persona_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_audit_logs_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_acting_persona_id", "audit_logs", ["acting_persona_id"])
    op.create_index("ix_audit_logs_game", "audit_logs", ["game"])
    op.create_index("ix_audit_logs_server_id", "audit_logs", ["server_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_target_persona_id", "audit_logs", ["target_persona_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ===== bf1_server_player_counts =====
    op.create_table(
        "bf1_server_player_counts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_pk", sa.Integer(), nullable=False),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("queue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spectator_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_player_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "sampled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["server_pk"],
            ["servers.id"],
            ondelete="CASCADE",
            name="fk_bf1_server_player_counts_server_pk_servers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_server_player_counts"),
    )
    op.create_index(
        "ix_bf1_server_player_counts_server_time",
        "bf1_server_player_counts",
        ["server_pk", "sampled_at"],
    )

    # ===== bf1_server_vips / bans / admins / owners =====
    for tbl in ("bf1_server_vips", "bf1_server_bans", "bf1_server_admins", "bf1_server_owners"):
        extra_cols: list[sa.Column] = []
        if tbl == "bf1_server_vips":
            extra_cols = [sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)]
        elif tbl == "bf1_server_bans":
            extra_cols = [
                sa.Column("reason", sa.Text(), nullable=True),
                sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            ]
        constraint_key = (
            "vips"
            if tbl == "bf1_server_vips"
            else "bans"
            if tbl == "bf1_server_bans"
            else "admins"
            if tbl == "bf1_server_admins"
            else "owners"
        )
        op.create_table(
            tbl,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("server_pk", sa.Integer(), nullable=False),
            sa.Column("persona_id", sa.BigInteger(), nullable=False),
            sa.Column("display_name", sa.String(length=64), nullable=True),
            *extra_cols,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["server_pk"],
                ["servers.id"],
                ondelete="CASCADE",
                name=f"fk_{tbl}_server_pk_servers",
            ),
            sa.PrimaryKeyConstraint("id", name=f"pk_{tbl}"),
            sa.UniqueConstraint(
                "server_pk",
                "persona_id",
                name=f"uq_bf1_{constraint_key}_server_persona",
            ),
        )
        op.create_index(f"ix_{tbl}_server_pk", tbl, ["server_pk"])
        op.create_index(f"ix_{tbl}_persona_id", tbl, ["persona_id"])

    # ===== bf1_server_manager_vips =====
    op.create_table(
        "bf1_server_manager_vips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_pk", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["server_pk"],
            ["servers.id"],
            ondelete="CASCADE",
            name="fk_bf1_server_manager_vips_server_pk_servers",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_bf1_server_manager_vips_granted_by_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_server_manager_vips"),
        sa.UniqueConstraint(
            "server_pk",
            "persona_id",
            "valid_from",
            name="uq_bf1_manager_vips_server_persona_from",
        ),
    )
    op.create_index(
        "ix_bf1_server_manager_vips_server_pk", "bf1_server_manager_vips", ["server_pk"]
    )
    op.create_index(
        "ix_bf1_server_manager_vips_persona_id", "bf1_server_manager_vips", ["persona_id"]
    )

    # ===== bf1_match_id_caches =====
    op.create_table(
        "bf1_match_id_caches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("match_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_match_id_caches"),
    )
    op.create_index("ix_bf1_match_id_caches_persona", "bf1_match_id_caches", ["persona_id"])
    op.create_index("ix_bf1_match_id_caches_persona_id", "bf1_match_id_caches", ["persona_id"])

    # ===== bf1_matches =====
    op.create_table(
        "bf1_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.String(length=64), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("map_name", sa.String(length=64), nullable=True),
        sa.Column("game_mode", sa.String(length=64), nullable=True),
        sa.Column("server_name", sa.String(length=255), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bf1_matches"),
        sa.UniqueConstraint("match_id", name="uq_bf1_matches_match_id"),
    )
    op.create_index("ix_bf1_matches_match_id", "bf1_matches", ["match_id"])
    op.create_index("ix_bf1_matches_played_at", "bf1_matches", ["played_at"])


def downgrade() -> None:
    op.drop_table("bf1_matches")
    op.drop_table("bf1_match_id_caches")
    op.drop_table("bf1_server_manager_vips")
    op.drop_table("bf1_server_owners")
    op.drop_table("bf1_server_admins")
    op.drop_table("bf1_server_bans")
    op.drop_table("bf1_server_vips")
    op.drop_table("bf1_server_player_counts")
    op.drop_table("audit_logs")
    op.drop_table("server_memberships")
    op.drop_table("servers")
    op.drop_table("ea_accounts")
    op.drop_table("users")
