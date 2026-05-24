# BF-Manager

> Battlefield 系列战绩查询与服务器管理 Web 全栈平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript)](https://www.typescriptlang.org/)

面向开放注册的 Battlefield 系列玩家与服主平台。架构以共享的 EA 身份层 + 游戏特定实现层组合，原生支持多游戏接入。前端移动优先响应式设计，桌面与手机浏览器均获得良好体验。

## 功能范围

| 模块 | 功能 |
|---|---|
| 用户认证 | EA Cookie (remid / sid) 登录，persona 自动绑定，JWT 签发，AES-256-GCM 加密存储凭据，AppHeader 用户菜单 + 登出 |
| 游戏入口 | 首页游戏选择，GameSwitcher 切换器，per-game 主题切换 |
| BF1 战绩查询 | 头像（SAL 反查，gametools 兜底）、生涯数据、武器统计、载具统计、最近对局 |
| BF1 服务器列表 | 服务器搜索、客户端分批渲染（每批 50，最多拉 200）、详情页（地图轮换、当前对局、玩家列表） |
| BF1 服管操作 | 踢人、VBAN 增删、换图，二次确认（移动 BottomSheet / 桌面 Dialog）+ 审计日志 |
| 操作日志 | 跨游戏审计日志：普通用户只看自己，平台 admin 看全部，按 game / server / action 筛选 |
| 服管权限授予 | `/admin/memberships`：仅平台 admin 可见，授予 / 撤销服管权限（viewer / moderator / admin / owner） |

## 技术栈

| 层 | 选型 |
|---|---|
| 仓库形态 | Monorepo + pnpm workspaces |
| 前端 | Next.js 16 + App Router + TypeScript + shadcn/ui + Tailwind v4 + TanStack Query + Zustand + RHF/Zod + ECharts |
| 后端 | FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 |
| 数据库 | PostgreSQL 16 + Redis 7 |
| 包管理 | 后端 uv，前端 pnpm |
| 容器化 | Docker Compose + 多阶段 Dockerfile，TLS 与反代由 host 上的 openresty / nginx 处理 |
| 镜像 | ghcr.io（GitHub Container Registry），由 `release.yml` workflow 自动构建并推送 |
| PWA | manifest + SVG 图标 + apple-touch-icon meta，支持"添加到主屏幕"安装 |

## 目录结构

```
bf-manager/
├── apps/
│   ├── web/                  # Next.js 前端
│   └── backend/              # FastAPI 后端
├── packages/
│   ├── shared-types/         # 从 OpenAPI 生成的 TS 类型
│   ├── eslint-config/        # 共享 ESLint 配置
│   └── tsconfig/             # 共享 TS 配置
├── tools/                    # 脚本工具（含 generate-types.sh）
├── docker-compose.yml        # dev 环境
├── docker-compose.prod.yml   # prod 环境（backend / web 仅监听 127.0.0.1，由 host openresty 反代）
└── Makefile                  # 快捷命令
```

后端核心目录约定：

```
apps/backend/app/
├── domain/
│   ├── ea/              # 跨游戏共享：身份、persona、Blaze 协议
│   └── games/
│       └── bf1/         # BF1 特定：profile、gateway、字段 schema
├── services/            # 业务编排（含 authz / membership / audit）
├── models/              # SQLAlchemy 表（共享 + 游戏特定子目录）
├── schemas/             # Pydantic 请求 / 响应
└── api/v1/              # 路由（auth / memberships / audit-logs / games/<game_id>/）
```

接口级集成测试位于 `apps/backend/tests/`（health / auth / audit / memberships），运行于 in-memory sqlite，不依赖 postgres / redis。

## 快速开始

### 前置依赖

- Docker 与 Docker Compose
- Node.js 20+ 与 pnpm 9+
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)
- Make（Windows 用户：`choco install make`）

### 启动开发环境

```bash
# 复制环境变量样例
cp .env.example .env

# 安装依赖（首次）
make install

# 一键起栈（postgres + redis + backend + web）
make dev

# 跑数据库迁移
make migrate

# Seed 一个 EA 代查询账号到 ea_accounts 表（玩家查询 / 服管功能需要）
# remid / sid 从 accounts.ea.com 的浏览器 Cookies 拿到
docker compose exec backend uv run python tools/seed_ea_account.py \
    --persona-id <PERSONA_ID> --remid <REMID> --sid <SID>
```

