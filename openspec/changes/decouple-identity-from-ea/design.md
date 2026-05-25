## Context

bf-manager 的现有身份模型由两次决策塑形：

第一次是从 xiaomai-bot（QQ 机器人）迁移到 Web。xiaomai-bot 里 QQ 号是天然身份层，EA persona 通过 binding 表挂在 QQ 用户下；迁移到 Web 后失去 QQ 这一外部稳定身份源，最简化的做法是把 EA persona 直接拔成身份，于是 `users.persona_id` 既是登录依据也是凭据载体。

第二次是 MVP 阶段为了快速上线 admin 概念，引入了 `ADMIN_PERSONA_IDS` 环境变量，每次登录时把名单内的 persona 强制写为 `role='admin'`。声明式但与 DB 状态持续打架。

当前的 `users` 表实际承担了三种角色：身份（who you are）、凭据（how you act on EA）、权限（what you can do on the platform）。三者揉在同一行里，扩展任何一项都会影响另外两项。

参考实现 BFBAN（`BFBAN/bfban-website` 仓库 `backend/bfban_2.0.sql` 与 `backend/middleware/auth.js`、`backend/routes/user.js`）采用了完全相反的取舍：`users` 表的核心字段是 `username + password + privilege`，EA 通过 `origin*` 系列字段作为绑定属性，注册时强制邮箱验证证明持有 EA，登录走本地密码。这套模型证明了「Web 平台 + EA 业务」是可以解耦的，但 BFBAN 的业务场景（封禁裁定）不需要以用户身份调 EA API，凭据只作身份验真使用；bf-manager 必须持续保有可用的 EA 会话执行服管操作，对凭据生命周期管理的要求更高。

## Goals / Non-Goals

**Goals:**

- 把「身份 / 凭据 / 权限」三个职责拆到清晰的实体边界上。身份在 `users`，凭据在 `ea_bindings`，平台权限留在 `users.role`，服务器权限留在 `server_memberships`。
- 让「平台管理者无需 BF 账号」这一基础诉求成立——通过 CLI 创建的本地 admin 完全可以登录后台、管理平台用户、查审计日志，不需要任何 EA 绑定。
- 保留 EA cookie 登录作为玩家用户的主流入口，体验与现状基本一致。
- 提供 EA 账号丢失或换号场景下的优雅恢复路径：解绑旧 EA、绑新 EA，user_id 与所有权限不变。
- 把 `ADMIN_PERSONA_IDS` 这个声明式覆盖机制彻底从代码中移除，避免后续维护负担。

**Non-Goals:**

- **多 EA 切换 UI**：表结构允许一个 user 多条 binding，但前端不暴露切换器；执行 EA 操作时一律取 primary binding。后续 change 再做。
- **admin 管理后台 UI**：admin 名单的增删走数据库或下一个 change 提供的路由，本 change 不做前端管理页。
- **公开 username+password 注册**：本地账号仅由 CLI 创建。Web 注册路径完全是 EA cookie 自动开户。
- **邮箱验证流程**：本地 admin 的 email 字段仅作联系方式存储，不做验证码、不做密码找回邮件——重置走 CLI。
- **`privilege` JSON 数组**：`role` 保持单值 string，避免现阶段不必要的复杂度。
- **删除 `users.persona_id` 索引的查询能力**：所有原本通过 persona 查 user 的代码改为 join `ea_bindings`，索引建在 `ea_bindings.persona_id` 上即可。

## Decisions

### 表结构与归一化

`ea_bindings.persona_id` 设为全局 `UNIQUE`。语义是：一个真实 EA 账号在 bf-manager 实例内只能属于一个 user。这避免了「用户 A 绑定了 persona X，用户 B 也声称绑定 persona X」的冲突场景。代价是：用户换 EA 主号时，若新 persona 已经被另一个 user 占用（小概率，但例如出售 / 转手 EA 账号），必须先由占用方解绑——这种边角场景接受 CLI 介入处理。

`ea_bindings.is_primary` 在 DB 层加 partial unique index：`CREATE UNIQUE INDEX uq_ea_bindings_user_primary ON ea_bindings (user_id) WHERE is_primary = true`。本项目锁定 PostgreSQL，partial unique index 是 PG 一等公民，由 DB 兜底「一个 user 至多一条 primary binding」的不变量。service 层仍做事务内校验以返回友好错误，但最终一致性责任归 DB。

`users.local_password_hash` 允许 `NULL`：EA cookie 登录创建的 user 此字段为 NULL，他们无法走 local-login。本地 admin 此字段非 NULL，但他们也能后续绑定 EA（变成「双入口都能登录的混合账号」），不强制互斥。

