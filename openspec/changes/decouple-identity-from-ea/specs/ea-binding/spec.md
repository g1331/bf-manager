## ADDED Requirements

### Requirement: EaBinding 实体作为独立凭据层

EA personas and EA credentials MUST live in a dedicated `ea_bindings` table with N:1 relation to `users`, and `persona_id` MUST be globally UNIQUE across the table.

EA persona 与 EA 凭据必须由 `ea_bindings` 表承载，与 `users` 表完全分离。一条 `ea_bindings` 记录代表「某个 user 拥有某个 EA persona 的可用会话」，是 N 对 1 关系（一个 user 可有多条 binding，每条 binding 隶属一个 user）。

`ea_bindings` 表必须包含：`id`、`user_id`（外键到 `users.id`，`ON DELETE CASCADE`）、`persona_id`（BigInteger，全局唯一）、`display_name`、`avatar_url`、`encrypted_remid`、`encrypted_sid`、`encrypted_session`、`encrypted_access_token`、`is_primary`、`is_frozen`、`last_verified_at`、`created_at`、`updated_at`。

#### Scenario: persona_id 全局唯一

- **WHEN** 尝试创建一条 binding，其 `persona_id` 已存在于另一条 binding 中
- **THEN** 数据库唯一约束拒绝插入；service 层捕获并返回明确错误「该 EA 账号已绑定到其他用户」

#### Scenario: user 删除级联

- **WHEN** 一个 user 被硬删除
- **THEN** 其所有 ea_bindings 自动级联删除，不留孤儿记录

#### Scenario: 一个 user 至多一条 primary binding

- **WHEN** service 层将某条 binding 设为 `is_primary=true`
- **THEN** 同一 user 下其他所有 binding 的 `is_primary` 在同一事务内被置为 false

### Requirement: EA cookie 登录写入或更新 binding

The EA cookie login path MUST upsert the corresponding `ea_bindings` record, and MUST automatically clear `is_frozen` when an existing frozen binding is reactivated by a fresh login.

EA cookie 登录路径必须负责 `ea_bindings` 记录的创建与维护。

对于 persona 首次出现的情况：插入新 binding，`is_primary=true`，`is_frozen=false`，加密凭据写入，`last_verified_at` 取当前时间。

对于 persona 已存在 binding 的情况：更新该 binding 的所有加密凭据字段、`display_name`、`avatar_url`、`last_verified_at`；若该 binding 之前为 `is_frozen=true`，自动置 false 视为「重新激活」；不修改 `is_primary` 状态。

#### Scenario: 重新登录自动解冻

- **WHEN** 一条 `is_frozen=true` 的 binding 对应 persona 再次走 EA cookie 登录
- **THEN** binding 的 `is_frozen` 被置为 false，加密凭据被更新

### Requirement: 用户主动解绑

Users MUST be able to unbind their own bindings via `POST /api/v1/me/ea-bindings/{id}/unbind`, and the system MUST wipe all encrypted credential fields on unbind while preserving the binding row as historical record.

用户必须能通过 `POST /api/v1/me/ea-bindings/{id}/unbind` 主动解绑一条属于自己的 binding。解绑行为不删除记录，而是：将 `is_frozen` 置为 true、`is_primary` 置为 false、清空所有 `encrypted_*` 字段（密文也不留）。

若被解绑的 binding 是当前的 primary，且该 user 还存在其他 `is_frozen=false` 的 binding，service 层必须自动把其中 `last_verified_at` 最近的一条提升为 primary；若不存在其他可用 binding，该 user 在执行任何需要 EA API 的操作时返回 `EA_BINDING_REQUIRED` 错误。

#### Scenario: 解绑非自有 binding

- **WHEN** 用户 A 调用 `POST /api/v1/me/ea-bindings/{B 的 binding id}/unbind`
- **THEN** 服务返回 404，不暴露 binding 是否存在

#### Scenario: 解绑后凭据彻底清除

- **WHEN** 用户解绑一条 binding
- **THEN** 该 binding 的 `encrypted_remid`、`encrypted_sid`、`encrypted_session`、`encrypted_access_token` 全部置 NULL，仅保留 `persona_id`、`display_name` 等非敏感字段作为「曾经绑定过」的历史记录

#### Scenario: primary 解绑后自动提升

- **WHEN** 一个 user 有两条 binding A（primary, 较旧）与 B（非 primary, 较新）均未冻结，用户解绑 A
- **THEN** B 自动被提升为 primary（`is_primary=true`）

### Requirement: EA API 操作的凭据路由与审计身份

EA API 调用必须通过一个可替换的 credential provider 获取凭据；当 provider 无可用凭据源时，操作 MUST 以错误码 `EA_BINDING_REQUIRED` 拒绝。审计日志的 `acting_persona_id` MUST 取自当前用户的 primary 且未冻结 binding，无 binding 时取 0。

所有需要调用 EA API 的服务（BF1 服管命令、用户面 BF 数据查询等）必须通过一个抽象的 `BF1ClientProvider`（或等价接口）获取已登录的 EA 客户端。该接口负责封装「按何种策略选择凭据」的决策，service 与路由层不直接感知凭据来源。

本 change 提供一个 `PooledBF1ClientProvider` 实现：从全局 `ea_accounts` 后台账号池取凭据，任何登录用户都可调用（无需个人 binding）。未来引入「群组与按发起者 EA 身份路由」的 change 时，将新增其他 provider 实现替换或扩展，service 与路由签名不变。

当 provider 判断没有任何可用凭据源（既无后台账号、无用户 binding、无群组绑定）时，必须抛出错误码 `EA_BINDING_REQUIRED`，HTTP 状态 4xx，错误信息提示发起者绑定 EA 或联系管理员配置账号。

审计身份语义与凭据来源解耦：无论 EA API 实际使用哪条凭据，`AuditLog.acting_persona_id` 始终取自「当前操作发起者 user 的 primary 且未冻结 binding 的 persona_id」；若发起者无可用 binding（如 CLI 创建的本地 admin），写 0 表示「以平台身份执行」。

#### Scenario: provider 无可用凭据源时的拒绝

- **WHEN** credential provider 在执行 EA API 调用前判定当前上下文（user、目标 server、群组绑定）没有任何可用凭据源
- **THEN** 操作以 HTTP 412 拒绝，错误码 `EA_BINDING_REQUIRED`，body 包含引导信息

#### Scenario: 后台账号池可用时本地 admin 可执行服管

- **WHEN** 一个由 CLI 创建的本地 admin（无任何 ea_bindings）通过 `PooledBF1ClientProvider` 调用服管路由，且 `ea_accounts` 池中存在可用账号
- **THEN** 操作成功执行，因为账号池兜底；`AuditLog.acting_persona_id` 写 0 表示「以平台身份执行」

#### Scenario: 审计日志记录 acting_persona_id

- **WHEN** 一个拥有 primary binding 的用户成功执行了一次 EA API 服管操作
- **THEN** `AuditLog.acting_persona_id` 等于该用户 primary binding 的 `persona_id`，`user_id` 等于操作发起者 user 的 id；与实际 EA 调用使用的凭据来源无关

#### Scenario: 本地 admin 平台操作的 acting_persona_id

- **WHEN** 一个本地 admin 执行不涉及 EA API 的纯平台操作（例如查审计日志）
- **THEN** `AuditLog.acting_persona_id=0`，`user_id` 为该 admin 的 id
