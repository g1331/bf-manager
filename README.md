# BF-Manager

> Battlefield 系列战绩查询与服务器管理 Web 全栈平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript)](https://www.typescriptlang.org/)

面向开放注册的 Battlefield 系列玩家与服主平台。MVP 阶段聚焦 BF1，架构层面预留 BFV / BF2042 接入空间。前端移动优先响应式设计，桌面与手机浏览器均获得良好体验。

## 功能范围（MVP）

| 模块 | 功能 |
|---|---|
| M1 · 用户认证 | EA Cookie (remid / sid) 登录，persona 自动绑定，JWT 签发，AES-256-GCM 加密存储凭据 |
| M2 · 游戏入口 | 首页游戏选择，GameSwitcher 切换器，per-game 主题切换 |
| M3 · BF1 战绩查询 | 生涯数据 / 武器统计 / 载具统计 / 最近对局 |
| M4 · BF1 服务器列表 | 列表分页搜索、详情页（地图轮换、当前对局、玩家列表） |
| M5 · BF1 服管操作 | 踢人、VBAN 增删、换图，二次确认 + 审计日志 |
| M6 · 操作日志 | 跨服务器审计日志，按服务器 / 操作类型筛选 |

## 技术栈

| 层 | 选型 |
|---|---|
| 仓库形态 | Monorepo + pnpm workspaces |
| 前端 | Next.js 15 + App Router + TypeScript + shadcn/ui + Tailwind + TanStack Query + Zustand + RHF/Zod + ECharts + next-pwa |
| 后端 | FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 |
| 数据库 | PostgreSQL 16 + Redis 7 |
| 包管理 | 后端 uv，前端 pnpm |
| 容器化 | Docker Compose + 多阶段 Dockerfile + Caddy（自动 TLS） |
| 镜像 | ghcr.io（GitHub Container Registry） |

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
├── tools/                    # 脚本工具
├── docker-compose.yml        # dev 环境
├── docker-compose.prod.yml   # prod 环境
├── Caddyfile                 # 反向代理与 TLS
└── Makefile                  # 快捷命令
```

后端核心目录约定：

```
apps/backend/app/
├── domain/
│   ├── ea/              # 跨游戏共享：身份、persona、Blaze 协议
│   └── games/
│       └── bf1/         # BF1 特定：profile、gateway、字段 schema
├── services/            # 业务编排
├── models/              # SQLAlchemy 表（共享 + 游戏特定子目录）
├── schemas/             # Pydantic 请求 / 响应
└── api/v1/              # 路由（通用 + games/<game_id>/ 子路由）
```

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
```

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

# 2. 初始化密钥
make secrets-init

# 3. 编辑 .env.prod 填入域名等参数
cp .env.example .env.prod
$EDITOR .env.prod

# 4. 拉镜像 + 启动
make prod-pull
make prod-up

# 5. 跑数据库迁移（首次部署需要）
docker compose -f docker-compose.prod.yml run --rm migrate
```

Caddy 自动从 Let's Encrypt 申请 TLS 证书，无需额外配置。

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

## 贡献

欢迎 Issue 与 Pull Request。提交规范遵循 [Conventional Commits](https://www.conventionalcommits.org/)。提交前会自动运行 `lefthook` 钩子（ruff + ESLint）。

## License

[MIT](LICENSE) © 2026 g1331
