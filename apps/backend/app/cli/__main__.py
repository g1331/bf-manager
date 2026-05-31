"""`python -m app.cli` 入口分发"""

from __future__ import annotations

import argparse
import sys

from app.cli.admin import (
    cmd_create_admin,
    cmd_grant_admin,
    cmd_list_admins,
    cmd_reset_password,
    cmd_revoke_admin,
    cmd_upsert_ea_account,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="bf-manager 后端 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-admin", help="创建本地管理员账号")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--email", default=None)
    _add_password_args(p_create)
    p_create.set_defaults(handler=cmd_create_admin)

    p_reset = sub.add_parser("reset-password", help="重置本地账号密码")
    p_reset.add_argument("--username", required=True)
    _add_password_args(p_reset)
    p_reset.set_defaults(handler=cmd_reset_password)

    p_list = sub.add_parser("list-admins", help="列出所有 role=admin 的 user")
    p_list.set_defaults(handler=cmd_list_admins)

    p_grant = sub.add_parser("grant-admin", help="把指定 persona 对应的 user 升为 admin")
    p_grant.add_argument("--persona", type=int, required=True)
    p_grant.set_defaults(handler=cmd_grant_admin)

    p_revoke = sub.add_parser("revoke-admin", help="把指定 persona 对应的 user 降为 user")
    p_revoke.add_argument("--persona", type=int, required=True)
    p_revoke.set_defaults(handler=cmd_revoke_admin)

    p_ea = sub.add_parser(
        "upsert-ea-account", help="创建或更新账号池中的 EA 服管账号（按 persona_id）"
    )
    p_ea.add_argument("--persona-id", type=int, required=True, help="EA persona_id")
    p_ea.add_argument("--display-name", default=None)
    p_ea.add_argument("--disable", action="store_true", help="写入后置为停用")
    p_ea.add_argument(
        "--stdin-json",
        action="store_true",
        help="从 stdin 读取凭据 JSON（键 remid/sid/session/access_token，不进 history，推荐）",
    )
    p_ea.add_argument("--remid", default=None, help="不安全：会进入 shell history")
    p_ea.add_argument("--sid", default=None, help="不安全：会进入 shell history")
    p_ea.add_argument("--session", default=None, help="不安全：会进入 shell history")
    p_ea.add_argument("--access-token", default=None, help="不安全：会进入 shell history")
    p_ea.set_defaults(handler=cmd_upsert_ea_account)

    return parser


def _add_password_args(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--password", default=None, help="直接传入密码（不安全，会进入 shell history）")
    g.add_argument(
        "--password-stdin",
        action="store_true",
        help="从 stdin 读取密码（推荐脚本场景）",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
