## Why

当前 bf-manager 的身份层与 EA 凭据层是同一张 `users` 表的同一行：`persona_id` 既作为登录主键依据，又作为 EA API 调用的执行身份。这种压平带来四个具体不适：

1. **平台维护者必须拥有 BF 账号**。维护这套部署的运维或协作者，可能并不打 BF，却因为 Web 唯一入口是 EA cookie 登录，被迫去注册一个 EA 账号才能进后台。
2. **EA 账号封禁导致权限全失**。EA 误封并不罕见。一旦 persona 不可用，与之绑定的服管权限、平台 admin 身份、跨服务器审计身份会一并蒸发。
3. **同一玩家多 EA 账号无法归一**。主号与小号被识别为两个完全独立的 bf-manager 用户，权限不能互通。
4. **admin 名单只能通过 env 维护**。`ADMIN_PERSONA_IDS` 改一次就要重启容器；admin 之间无法在 UI 互相授权；admin 名单变更没有审计轨迹。

对比同生态的 BFBAN（`BFBAN/bfban-website`），其设计早已把这两层解开：身份用 `username + password`，EA 用 `originPersonaId / originEmail` 作为绑定属性，并支持换绑、冻结、多角色（`privilege` JSON 数组）。bf-manager 可以借鉴这套分层，同时保留 EA cookie 作为主流登录入口以兼容现有用户体验。

## What Changes

将 `users` 表拆为两个职责清晰的实体：

- **`users`** 表只承担身份层职责：`id`、`username`、`local_password_hash`、`email`、`role`、`is_active`、`is_frozen`。`persona_id` 与所有 `encrypted_*` 凭据字段从此表移除。
- **`ea_bindings`** 表承担 EA 凭据层职责：`user_id`（FK）、`persona_id`（全局唯一）、`display_name`、`avatar_url`、`encrypted_remid / sid / session / access_token`、`is_primary`、`is_frozen`、`last_verified_at`。一个 user 可以拥有 N 条 ea_bindings，其中至多一条 `is_primary=true`。

登录入口拆分为两条：

- **Web 主入口 `POST /api/v1/auth/ea-login`**：保留现有 EA cookie 登录流程。首次登录时：若该 persona 已存在 `ea_bindings` 记录，定位到对应 user 完成登录；若不存在，自动创建一个 user（`username` 自动生成为 `persona_<id>`），并写入首条 `ea_bindings` 标记为 primary。
- **二级入口 `POST /api/v1/auth/local-login`**：仅供 CLI 创建的本地 admin 使用。`username + password` 校验通过即颁发同名 `bfm_access_token` cookie。前端登录页提供折叠链接「使用本地账号登录」进入。

引入 CLI 子命令 `python -m app.cli create-admin --username <name> --password <pw>`，用于首次部署时创建无 EA 绑定的初始管理员。

引入 `python -m app.cli reset-password --username <name>` 用于忘密重置。

`User.role` 仍保留为单值 string（`admin / user`），不切换为 JSON 数组。服务器级角色仍由 `server_memberships` 表承担。`role` 字段的写入路径变为：本地 admin 在 CLI 创建时显式设置；其余用户登录时一律为 `user`，与 EA persona 完全无关。

`env ADMIN_PERSONA_IDS` 在升级到本版本时执行一次 Alembic data migration，把名单内的 persona 对应 user 的 `role` 设为 `admin`；之后 backend 代码不再读取该环境变量，下一个主版本可删除字段。

凭据生命周期：`ea_bindings` 新增 `is_frozen` 标志，由用户在「账号设置」手动解绑或后台检测到连续刷新失败时置 true；冻结的 binding 不参与「当前活跃 EA 操作身份」选择，但记录保留。用户失去所有可用 binding 后，账号本身不被禁用，仅在尝试执行任何需要 EA API 的操作时返回 `EA_BINDING_REQUIRED` 错误码。

「执行 EA 操作时用哪条 binding」的选择策略：默认取 `is_primary=true` 且 `is_frozen=false` 的那条；若没有合适 binding，操作直接拒绝并提示用户去绑定。多 binding 切换 UI 不在本 change 范围。

审计日志的 `acting_persona_id` 改为从「当前选中的 binding」取值，而非从 `user.persona_id` 取（该字段已不存在）。本地 admin 在不涉及 EA API 的纯平台操作中，`acting_persona_id` 写 0 表示「无 persona」。

## Capabilities

### New Capabilities

- `platform-account`: 平台账号实体——身份、登录方式、角色、激活与冻结状态、CLI 管理命令。
- `ea-binding`: EA 账号绑定实体——绑定关系、凭据加密存储、首要标记、冻结流程、操作身份选择。

### Modified Capabilities

无（本仓库 `openspec/specs/` 当前为空，此为首批 spec）。

## Impact

**数据库**：新增 `ea_bindings` 表；`users` 表移除 `persona_id`、`encrypted_*`、`avatar_url`、`display_name`，新增 `username`、`local_password_hash`、`email`、`is_frozen`。需要 Alembic data migration 把现有 users 的 EA 字段搬到 ea_bindings，并 seed admin 名单。

**后端代码**：`app/models/user.py` 拆分新增 `ea_binding.py`；`app/services/user_service.py` 大幅改写（不再 upsert 凭据，改为定位/创建 user + 写入 binding）；新增 `app/services/ea_binding_service.py`；新增 `app/services/auth_service.py` 内 `local_login` 分支；新增 `app/cli/admin.py`；`app/core/config.py` 移除 `admin_persona_ids` 与相关 property；所有读 `user.persona_id` / `user.encrypted_*` 的位点改为读 binding。

**前端代码**：登录页增加「使用本地账号登录」折叠入口；账号设置页新增「EA 绑定」分区（列出当前绑定、解绑按钮）。绑定列表的「添加绑定」交互不在本 change，留给后续 change。

**配置**：`.env.example` 与 `docker-compose.prod.yml` 移除 `ADMIN_PERSONA_IDS`；README 部署章节改写为「初始管理员通过 CLI 创建」。

**测试**：`apps/backend/tests/conftest.py` 中构造 admin 的 fixture 改为创建本地 admin；新增 `test_local_login.py`、`test_ea_binding.py`、`test_create_admin_cli.py`；现有 `test_memberships.py` 等需要调整 admin 构造方式。

**Non-Goals**：admin 管理 UI（在前端列表/添加/移除 admin、AuditLog 写入）单独立 change；多 EA binding 切换 UI 单独立 change；username+password 公开注册流程不做（本地 admin 仅 CLI 创建）。
