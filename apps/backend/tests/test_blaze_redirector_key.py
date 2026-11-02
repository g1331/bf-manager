"""redirector 公钥指纹监测：指纹对得上不出声，变了告警一次，取不到证书也不挡连接"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from app.domain.ea.blaze_protocol import socket as socket_module
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID
from loguru import logger


def _cert() -> tuple[bytes, str]:
    """生成一张自签证书，返回 DER 与公钥指纹"""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "winter15.gosredirector.ea.com")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    spki = key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return cert.public_bytes(Encoding.DER), hashlib.sha256(spki).hexdigest()


class _SSLObject:
    def __init__(self, der: bytes) -> None:
        self.der = der

    def getpeercert(self, binary_form: bool = False) -> bytes:
        return self.der


class _Stream:
    def __init__(self, ssl_object: Any) -> None:
        self.ssl_object = ssl_object

    def get_extra_info(self, info: str) -> Any:
        return self.ssl_object if info == "ssl_object" else None


def _response(ssl_object: Any) -> httpx.Response:
    return httpx.Response(200, extensions={"network_stream": _Stream(ssl_object)})


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    monkeypatch.setattr(socket_module, "_reported_redirector_keys", set())
    messages: list[str] = []
    handler_id = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    yield messages
    logger.remove(handler_id)


def test_known_key_is_silent(warnings: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    der, fingerprint = _cert()
    monkeypatch.setattr(socket_module, "REDIRECTOR_SPKI_SHA256", fingerprint)
    socket_module.check_redirector_key(_response(_SSLObject(der)))
    assert warnings == []


def test_changed_key_warns_once(warnings: list[str]) -> None:
    der, fingerprint = _cert()
    socket_module.check_redirector_key(_response(_SSLObject(der)))
    socket_module.check_redirector_key(_response(_SSLObject(der)))
    assert len(warnings) == 1
    assert fingerprint in warnings[0]
    assert "winter15.gosredirector.ea.com" in warnings[0]


def test_missing_cert_does_not_raise(warnings: list[str]) -> None:
    socket_module.check_redirector_key(_response(None))
    socket_module.check_redirector_key(httpx.Response(200))
    assert warnings == []