`users.username` 全局 `UNIQUE`，自动生成的 EA 用户为 `persona_<persona_id>` 形态，本地 admin 由 CLI 显式指定。冲突由 CLI 提示后由部署者改名。

### 登录链路改造

EA cookie 登录的链路改为：

```
   EA cookie → 校验 → 拿到 persona_id
        │
        ▼
   SELECT * FROM ea_bindings WHERE persona_id = ?
        │
        ├── 命中: 加载 binding.user，更新 binding 凭据，颁发 JWT(sub=user.id)
        │
        └── 未命中: 创建 user (username=persona_<id>, role='user'),
                   插入 binding (is_primary=true), 颁发 JWT(sub=user.id)
```

local-login 的链路：

```
   POST /api/v1/auth/local-login { username, password }
        │
        ▼
   SELECT * FROM users WHERE username = ? AND local_password_hash IS NOT NULL
        │
        ├── verify(password, hash): 颁发 JWT(sub=user.id)
        │
        └── 失败: 401，错误信息不区分「用户不存在」与「密码错误」
```

JWT 内容不变，仍为 `sub = user.id`。鉴权中间件 `get_current_user` 不需要改造，因为它本就只查 user。

### CLI 形态

新增 `apps/backend/app/cli/__init__.py` 与 `apps/backend/app/cli/admin.py`。入口走 `python -m app.cli`，使用 typer 或 argparse 任选（仓库现有依赖含 fastapi，倾向 argparse 避免新依赖）。命令：

```
   python -m app.cli create-admin --username <name> --password <pw> [--email <addr>]
   python -m app.cli reset-password --username <name> --password <new_pw>
   python -m app.cli list-admins
```

`create-admin` 行为：创建 `users` 行，`role='admin'`，`local_password_hash` 写入 bcrypt 哈希，不创建任何 `ea_bindings`。同名 username 已存在时报错退出。

追加 `grant-admin --persona <id>` 子命令：把指定 persona_id 对应的 user（必须已存在）的 `role` 升为 admin。用于把现有 EA 用户提权为平台管理员，替代旧 `ADMIN_PERSONA_IDS` env 的诉求。

部署文档示例：

```
   docker compose exec backend python -m app.cli create-admin \
       --username root --password "$(openssl rand -base64 24)"

   docker compose exec backend python -m app.cli grant-admin --persona 12345
```

### 密码哈希算法

使用 bcrypt（`passlib[bcrypt]` 依赖）。bf-manager 现已使用 `passlib` 间接依赖（通过 python-jose），直接显式声明并启用 bcrypt schema。

### 凭据冻结的触发与解冻

`ea_bindings.is_frozen=true` 的触发条件：

- 用户在「账号设置」点击「解绑此 EA 账号」，service 层把对应 binding 的 `is_primary=false`、`is_frozen=true`，并清空 `encrypted_*` 字段（密文也不留）。
- EA cookie refresh（未来实现）连续失败 N 次时自动置 frozen。本 change 不实现自动检测，仅预留字段。

解冻路径：用户重新走 EA cookie 登录，链路命中已存在的 binding 时，service 层把 `is_frozen` 重置为 false 并写入新凭据。

「primary 被冻结后会怎样」：若该 user 还有其他非冻结 binding，提升时间最近一条为 primary；若没有，user 自身的 `is_frozen` 不变，但任何需要 EA API 的操作都返回 `EA_BINDING_REQUIRED`。

### 数据迁移

Alembic migration 分两步：

**第一步（schema）**：

1. **预检查**：跑 `SELECT persona_id, COUNT(*) FROM users GROUP BY persona_id HAVING COUNT(*)>1 OR persona_id IS NULL`。任何冲突或异常值立即抛错退出，要求人工清理。
2. 新建 `ea_bindings` 表，含 `persona_id UNIQUE` 约束、`user_id` 普通索引、partial unique index `(user_id) WHERE is_primary = true`。
3. 在 `users` 表新增 `username`、`local_password_hash`、`email`、`is_frozen` 字段（先 nullable）。
4. 把每个现有 user 的 `persona_id / display_name / avatar_url / encrypted_*` 复制到一条新 `ea_bindings` 记录，`is_primary=true`，`is_frozen=false`，`last_verified_at` 取 `last_login_at`。
5. 用 `persona_<persona_id>` 填充每个 user 的 `username`，置 `NOT NULL`、`UNIQUE`。
6. 删除 `users` 表中 `persona_id`、`display_name`、`avatar_url`、`encrypted_*` 字段及对应索引。