### 平台 admin 配置

`ADMIN_PERSONA_IDS` 环境变量（逗号分隔的 persona_id 列表）决定哪些用户登录后自动获得 `role=admin`，可访问 `/admin/memberships` 与全量审计日志。

```bash
# .env / .env.prod
ADMIN_PERSONA_IDS=1003517866915,1004198901469
```

声明式管理：每次登录按 env 重新计算 role，不在名单内的用户会被降回 `user`。env 改了重启 backend 即生效。

服管授权流程：平台 admin 在 `/admin/memberships` 录入 `(persona_id, game, server_id, role)` 即可。被授权用户必须先在本平台登录过一次（users 表里有记录）。

启动后访问：

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| Postgres | localhost:5432 (bf / bf) |
| Redis | localhost:6379 |

### 移动端测试

DevTools 中切换到以下 viewport 验证响应式：

- iPhone SE (375px) / iPhone 14 Pro (393px) / iPhone 14 Pro Max (430px)
- Android 小屏 (360px) / 中屏 (412px)
- 桌面 (1280px / 1920px)

## 生产部署

```bash
# 1. 在部署机器上克隆仓库
git clone https://github.com/g1331/bf-manager.git
cd bf-manager

# 2. 初始化密钥（生成 secrets/ 下的 postgres_password / database_url / ea_cred_encryption_key / jwt_secret_key）
bash tools/init-prod-secrets.sh

# 3. 编辑 .env.prod 填入域名、admin persona 名单等参数
cp .env.example .env.prod
$EDITOR .env.prod   # 至少设置 DOMAIN 与 ADMIN_PERSONA_IDS

# 4. 拉镜像 + 启动
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# 5. （首次部署）migrate 服务由 compose 自动跑一次 alembic upgrade head；
#    如需手动重跑：
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate

# 6. Seed 至少一个 EA 代查询账号（玩家查询 / 服管必需）
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \
    python tools/seed_ea_account.py \
    --persona-id <PERSONA_ID> --remid <REMID> --sid <SID>
```

TLS 与反代由 host 上的 openresty / nginx 处理，backend 与 web 容器只把 `127.0.0.1:8000` 与 `127.0.0.1:3000` 暴露给 host，杜绝外网直连绕过反代。

镜像由 GitHub Actions `release.yml` workflow 在 push main 或打 tag（`v*`）时构建并推送到 `ghcr.io/g1331/bf-manager-{backend,web}`。`IMAGE_TAG` 环境变量可锁定具体版本。

## 多游戏支持

新增游戏（如 BFV）的步骤：

1. 创建 `apps/backend/app/domain/games/<game_id>/` 目录，复制 BF1 结构作为模板
2. 编写 `profile.py`，填入新游戏的代号、请求头版本、Blaze 端点
3. 在 `models/<game_id>/` 添加游戏特定表，写 Alembic migration
4. 在 `services/<game_id>/` 实现业务逻辑
5. 在 `api/v1/games/<game_id>/` 添加路由
6. 前端 `app/(public)/[game]/` 动态段自动覆盖，仅需添加 `components/games/<game_id>/` 特定组件和 `styles/themes/<game_id>.css`
7. `lib/game-registry.ts` 添加游戏元数据条目

详见 `apps/backend/app/domain/games/README.md`。

## 类型生成（前后端 schema 一致性）

前端使用的类型来自后端 FastAPI 的 OpenAPI 定义，由 `tools/generate-types.sh` 通过 `openapi-typescript` 生成到 `packages/shared-types/src/api.d.ts`。

```bash
# 1. 起后端（dev 或本地）
make dev

# 2. 生成类型
bash tools/generate-types.sh
```

生成结果不进 git（被 `.gitignore` 忽略），后端 schema 改动后前端需要重新生成。前端可通过 `@bf-manager/shared-types/api` 引用 `paths` / `components`，获得与后端 OpenAPI 一致的类型。

## 贡献

欢迎 Issue 与 Pull Request。提交规范遵循 [Conventional Commits](https://www.conventionalcommits.org/)。提交前会自动运行 `lefthook` 钩子（ruff + ESLint）。

## License

[MIT](LICENSE) © 2026 g1331
