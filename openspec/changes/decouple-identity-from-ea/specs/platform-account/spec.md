## ADDED Requirements

### Requirement: User 实体作为独立身份层

The `users` table MUST serve as the sole identity layer and MUST NOT contain any EA persona identifiers or EA credential fields.

平台账号必须由 `users` 表承载，且该表只承担身份层职责——不存储任何 EA persona 标识或 EA 凭据。一个 user 是 bf-manager 系统内的稳定身份单元，其生命周期独立于任何外部 EA 账号的可用性。

`users` 表必须包含且仅包含以下身份相关字段：`id`、`username`（全局唯一）、`local_password_hash`（可空）、`email`（可空）、`role`（值域 `admin / user`）、`is_active`、`is_frozen`、`last_login_at`、`created_at`、`updated_at`。

#### Scenario: 用户存在性与 EA 可用性解耦

- **WHEN** 一个 user 的所有 ea_bindings 都被冻结或删除
- **THEN** 该 user 仍然能够通过其他可用方式登录，`users.is_active` 不被自动置 false，权限（含 `role` 与 `server_memberships`）完整保留

#### Scenario: username 唯一性

- **WHEN** 创建一个新 user 时指定的 username 已被占用
- **THEN** 创建操作失败并返回明确错误，不允许两个 user 共享同一 username

### Requirement: 双登录入口

The system MUST expose exactly two login entry points, each producing JWTs with identical structure so downstream auth middleware remains entry-point agnostic.

系统必须支持两种登录入口，分别对应两类身份来源。

第一种是 EA cookie 登录（`POST /api/v1/auth/login`），面向所有 BF 玩家用户。该路径根据 EA cookie 校验得到 persona_id，通过 `ea_bindings.persona_id` 查找归属 user；找不到时自动创建 user（username 自动生成为 `persona_<persona_id>`，role 为 `user`）并写入首条 binding。

第二种是本地账号登录（`POST /api/v1/auth/local-login`），面向通过 CLI 创建的本地管理员。该路径凭 `username + password` 校验通过 `users.local_password_hash`，颁发与 EA 登录同名的 `bfm_access_token` cookie。

两条入口颁发的 JWT 结构必须完全一致（`sub = user.id`），下游鉴权中间件不区分入口来源。

#### Scenario: EA 登录命中已存在 binding

- **WHEN** 一个已登录过的 persona 再次走 EA cookie 登录
- **THEN** 系统通过 `ea_bindings.persona_id` 定位到原 user，更新该 binding 的加密凭据与 `last_verified_at`，颁发 JWT(sub=user.id)，不创建新 user

#### Scenario: EA 登录首次开户

- **WHEN** 一个全新 persona 走 EA cookie 登录，且 `ea_bindings` 表无该 persona 记录
- **THEN** 系统创建一个 user（`username='persona_<persona_id>'`，`role='user'`，`local_password_hash=NULL`），并插入一条 `is_primary=true` 的 binding，颁发 JWT(sub=user.id)

#### Scenario: 本地登录走 username/password

- **WHEN** 客户端 POST /api/v1/auth/local-login 携带 username 与 password
- **THEN** 系统查找 username 对应 user，使用 bcrypt 校验 password 与 `local_password_hash`，校验通过时颁发 JWT(sub=user.id) cookie；username 不存在或密码错误时返回 401，错误信息不区分两种失败

#### Scenario: 无密码用户不能走本地登录

- **WHEN** EA cookie 自动创建的 user（`local_password_hash IS NULL`）尝试走 local-login
- **THEN** 系统返回 401，不应在错误中暴露「该用户存在但无密码」的事实

### Requirement: CLI 管理本地账号

The backend MUST provide a `python -m app.cli` entry point with admin management subcommands, and all password-accepting commands MUST support three input modes (flag, stdin, interactive prompt).

后端必须提供 `python -m app.cli` 命令入口，至少包含以下子命令：

`create-admin --username <name> --password <pw> [--email <addr>]` 创建一个 `role='admin'`、`local_password_hash` 非空、无 ea_bindings 的本地管理员。

`reset-password --username <name> --password <new_pw>` 重置指定 user 的本地密码。

`list-admins` 列出所有 `role='admin'` 的 user，含 username、是否有 binding、最后登录时间。

所有接受密码的子命令必须支持三种密码输入方式：`--password <pw>` 直接传参（最不安全，便于脚本化）、`--password-stdin` 从标准输入读取（推荐脚本场景）、未提供密码参数时通过 `getpass.getpass()` 交互式 prompt（推荐人工场景）。

#### Scenario: 首次部署创建初始 admin

- **WHEN** 部署者在 docker 容器内执行 `python -m app.cli create-admin --username root` 并在 prompt 中输入密码
- **THEN** 系统创建 username='root'、role='admin' 的 user，`local_password_hash` 为输入密码的 bcrypt 哈希，无任何 ea_bindings；该 user 立即可通过 local-login 入口登录

#### Scenario: 同名 username 冲突

- **WHEN** 执行 `create-admin --username root`，而 username='root' 的 user 已存在
- **THEN** CLI 报错退出（非零退出码），不修改任何现有数据

#### Scenario: 密码不进入 shell 历史

- **WHEN** 部署者执行 `create-admin --username root`（不带 --password）
- **THEN** CLI 进入交互式 prompt，密码输入不回显，命令完整记录在 shell history 中不包含密码明文

### Requirement: role 字段语义与写入路径

`users.role` MUST remain a single-value string with domain `admin | user`, and the backend MUST NOT read the `ADMIN_PERSONA_IDS` environment variable to compute role at runtime.

`users.role` 字段保持单值 string，值域 `admin / user`。该字段的写入路径必须严格限制：

- CLI `create-admin` 在创建时显式设置为 `admin`。
- EA cookie 登录创建新 user 时一律设置为 `user`。
- EA cookie 登录命中已存在 user 时不修改 `role` 字段。
- 本 change 范围内不提供 Web 路由修改 `role`（admin 管理 UI 留给后续 change）。

环境变量 `ADMIN_PERSONA_IDS` 必须不再被后端代码读取以决定 `role`。

#### Scenario: EA 登录不覆盖已有 role

- **WHEN** 一个 `role='admin'` 的 user 通过 EA cookie 登录
- **THEN** 系统更新 binding 凭据与 `last_login_at`，但 `users.role` 字段保持 `admin` 不变

#### Scenario: 环境变量不再影响 role

- **WHEN** `ADMIN_PERSONA_IDS=12345` 环境变量存在，且 persona_id=12345 走 EA cookie 登录
- **THEN** 该 user 的 `role` 由 DB 当前值决定，与环境变量完全无关
