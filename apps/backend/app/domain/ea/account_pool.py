"""EA 账号池（用于代查询）

服务层接口骨架。BF1 阶段调用方负责：
1. 从数据库读取一个可用的 EAAccount
2. 用其凭据构造 BF1GatewayClient（注入持久化回调）
3. 调用结束后通过回调更新 sid / session
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EACredentials:
    """从 EAAccount 表解密后的凭据"""

    persona_id: int
    display_name: str | None
    remid: str
    sid: str
    session: str | None = None
    access_token: str | None = None
