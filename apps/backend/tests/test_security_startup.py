"""生产环境启动自检：密钥缺失或不合格时拒绝启动"""

from __future__ import annotations

import base64
from collections.abc import Callable

import pytest
from app.core import security
from app.core.config import Settings

_GOOD_JWT = "a" * 64
_GOOD_EA_KEY = base64.b64encode(b"k" * 32).decode()


@pytest.fixture
def use_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """把 security 模块看到的配置换成指定值，并清掉缓存的加密器"""

    def apply(**overrides: str) -> None:
        settings = Settings.model_validate(overrides)
        monkeypatch.setattr(security, "get_settings", lambda: settings)
        monkeypatch.setattr(security, "_cipher", None)

    return apply


def test_non_production_skips_check(use_settings: Callable[..., None]) -> None:
    use_settings(environment="development", jwt_secret_key="", ea_cred_encryption_key="")
    security.check_production_secrets()


@pytest.mark.parametrize("jwt_key", ["", "short-secret"])
def test_production_rejects_weak_jwt_secret(
    use_settings: Callable[..., None], jwt_key: str
) -> None:
    use_settings(
        environment="production", jwt_secret_key=jwt_key, ea_cred_encryption_key=_GOOD_EA_KEY
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        security.check_production_secrets()


@pytest.mark.parametrize("ea_key", ["", "not-base64!", base64.b64encode(b"x" * 16).decode()])
def test_production_rejects_bad_ea_key(use_settings: Callable[..., None], ea_key: str) -> None:
    use_settings(environment="production", jwt_secret_key=_GOOD_JWT, ea_cred_encryption_key=ea_key)
    with pytest.raises(ValueError, match="EA_CRED_ENCRYPTION_KEY"):
        security.check_production_secrets()


def test_production_accepts_valid_secrets(use_settings: Callable[..., None]) -> None:
    use_settings(
        environment="production", jwt_secret_key=_GOOD_JWT, ea_cred_encryption_key=_GOOD_EA_KEY
    )
    security.check_production_secrets()
