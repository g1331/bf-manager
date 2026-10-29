"""客户端 IP 的统一取值入口。

生产链路是 Cloudflare → openresty → uvicorn：openresty 按 Cloudflare IP 段还原真实地址后，
用单值覆盖 X-Forwarded-For，uvicorn 的 proxy-headers 再把它写进 ``request.client``。
限流、审计、访问统计都从这里取，以后换取值方式只改这一处。
"""

from __future__ import annotations

from fastapi import Request


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
