# BF-Manager · 开发与部署快捷命令
# 使用方式：make <target>
# Windows 下需要 GNU Make（可通过 chocolatey: choco install make 安装）

.PHONY: help install dev dev-logs dev-down dev-clean \
        prod-pull prod-up prod-down prod-logs prod-restart \
        migrate makemigrations shell-be shell-fe shell-db shell-redis \
        lint typecheck test fmt secrets-init backup gen-types

help: ## 显示可用命令
	@echo "BF-Manager · Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ===== 安装 =====
install: ## 安装前端与后端依赖
	pnpm install
	cd apps/backend && uv sync

# ===== 开发环境（dev） =====
dev: ## 启动开发环境（postgres + redis + backend + web）
	docker compose up -d
	@echo ""
	@echo "  Backend  → http://localhost:8000"
	@echo "  Web      → http://localhost:3000"
	@echo "  Postgres → localhost:5432 (bf/bf)"
	@echo "  Redis    → localhost:6379"

dev-logs: ## 跟踪开发环境日志
	docker compose logs -f

dev-down: ## 停止开发环境
	docker compose down

dev-clean: ## 停止开发环境并清理数据卷
	docker compose down -v

# ===== 生产环境（prod） =====
# 所有 prod 命令都需要 .env.prod（DOMAIN 等变量由 compose 文件强制要求）
prod-pull: ## 拉取生产镜像
	docker compose -f docker-compose.prod.yml --env-file .env.prod pull

prod-up: ## 启动生产环境
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

prod-down: ## 停止生产环境
	docker compose -f docker-compose.prod.yml --env-file .env.prod down

prod-logs: ## 跟踪生产环境日志
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f

prod-restart: ## 重启生产环境
	docker compose -f docker-compose.prod.yml --env-file .env.prod restart

prod-migrate: ## 在生产环境单独触发一次数据库迁移（compose up 时也会自动跑一次）
	docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrate

# ===== 数据库 =====
migrate: ## 跑数据库迁移到最新版本
	docker compose exec backend uv run alembic upgrade head

makemigrations: ## 生成新的 Alembic migration（用法：make makemigrations msg="add foo"）
	docker compose exec backend uv run alembic revision --autogenerate -m "$(msg)"

# ===== 容器内 Shell =====
shell-be: ## 进入后端容器
	docker compose exec backend bash

shell-fe: ## 进入前端容器
	docker compose exec web sh

shell-db: ## 进入数据库 psql
	docker compose exec postgres psql -U bf -d bf_manager

shell-redis: ## 进入 redis-cli
	docker compose exec redis redis-cli

# ===== 代码质量 =====
lint: ## 运行前后端 lint
	cd apps/backend && uv run ruff check .
	pnpm -r lint

typecheck: ## 运行前后端类型检查
	cd apps/backend && uv run ruff check . --select=ANN
	pnpm -r typecheck

fmt: ## 格式化前后端代码
	cd apps/backend && uv run ruff format .
	pnpm -r format

test: ## 运行测试
	cd apps/backend && uv run pytest
	pnpm -r test

# ===== 工具 =====
secrets-init: ## 初始化生产环境密钥到 ./secrets/
	bash tools/init-prod-secrets.sh

backup: ## 备份数据库到 ./backups/
	bash tools/backup.sh

gen-types: ## 从后端 OpenAPI 生成前端类型
	bash tools/generate-types.sh
