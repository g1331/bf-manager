"""请求编号：每个 HTTP 请求生成一个短编号，贯穿日志、响应头与错误响应体。

用户反馈问题时报出错误编号，即可在日志里按 ``request_id=`` 定位到对应请求。
编号由服务端生成，不沿用客户端传入的 ``X-Request-ID``，避免被伪造成与别人的请求混淆。
"""

from __future__ import annotations

import uuid

from fastapi import Request
from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


class RequestIdMiddleware:
    """纯 ASGI 中间件：编号写进 ``scope["state"]``，异常处理器构造的 Request 也能读到。

    未处理异常的 500 响应由最外层的 ServerErrorMiddleware 直接发出，不经过这里的
    响应头注入，所以错误体里也带一份 ``request_id``（见 main.py 的异常处理器）。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        with logger.contextualize(request_id=request_id):
            await self.app(scope, receive, send_with_header)
