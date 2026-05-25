"""CLI 子命令实现：本地账号与 admin 名单管理

所有命令通过 `python -m app.cli <name>` 入口调用。命令内部走异步 DB session。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.db.session import close_engine, get_sessionmaker
from app.models import User
from app.services.user_service import UserService


def _resolve_password(args: argparse.Namespace, prompt_label: str = "Password") -> str:
    """按优先级取密码：--password > --password-stdin > 交互式 getpass。

    --password：不安全（进入 shell history）但便于自动化
    --password-stdin：从 stdin 读取（推荐脚本场景）
    无参数：getpass 交互式 prompt（推荐人工场景，不回显且不进 history）
    """
    if args.password is not None:
        return args.password
    if args.password_stdin:
        data = sys.stdin.read()
        # 允许 stdin 末尾有换行
        return data.rstrip("\r\n")
    try:
        pw1 = getpass.getpass(f"{prompt_label}: ")
        pw2 = getpass.getpass(f"{prompt_label} (confirm): ")
    except EOFError:
        # 非 TTY 环境（如 docker compose exec -T）下 getpass 立即 EOF。
        # 给出明确的下一步提示而非抛 Python traceback。
        print(
            "无法从交互式 prompt 读取密码（当前环境无 TTY）。"
            "请改用 --password-stdin 或 --password 参数。",
            file=sys.stderr,
        )
        sys.exit(2)
    if pw1 != pw2:
        print("两次输入的密码不一致", file=sys.stderr)
        sys.exit(2)
    return pw1


def cmd_create_admin(args: argparse.Namespace) -> int:
    password = _resolve_password(args, "Password")
    if not password:
        print("密码不能为空", file=sys.stderr)
        return 2
    return asyncio.run(_run_create_admin(args.username, password, args.email))


async def _run_create_admin(username: str, password: str, email: str | None) -> int:
    try:
        async with get_sessionmaker()() as session:
            users = UserService(session)
            user = await users.create_local_admin(username=username, password=password, email=email)
            print(f"已创建本地管理员: id={user.id} username={user.username} role={user.role}")
            return 0
    except ValueError as e:
        print(f"创建失败: {e}", file=sys.stderr)
        return 1
    finally:
        await close_engine()


def cmd_reset_password(args: argparse.Namespace) -> int:
    password = _resolve_password(args, "New password")
    if not password:
        print("密码不能为空", file=sys.stderr)
        return 2
    return asyncio.run(_run_reset_password(args.username, password))


async def _run_reset_password(username: str, password: str) -> int:
    try:
        async with get_sessionmaker()() as session:
            users = UserService(session)
            user = await users.get_by_username(username)
            if user is None:
                print(f"username='{username}' 不存在", file=sys.stderr)
                return 1
            await users.set_local_password(user, password)
            print(f"已重置 {username} 的密码")
            return 0
    finally:
        await close_engine()


def cmd_list_admins(_args: argparse.Namespace) -> int:
    return asyncio.run(_run_list_admins())


async def _run_list_admins() -> int:
    try:
        async with get_sessionmaker()() as session:
            rows = (await session.scalars(select(User).where(User.role == "admin"))).all()
            if not rows:
                print("（无 admin）")
                return 0
            print(f"{'id':>4}  {'username':<32}  {'has_password':<13}  last_login_at")
            for u in rows:
                has_pw = "yes" if u.local_password_hash else "no"
                print(
                    f"{u.id:>4}  {u.username:<32}  {has_pw:<13}  "
                    f"{u.last_login_at.isoformat() if u.last_login_at else '-'}"
                )
            return 0
    finally:
        await close_engine()


def cmd_grant_admin(args: argparse.Namespace) -> int:
    return asyncio.run(_run_grant_admin(args.persona))


async def _run_grant_admin(persona_id: int) -> int:
    try:
        async with get_sessionmaker()() as session:
            users = UserService(session)
            user = await users.grant_admin(persona_id)
            print(
                f"已将 username={user.username} (id={user.id}, persona_id={persona_id}) 升级为 admin"
            )
            return 0
    except ValueError as e:
        print(f"提权失败: {e}", file=sys.stderr)
        return 1
    finally:
        await close_engine()


def cmd_revoke_admin(args: argparse.Namespace) -> int:
    return asyncio.run(_run_revoke_admin(args.persona))


async def _run_revoke_admin(persona_id: int) -> int:
    try:
        async with get_sessionmaker()() as session:
            users = UserService(session)
            user = await users.revoke_admin(persona_id)
            print(
                f"已将 username={user.username} (id={user.id}, persona_id={persona_id}) 降回 user"
            )
            return 0
    except ValueError as e:
        print(f"降权失败: {e}", file=sys.stderr)
        return 1
    finally:
        await close_engine()
