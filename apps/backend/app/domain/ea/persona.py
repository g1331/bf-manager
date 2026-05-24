"""EA Persona 查询（占位骨架）

未来从 BF1GatewayClient 抽出与游戏无关的：
- getPersonasByName（按昵称查 persona_id）
- getPersonasByIds（批量查 persona 详情）
- setLocale（语言偏好）

这些 method 在 EA Gateway 上对所有 BF 系列游戏都返回同样格式的结果。
"""

from __future__ import annotations
