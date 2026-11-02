"""redirector 公钥指纹监测：指纹对得上不出声，变了告警一次，取不到证书也不挡连接"""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.domain.ea.blaze_protocol import socket as socket_module
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from cryptography.x509.oid import NameOID
from loguru import logger


def _make_cert() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
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
    return cert, key


def _fingerprint(cert: x509.Certificate) -> str:
    spki = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(spki).hexdigest()


def _cert() -> tuple[bytes, str]:
    """生成一张自签证书，返回 DER 与公钥指纹"""
    cert, _ = _make_cert()
    return cert.public_bytes(Encoding.DER), _fingerprint(cert)


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
    monkeypatch.setattr(socket_module, "_redirector_cert_unavailable_reported", False)
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


def test_missing_cert_warns_once_without_raising(warnings: list[str]) -> None:
    socket_module.check_redirector_key(_response(None))
    socket_module.check_redirector_key(httpx.Response(200))
    assert len(warnings) == 1
    assert "监测本进程内失效" in warnings[0]


class _BrokenFieldsCert:
    """公钥能取，主体 / 有效期读取时抛错（真实遇到过 notAfter 为 0 年的证书）"""

    def __init__(self, cert: x509.Certificate) -> None:
        self._cert = cert

    def public_key(self) -> Any:
        return self._cert.public_key()

    @property
    def subject(self) -> Any:
        raise ValueError("year 0 is out of range")


def test_broken_cert_fields_still_warn_once(
    warnings: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cert, _ = _make_cert()
    monkeypatch.setattr(socket_module, "_redirector_cert", lambda _r: _BrokenFieldsCert(cert))
    socket_module.check_redirector_key(httpx.Response(200))
    socket_module.check_redirector_key(httpx.Response(200))
    assert len(warnings) == 1
    assert _fingerprint(cert) in warnings[0]
    assert "证书字段解析失败" in warnings[0]


async def test_reads_cert_from_real_tls_response(warnings: list[str], tmp_path: Path) -> None:
    """非流式请求返回后仍能从连接上取到证书：依赖升级若让这里失效，用例会失败"""
    cert, key = _make_cert()
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(Encoding.PEM))
    key_file.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    server_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server_ctx.load_cert_chain(cert_file, key_file)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_ctx)
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(f"https://127.0.0.1:{port}/", content=b"x")
        socket_module.check_redirector_key(response)
    finally:
        server.close()
        await server.wait_closed()
    assert len(warnings) == 1
    assert _fingerprint(cert) in warnings[0]
