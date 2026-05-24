## 1. 数据模型与迁移

- [ ] 1.1 新建 `apps/backend/app/models/ea_binding.py`，定义 `EaBinding` 模型（字段、索引、关系）
- [ ] 1.2 改写 `apps/backend/app/models/user.py`：移除 `persona_id / display_name / avatar_url / encrypted_*`，新增 `username / local_password_hash / email / is_frozen`
- [ ] 1.3 在 `app/models/__init__.py` 导出 `EaBinding`
- [ ] 1.4 编写 Alembic migration：建 `ea_bindings` 表 + `users` 表字段增删 + 数据搬运 + admin 名单 seed
- [ ] 1.5 编写 down revision：从 `ea_bindings` 反向重建 `users` 旧字段
- [ ] 1.6 在 staging 环境跑 up + down 双向验证，确认零数据损失

## 2. CLI 工具

- [ ] 2.1 新建 `apps/backend/app/cli/__init__.py` 与 `app/cli/__main__.py`，绑定到 `python -m app.cli` 入口
- [ ] 2.2 新建 `app/cli/admin.py`：实现 `create-admin`、`reset-password`、`list-admins` 三个子命令
- [ ] 2.3 `create-admin` 支持 `--password` 直接传 / `--password-stdin` / 不传时交互 prompt 三种密码输入方式
- [ ] 2.4 添加单元测试 `tests/cli/test_admin_cli.py`

## 3. 服务层

- [ ] 3.1 新建 `app/services/ea_binding_service.py`：`get_by_persona`、`upsert_after_ea_login`、`freeze`、`unfreeze`、`list_for_user`、`get_primary_for_user`
- [ ] 3.2 改写 `app/services/user_service.py`：移除凭据 upsert 逻辑，新增 `get_or_create_by_ea_login`、`create_local_admin`、`verify_local_password`、`set_local_password`
- [ ] 3.3 移除 `_role_for_persona` 与所有对 `settings.admin_persona_id_set` 的引用
- [ ] 3.4 新建 `app/core/passwords.py`：bcrypt 哈希与校验封装
- [ ] 3.5 添加单元测试覆盖上述 service 的关键路径

## 4. 路由层

- [ ] 4.1 改写 `app/api/v1/auth.py` 的 EA cookie 登录路由：调用新的 `get_or_create_by_ea_login` 与 `upsert_after_ea_login`，确保新老用户路径都正确
- [ ] 4.2 新增 `POST /api/v1/auth/local-login` 路由，校验 username/password，颁发同名 `bfm_access_token` cookie
- [ ] 4.3 新增 `GET /api/v1/auth/me` 返回值扩展：包含 `username`、`role`、`primary_binding`（含 persona_id、display_name、is_frozen）
- [ ] 4.4 新增 `POST /api/v1/me/ea-bindings/{id}/unbind` 路由：用户解绑指定 binding
- [ ] 4.5 调整所有使用 `user.persona_id` 的位点（grep `user.persona_id` 后逐一改造）：改为通过 binding 取
- [ ] 4.6 调整审计日志写入：`acting_persona_id` 取自当前 binding；本地 admin 无 binding 时写 0
- [ ] 4.7 调整所有使用 `user.encrypted_*` 的位点：改为通过 binding 取
- [ ] 4.8 添加路由层集成测试

## 5. 配置与部署

- [ ] 5.1 `app/core/config.py` 中标记 `admin_persona_ids` 为 deprecated（保留字段但代码不再读取）
- [ ] 5.2 `.env.example` 移除 `ADMIN_PERSONA_IDS` 行，加注释说明改用 CLI
- [ ] 5.3 `docker-compose.prod.yml` 移除 `ADMIN_PERSONA_IDS` 环境变量注入
- [ ] 5.4 在 `pyproject.toml` 显式声明 `passlib[bcrypt]` 依赖

## 6. 前端

- [ ] 6.1 登录页（`apps/web/app/login/page.tsx` 或对应路径）增加「使用本地账号登录」折叠链接，展开后显示 username/password 表单
- [ ] 6.2 调用 `/api/v1/auth/local-login` 的客户端方法
- [ ] 6.3 账号设置页新增「EA 绑定」分区：列出当前 binding（persona、display_name、is_primary、is_frozen），每条提供「解绑」按钮
- [ ] 6.4 调用 `/api/v1/me/ea-bindings/{id}/unbind` 的客户端方法
- [ ] 6.5 在需要 EA API 的页面（服务器管理操作）加入「无可用 EA binding」的友好提示与去绑定的跳转

## 7. 文档

- [ ] 7.1 `README.md` 部署章节改写：移除 `ADMIN_PERSONA_IDS` 说明，新增「初始管理员创建」小节，给出 `docker compose exec backend python -m app.cli create-admin` 示例
- [ ] 7.2 README 新增「身份模型」小节，说明 EA cookie 用户与本地 admin 的能力差异
- [ ] 7.3 `CLAUDE.md` 更新身份层的描述

## 8. 验证

- [ ] 8.1 端到端：用 EA cookie 登录新用户、解绑 EA、重新 EA 登录恢复绑定的完整流程
- [ ] 8.2 端到端：通过 CLI 创建本地 admin → local-login → 访问 admin-only 路由
- [ ] 8.3 端到端：本地 admin 访问需要 EA 的服务器操作 → 返回 `EA_BINDING_REQUIRED`
- [ ] 8.4 跑全量 pytest 与 mypy
- [ ] 8.5 `openspec validate decouple-identity-from-ea --strict` 通过
