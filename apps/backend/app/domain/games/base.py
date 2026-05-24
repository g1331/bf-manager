"""GameProfile 抽象：每款游戏的不变元数据"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class BlazeEndpoint(BaseModel):
    """Blaze 服务端点"""

    host: str
    port: int
    service_name: str  # e.g. "bf1-pc-prod"


@runtime_checkable
class GameProfile(Protocol):
    """游戏元数据 Protocol。

    用 Protocol + class-level attributes 风格，不强制继承 ABC，
    每个游戏 profile 用普通类声明常量即可。
    """

    game_id: str  # 'bf1' / 'bfv' / 'bf2042'
    display_name: str  # 'Battlefield 1'
    db_id: str  # X-DbId 请求头值
    hosting_game_id: str  # X-HostingGameId 请求头值
    client_version: str  # X-ClientVersion 请求头值
    code_cl: str
    data_cl: str
    save_game_version: str
    blaze_endpoints: list[BlazeEndpoint]
    supports_rsp_management: bool
    supports_vban: bool
    theme_token: str
