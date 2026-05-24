"""EA 身份层（占位骨架）

未来从 BF1GatewayClient 抽出与游戏无关的：
- remid/sid → access_token 换取
- access_token → authcode 换取
- session 自动刷新（auto_login）

这些逻辑虽然实现在 BF1 客户端里，但接口本身与游戏无关，BFV / BF2042 接入时
可以直接复用。
"""

from __future__ import annotations
