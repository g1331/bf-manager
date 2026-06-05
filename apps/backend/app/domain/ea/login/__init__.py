"""EA 邮箱密码 + 2FA 登录链路。

模块定位：在 bf-manager 内自实现 EA accounts.ea.com 的多步登录流程，取得 remid/sid
后立刻交由现有 `BF1GatewayClient.login()` 走完 BF1 sparta 链路，再由 service 层
加密回填到 `ea_bindings` 或 `ea_accounts`。

子模块划分：
- ``form_parser``     纯函数：lxml HTML 解析与表单字段提取
- ``login_engine``    有限状态机：驱动 EA 多步 POST 链路，拿到 remid/sid
- ``task_manager``    任务生命周期：内存存敏感数据，Redis 存版本号与状态元数据
- ``exceptions``      EA 链路自身的业务异常（区别于 api/errors.py 的 HTTP 错误）
- ``schemas``         Pydantic 入参出参模型

敏感数据约束：邮箱、密码、2FA 验证码、remid、sid、access_token 仅在内存中存在；
日志只记录 ``step / http_status / duration_ms / set_cookie_keys`` 等元数据。
"""