**admin 名单的迁移**：本迁移**不读** `ADMIN_PERSONA_IDS` 环境变量。理由是 env 在迁移执行时不一定与生产 env 一致（开发者本地、CI、staging 都可能写不同值），把运行时配置固化进版本历史是污染。部署者升级后需手工跑一次 `python -m app.cli grant-admin --persona <id>` 把现有 admin 一次性写入 DB。文档章节会显式列出此步骤。

**第二步（代码切换）**：在同一次发布里，backend 代码切换到读 `ea_bindings`，停止读 `admin_persona_ids` env。

**回滚策略**：down revision 从 `ea_bindings` 的 primary binding 反向重建 `users.persona_id / display_name / avatar_url / encrypted_*`。若发现存在 user 无任何 `ea_bindings`（如 CLI 创建的本地 admin），down 必须**报错退出**而非静默删除该 user 行——删除用户会连带 cascade `server_memberships` 与改变 `audit_logs` 归属，回滚场景下不可接受。要求运维先用 CLI 删除本地 admin 用户后再回滚。在 staging 环境跑双向验证。

### env 字段废弃节奏

本 change：代码完全不读 `admin_persona_ids`，但 `Settings` 类暂时保留字段（标记 deprecated 注释），避免现有 env 文件触发 `extra='forbid'` 报错（实际 config 用的是 `extra='ignore'`，所以可以直接删——但出于谨慎留一个版本作 grace period）。
下一个主版本：从 `Settings` 删除 `admin_persona_ids` 字段，从 `.env.example`、`docker-compose.prod.yml`、README 删除所有引用。

## Risks / Trade-offs

**风险一：迁移失败导致登录中断**。数据迁移涉及搬动凭据字段，若 down revision 不完整，回滚后用户无法登录。缓解：迁移前在 staging 环境跑完整 up + down 双向；迁移脚本写 dry-run 选项，先在生产 DB 副本上验证；迁移当晚保留 `users` 表完整快照。

**风险二：CLI 凭据进入 shell 历史**。`create-admin --password xxx` 会被记录在 bash history。缓解：CLI 同时支持从 stdin 读密码（`--password-stdin`）和交互式 prompt 模式（无 `--password` 参数时进入 `getpass.getpass()` 输入），文档默认推荐 prompt 模式。

**风险三：persona_id UNIQUE 约束在迁移时可能冲突**。理论上现有 `users.persona_id` 已经 unique，迁移后应当无冲突，但若历史数据存在脏数据需先清理。迁移脚本第一步先 `SELECT persona_id, COUNT(*) FROM users GROUP BY persona_id HAVING COUNT(*)>1 OR persona_id IS NULL` 检查（覆盖重复与异常值），发现任何冲突立即报错退出。

**风险四：本地 admin 无 EA 时无法测试 EA API 相关功能**。维护型 admin 创建后想测试一下 kick/ban 流程，发现自己没绑 EA。缓解：UI 在调用 EA 相关页面时清晰提示「此功能需要绑定 EA 账号，请前往账号设置」；文档说明本地 admin 与 EA 玩家 admin 的能力差异。

**权衡一：本地账号不做邮箱验证**。BFBAN 注册要求 EA 邮箱验真，本 change 跳过此步。理由是本地 admin 仅由部署者通过 CLI 创建（不存在「陌生人注册」威胁面），邮箱字段仅用作联系方式。代价是若部署者把 email 字段填错，无法通过邮件找回密码——但找回路径本就是 CLI `reset-password`，不依赖邮箱。

**权衡二：不引入 `privilege` JSON 数组**。BFBAN 用 `['root', 'dev', 'super']` 这种多角色组合。bf-manager 当前 `role` 只区分 admin/user，且服务器级权限已在 `server_memberships`，强行抽象为数组反而引入不必要复杂度。等到真有「站点审计员」「客服只读」之类的横切角色需求时再迁移。

**权衡三：多 binding 但无切换 UI**。表层支持一个 user 多条 binding，但 service 层执行 EA 操作时永远取 primary。这意味着小号绑上去也没法用，只是为未来扩展留接口。会引起部分用户疑问，文档需说明现阶段的限制。

**权衡四：env 字段留一个版本作 grace period**。理论上可以直接删，但生产 docker-compose 文件还引用着，删字段会导致 `Settings()` 初始化报 unknown field 错误（虽然现在是 `extra='ignore'`，但谨慎为上）。代价是代码里残留一个不读的字段一个版本周期。
