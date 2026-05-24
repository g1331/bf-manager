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

### Requirement: EA API 操作的身份选择

Any service that calls EA APIs on behalf of a user MUST source credentials from that user's primary, non-frozen binding, and MUST reject the operation with error code `EA_BINDING_REQUIRED` when no such binding exists.

所有需要以用户身份调用 EA API 的服务（服管命令、用户面 BF 数据查询等）必须从「当前 user 的 primary 且未冻结 binding」取加密凭据。

若该 user 没有满足条件的 binding，操作必须拒绝并返回错误码 `EA_BINDING_REQUIRED`，错误信息提示用户去「账号设置」绑定或重新登录 EA 账号。

不允许任何路径使用「最近活跃的 binding」「任意一条 binding」之类的隐式选择策略。

#### Scenario: 本地 admin 无 binding 时调用 EA 操作

- **WHEN** 一个由 CLI 创建的本地 admin（`local_password_hash` 非空，无任何 ea_bindings）调用需要 EA 凭据的服管路由
- **THEN** 路由返回 4xx 错误，错误码 `EA_BINDING_REQUIRED`，HTTP body 包含引导信息

#### Scenario: 所有 binding 都冻结时调用 EA 操作

- **WHEN** 一个 user 的所有 binding 都是 `is_frozen=true`
- **THEN** EA 操作返回 `EA_BINDING_REQUIRED`，与「无 binding」表现一致

#### Scenario: 审计日志记录 acting_persona_id

- **WHEN** 一个用户通过 primary binding 成功执行了一次 EA API 服管操作
- **THEN** AuditLog 记录的 `acting_persona_id` 等于该 binding 的 `persona_id`，`user_id` 等于操作发起者 user 的 id

#### Scenario: 本地 admin 平台操作的 acting_persona_id

- **WHEN** 一个本地 admin 执行不涉及 EA API 的纯平台操作（例如查审计日志）
- **THEN** AuditLog 记录的 `acting_persona_id=0`，`user_id` 为该 admin 的 id
