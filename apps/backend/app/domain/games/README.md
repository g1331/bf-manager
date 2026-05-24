# 游戏接入指南

每个支持的游戏在 `domain/games/<game_id>/` 下实现，与共享的 `domain/ea/` 层组合使用。

## 接入新游戏的步骤

1. 创建 `domain/games/<new_game>/` 目录，复制 `bf1/` 结构作为模板
2. 编写 `profile.py`，填入新游戏的代号、请求头版本、Blaze 端点，并在模块导入时通过 `GameRegistry.register(...)` 注册
3. 编写 `gateway.py`，继承共享 `domain/ea/gateway_base.BaseGatewayClient`，实现该游戏特定方法
4. 编写 `stats_schema.py` 和 `server_settings.py`，定义字段映射
5. 在 `models/<new_game>/` 添加游戏特定表，写 Alembic migration
6. 在 `services/<new_game>/` 实现业务逻辑
7. 在 `api/v1/games/<new_game>/` 添加路由
8. 前端 `app/(public)/[game]/` 与 `(dashboard)/[game]/` 动态段自动覆盖。只需添加 `components/games/<new_game>/` 特定组件和 `styles/themes/<new_game>.css`
9. 前端 `lib/game-registry.ts` 添加游戏元数据条目

## 抽象边界原则

只对**签名与语义真正一致**的能力共享接口：persona 查询、登录、Blaze 协议编解码。

**业务参数差异大的能力各游戏独立实现**：服管操作（踢人 / VBAN / 换图）、战绩字段、服务器设置面板。强行抽象会增加无意义中间层并提高未来维护成本。

## 引擎代号速查

| 游戏 | 内部代号 | X-DbId |
|---|---|---|
| Battlefield 1 | tunguska | `Tunguska.Shipping2PC.Win32` |
| Battlefield V | casablanca | `Casablanca.Shipping2PC.Win32` |
| Battlefield 2042 | kingston | `Kingston.Shipping2PC.Win32` |
| Battlefield 4 | warsaw | `Warsaw.Shipping2PC.Win32` |
| Battlefield Hardline | omaha | `Omaha.Shipping2PC.Win32` |
