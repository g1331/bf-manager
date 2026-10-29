"""开放 API 文档：只含公开查询接口的 OpenAPI，生产环境也对外提供。

完整的 /api/v1/openapi.json 在生产关闭（含管理接口）；这里从完整文档里挑出 BF1 的只读查询，
再删掉没被引用的 schema，给拿 API Key 的第三方生成类型、看字段用。
"""

from __future__ import annotations

import copy
import json
from typing import Any

from fastapi import APIRouter, Request

from app.api.rate_limit import API_KEY_HEADER, rate_limit

router = APIRouter()

_PUBLIC_PREFIX = "/api/v1/bf1/"
# 服管和卡行动要服主身份，不属于开放查询
_EXCLUDED_SEGMENTS = ("/server-admin", "/card")

_cache: dict[str, Any] | None = None


def _refs(node: Any) -> set[str]:
    text = json.dumps(node)
    found = set()
    marker = '"#/components/schemas/'
    start = text.find(marker)
    while start != -1:
        end = text.find('"', start + len(marker))
        found.add(text[start + len(marker) : end])
        start = text.find(marker, end)
    return found


def build_public_openapi(full: dict[str, Any]) -> dict[str, Any]:
    paths = {
        path: {"get": ops["get"]}
        for path, ops in full.get("paths", {}).items()
        if path.startswith(_PUBLIC_PREFIX)
        and not any(seg in path for seg in _EXCLUDED_SEGMENTS)
        and "get" in ops
    }
    paths = copy.deepcopy(paths)
    for ops in paths.values():
        ops["get"]["security"] = [{"ApiKey": []}, {}]

    # 从路径出发收集被引用的 schema，连带它们引用的 schema
    schemas = full.get("components", {}).get("schemas", {})
    keep: set[str] = set()
    pending = _refs(paths)
    while pending:
        name = pending.pop()
        if name in keep or name not in schemas:
            continue
        keep.add(name)
        pending |= _refs(schemas[name])

    return {
        "openapi": full.get("openapi", "3.1.0"),
        "info": {
            "title": "BF Manager 开放 API",
            "version": full.get("info", {}).get("version", ""),
            "description": (
                f"在 `{API_KEY_HEADER}` 请求头里带上在「我的主页 → 开放 API」申请的 key。"
                "不带 key 也能调用，但按 IP 计数、额度最低。"
            ),
        },
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": {
            "schemas": {name: schemas[name] for name in sorted(keep)},
            "securitySchemes": {
                "ApiKey": {"type": "apiKey", "in": "header", "name": API_KEY_HEADER}
            },
        },
    }


@router.get("/openapi.public.json", dependencies=[rate_limit("read")], include_in_schema=False)
async def public_openapi(request: Request) -> dict[str, Any]:
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = build_public_openapi(request.app.openapi())
    return _cache
