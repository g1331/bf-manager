"""BF1 GameProfile 实例"""

from __future__ import annotations

from typing import ClassVar

from app.domain.games.base import BlazeEndpoint


class BF1Profile:
    game_id: ClassVar[str] = "bf1"
    display_name: ClassVar[str] = "Battlefield 1"

    # Gateway 请求头
    db_id: ClassVar[str] = "Tunguska.Shipping2PC.Win32"
    hosting_game_id: ClassVar[str] = "tunguska"
    client_version: ClassVar[str] = "release-bf1-lsu35_26385_ad7bf56a_tunguska_all_prod"

    # 客户端版本字段
    code_cl: ClassVar[str] = "3779779"
    data_cl: ClassVar[str] = "3779779"
    save_game_version: ClassVar[str] = "26"

    blaze_endpoints: ClassVar[list[BlazeEndpoint]] = [
        BlazeEndpoint(
            host="bfgame.bf1.production.kvkprod.net",
            port=10539,
            service_name="bf1-pc-prod",
        ),
    ]

    supports_rsp_management: ClassVar[bool] = True
    supports_vban: ClassVar[bool] = True
    theme_token: ClassVar[str] = "bf1"
