"""安全相关：AES-256-GCM 加密 + JWT 签发与验证"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.core.config import get_settings

# ===== EA 凭据加密 =====


class CredentialCipher:
    """AES-256-GCM 凭据加密器"""

    def __init__(self, key_b64: str) -> None:
        if not key_b64:
            raise ValueError("EA_CRED_ENCRYPTION_KEY is not configured")
        try:
            key = base64.b64decode(key_b64)
        except Exception as e:
            raise ValueError(f"EA_CRED_ENCRYPTION_KEY is not valid base64: {e}") from e
        if len(key) != 32:
            raise ValueError(f"EA_CRED_ENCRYPTION_KEY must decode to 32 bytes (got {len(key)})")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        """加密返回 base64(nonce || ciphertext)"""
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        data = base64.b64decode(ciphertext_b64)
        nonce, ct = data[:12], data[12:]
        return self._aesgcm.decrypt(nonce, ct, None).decode("utf-8")


_cipher: CredentialCipher | None = None


def get_cipher() -> CredentialCipher:
    """惰性单例：避免启动时无 key 直接崩"""
    global _cipher  # noqa: PLW0603
    if _cipher is None:
        _cipher = CredentialCipher(get_settings().ea_cred_encryption_key)
    return _cipher


# ===== JWT =====


def create_access_token(
    subject: str | int,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT，失败抛 JWTError"""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


__all__ = [
    "CredentialCipher",
    "JWTError",
    "create_access_token",
    "decode_access_token",
    "get_cipher",
]
