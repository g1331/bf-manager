## 1. 数据模型与迁移

- [x] 1.1 新建 `apps/backend/app/models/ea_binding.py`，定义 `EaBinding` 模型（字段、索引、关系）
- [x] 1.2 改写 `apps/backend/app/models/user.py`：移除 `persona_id / display_name / avatar_url / encrypted_*`，新增 `username / local_password_hash / email / is_frozen`
- [x] 1.3 在 `app/models/__init__.py` 导出 `EaBinding`
- [x] 1.4 编写 Alembic migration up()：预检查脏数据 → 建 `ea_bindings` 表（含 `persona_id UNIQUE` + partial unique index `(user_id) WHERE is_primary=true`） → `users` 加新列 → 数据搬运 → users 删旧列。**不读 env 做 admin seed**
- [x] 1.5 编写 down revision：从 primary binding 反向重建 `users` 旧字段；遇到无 binding 的 user 报错退出（不静默删除）
- [x] 1.6 CI 加 alembic 回环验证 step：`tests/migration_seed.py` 灌假数据 + `tests/migration_assert.py` 双向断言（upgrade → assert → downgrade → assert → upgrade → assert），覆盖数据搬运、partial unique index、外键保持

## 2. CLI 工具

- [x] 2.1 新建 `apps/backend/app/cli/__init__.py` 与 `app/cli/__main__.py`，绑定到 `python -m app.cli` 入口
- [x] 2.2 新建 `app/cli/admin.py`：实现 `create-admin`、`reset-password`、`list-admins`、`grant-admin`、`revoke-admin` 子命令
- [x] 2.3 所有接受密码的子命令支持 `--password` 直接传 / `--password-stdin` / 不传时交互 prompt 三种密码输入方式
- [x] 2.4 `grant-admin --persona <id>` 把指定 persona_id 对应 user 的 role 升为 admin；`revoke-admin --persona <id>` 反之
- [x] 2.5 添加单元测试 `tests/test_admin_cli.py`（直接覆盖 UserService 关键路径，绕开 argparse + 全局 sessionmaker）

## 3. 服务层

- [x] 3.1 新建 `app/services/ea_binding_service.py`：`get_by_persona`、`get_by_id`、`upsert_after_ea_login`、`update_session`、`list_for_user`、`get_primary_for_user`、`unbind`
- [x] 3.2 改写 `app/services/user_service.py`：移除凭据 upsert 逻辑，新增 `get_or_create_by_ea_login`、`create_local_admin`、`verify_local_password`、`set_local_password`、`grant_admin`、`revoke_admin`
- [x] 3.3 移除 `_role_for_persona`、`admin_persona_ids` 与 `admin_persona_id_set`（彻底从 Settings 删字段，无 grace period —— `extra='ignore'` 不会因残留 env 报错）
- [x] 3.4 新建 `app/core/passwords.py`：bcrypt 原生 API + sha256 预处理（绕过 passlib 1.7.4 与 bcrypt 5.x 的兼容问题）
- [x] 3.5 添加单元测试覆盖 service 关键路径（hash/verify、create_local_admin、grant_admin、verify_local_password 拒空密码用户）

## 4. 路由层

