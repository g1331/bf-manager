"""通用 EA Gateway 客户端基类（占位骨架）

未来当第二款游戏（BFV / BF2042）接入时，从 BF1GatewayClient 中抽取共享的
JSON-RPC 调用骨架、headers 构造、错误码处理、session 自动刷新逻辑到本类。
当前 MVP 阶段只有 BF1 一款游戏，强行抽象会增加无意义中间层。
"""

from __future__ import annotations
