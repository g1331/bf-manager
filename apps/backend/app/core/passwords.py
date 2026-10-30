"""本地账号密码哈希与校验（bcrypt 原生 API + sha256 预处理）

为何不用 passlib：passlib 1.7.4 多年未更新，对 bcrypt 4.1+ 的 backend 版本探测崩溃，
而 bcrypt 后续小版本只升不降。直接用 bcrypt 原生 API 更稳。

为何 sha256 预处理：bcrypt 算法限制密码 <= 72 字节，超出会被截断或抛 ValueError。
先用 sha256 hex 摘要（固定 64 ASCII 字节，<72）再进 bcrypt，可以承载任意长度密码且不丢熵。
对于「sha256(pw) 与 sha256(pw') 碰撞」的可能性远低于 bcrypt 自身的破解难度，安全无折损。
"""

from __future__ import annotations

import hashlib
from functools import cache

import bcrypt


def _preprocess(plain: str) -> bytes:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("密码不能为空")
    return bcrypt.hashpw(_preprocess(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_preprocess(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


@cache
def _dummy_hash() -> str:
    return hash_password("bf-manager-timing-dummy")


def verify_password_timing_safe(plain: str, hashed: str | None) -> bool:
    """账号不存在或没设密码时，也拿一个假哈希做一次同等成本的比对再返回 False，
    免得别人凭登录接口的响应时间判断某个邮箱 / 用户名是否注册过。"""
    if not hashed:
        verify_password(plain or "-", _dummy_hash())
        return False
    return verify_password(plain, hashed)