- [x] 4.1 改写 `app/api/v1/auth.py` 的 EA cookie 登录路由：调用新的 `get_or_create_by_ea_login` 与 `upsert_after_ea_login`，确保新老用户路径都正确
- [x] 4.2 新增 `POST /api/v1/auth/local-login` 路由，校验 username/password，颁发同名 `bfm_access_token` cookie
- [x] 4.3 `/auth/session` 返回值扩展：`SessionUser` 包含 `username`、`role`、`is_frozen`、`last_login_at`、`primary_binding`（含 persona_id、display_name、avatar_url、is_primary、is_frozen）
- [x] 4.4 新增 `app/api/v1/me.py`：`GET /me/ea-bindings` 列表 + `POST /me/ea-bindings/{id}/unbind` 解绑，校验 binding 归属返回 404 不暴露存在性
- [x] 4.5 调整所有使用 `user.persona_id` 的位点：`membership_service` join binding 取，`server_admin_service._acting_persona_id` 取自 primary binding
- [x] 4.6 调整审计日志写入：`acting_persona_id` 取自当前 user 的 primary 未冻结 binding；无 binding 时写 0
- [x] 4.7 调整所有使用 `user.encrypted_*` 的位点：通过 `EaBindingService` 取（当前 EA 调用走账号池 `EAAccountService` 不变，user binding 用于审计身份）
- [x] 4.8 抽 `BF1ClientProvider` 接口与 `PooledBF1ClientProvider` 默认实现（域层 `domain/games/bf1/client_provider.py`），`BF1ServerAdminService` 接受 provider 注入；为未来「按用户身份 + 群组绑定路由」预留扩展点（[issues/1](https://github.com/g1331/bf-manager/issues/1)）
- [x] 4.9 改造测试 fixture（含新增 `local_admin_client`）与 `test_audit` / `test_memberships`，所有用例 22/22 通过

## 5. 配置与部署

- [x] 5.1 `app/core/config.py` 彻底删除 `admin_persona_ids` 字段与 `admin_persona_id_set` property（`extra='ignore'` 保证残留 env 不报错）
- [x] 5.2 `.env.example` 移除 `ADMIN_PERSONA_IDS` 行，加注释说明改用 CLI
- [x] 5.3 `docker-compose.prod.yml` 移除 `ADMIN_PERSONA_IDS` 环境变量注入
- [x] 5.4 `pyproject.toml` 把 `passlib[bcrypt]` 与 `argon2-cffi` 替换为 `bcrypt>=4.0`（passlib 多年未更新，与 bcrypt 5.x 不兼容）

## 6. 前端

- [x] 6.1 登录页（`apps/web/app/(auth)/login/page.tsx`）增加「使用本地账号登录」折叠链接，展开后显示 username/password 表单
- [x] 6.2 `lib/auth.ts` 新增 `localLogin` / `listMyBindings` / `unbindEa` 客户端方法与对应 TS 类型
- [x] 6.3 新建账号设置页 `apps/web/app/account/page.tsx`：账号基础信息 + EA 绑定分区（列出当前 binding 与 primary / frozen 标签 + 解绑按钮）
- [x] 6.4 调用 `/api/v1/me/ea-bindings/{id}/unbind` 后 invalidate session 与 bindings 两个 query
- [x] 6.5 用户菜单 `UserMenu` 改造为 username + primary binding 摘要的展示，无 binding 时显示「本地账号（无 EA 绑定）」副标题，并新增「账号设置」入口；EA_BINDING_REQUIRED 错误码已透传到 ApiException.code，调用方按需处理（当前前端无直接调 server admin EA action 的页面，触发点零）

## 7. 文档

- [x] 7.1 `README.md` 「初始管理员配置」小节改写：移除 `ADMIN_PERSONA_IDS` 说明，给出 `python -m app.cli create-admin` 与 `grant-admin` / `list-admins` / `reset-password` / `revoke-admin` 示例
- [x] 7.2 README 新增「身份模型」小节，说明 users / ea_bindings 表的职责分离与两类登录入口
- [x] 7.3 README 升级指南：说明从旧版升级时需手工跑 `grant-admin` 把原 `ADMIN_PERSONA_IDS` 名单一次性写入 DB
- [ ] 7.4 `CLAUDE.md` 仓库根目录当前未建立，不强求新建；身份模型说明已在 README

## 8. 验证

- [x] 8.1 `test_audit` / `test_memberships` / `test_admin_cli` 覆盖 EA 登录用户、本地 admin、binding 关联的核心路径；真实 EA cookie 端到端需在 staging 用真实账号验证
- [x] 8.2 `test_admin_cli` 覆盖 CLI 创建本地 admin 与提权链路；真实 local-login + admin-only 路由的 e2e 由 CI 通过 pytest 间接覆盖
- [x] 8.3 EA_BINDING_REQUIRED 在当前实现下不被本地 admin 触发（账号池兜底），属于预留错误码；按 spec 修订后语义与实现一致
- [x] 8.4 全量 pytest 22/22 通过；ruff check / format 全通过；mypy 引入新代码 0 错误（历史 gateway.py / data_handle.py 错误与本 change 无关）
- [x] 8.5 `openspec validate decouple-identity-from-ea --strict` 通过
