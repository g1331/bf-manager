"""EA 相关连接的证书校验：Blaze 只信任 GOS CA，其余 HTTPS 一律走系统 CA"""

from __future__ import annotations

import re
import ssl
from pathlib import Path

from app.domain.ea.blaze_protocol.socket import GOS_CA_FILE, blaze_ssl_context

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_blaze_context_verifies_against_gos_ca() -> None:
    ctx = blaze_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    # GOS CA 的 Basic Constraints 没标 critical，严格模式会拒掉整条链
    assert not ctx.verify_flags & ssl.VERIFY_X509_STRICT
    subjects = [dict(x[0] for x in ca["subject"]) for ca in ctx.get_ca_certs()]
    assert {"commonName": "GOS 2015 Certificate Authority"}.items() <= subjects[0].items()
    assert len(subjects) == 1


def test_gos_ca_file_is_packaged_inside_app() -> None:
    # Dockerfile 只拷 app/，CA 文件必须在包目录里
    assert GOS_CA_FILE.is_file()
    assert APP_DIR in GOS_CA_FILE.resolve().parents


def test_no_disabled_certificate_checks_in_app() -> None:
    """除 Blaze redirector（见 socket.py 的说明）外，不允许再关掉证书校验"""
    pattern = re.compile(r"CERT_NONE|ssl\s*=\s*False|verify\s*=\s*False|check_hostname\s*=\s*False")
    hits = []
    for path in APP_DIR.rglob("*.py"):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(APP_DIR)}:{no}: {line.strip()}")
    assert hits == [
        "domain/ea/blaze_protocol/socket.py:75: "
        "async with httpx.AsyncClient(verify=False) as client:"
    ]
