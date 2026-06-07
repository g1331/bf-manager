#!/usr/bin/env bash
# 生产环境一键部署 / 更新脚本
#
# 首次运行：备齐 secrets、准备 .env.prod（交互填 DOMAIN）、拉镜像、起服务（migrate
#           job 自动跑 alembic upgrade head）、检测到无管理员时交互创建第一个管理员。
# 后续运行：拉新镜像、滚动更新、自动迁移。幂等，可重复执行。
#
# 镜像由 CI（release.yml）在 push main / 打 tag 时构建推送到 GHCR，本机只 pull，不 build。
#
# 用法：
#   bash tools/deploy.sh                 # 部署 / 更新到当前 IMAGE_TAG（默认 latest）
#   bash tools/deploy.sh --tag v1.2.3    # 锁定镜像版本
#   bash tools/deploy.sh --skip-admin    # 跳过首个管理员检测 / 创建
#   bash tools/deploy.sh --help

set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

ENV_FILE=".env.prod"
COMPOSE_FILE="docker-compose.prod.yml"
SECRETS_DIR="secrets"
REQUIRED_SECRETS=(postgres_password database_url ea_cred_encryption_key jwt_secret_key)
# .env.example 里 DOMAIN 的占位值，等同于「未配置」
DOMAIN_PLACEHOLDER="bf-manager.example.com"

IMAGE_TAG_OVERRIDE=""
SKIP_ADMIN=0

log() { printf '\033[36m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[deploy]\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            IMAGE_TAG_OVERRIDE="${2:?--tag 需要一个值}"
            shift 2
            ;;
        --tag=*)
            IMAGE_TAG_OVERRIDE="${1#*=}"
            shift
            ;;
        --skip-admin)
            SKIP_ADMIN=1
            shift
            ;;
        -h | --help)
            sed -n '2,14p' "$0"
            exit 0
            ;;
        *) die "未知参数: $1（用 --help 查看用法）" ;;
    esac
done

command -v docker >/dev/null 2>&1 || die "未找到 docker"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose v2（需要 docker compose 而非 docker-compose）"

# ===== 1. secrets =====
missing_secret=0
for s in "${REQUIRED_SECRETS[@]}"; do
    [[ -f "$SECRETS_DIR/$s" ]] || missing_secret=1
done
if [[ $missing_secret -eq 1 ]]; then
    log "secrets 不完整，运行 tools/init-prod-secrets.sh 生成缺失项"
    bash tools/init-prod-secrets.sh
else
    log "secrets 已就绪"
fi

# ===== 2. .env.prod（生产 compose 唯一硬性要求是真实 DOMAIN）=====
if [[ ! -f "$ENV_FILE" ]]; then
    log "$ENV_FILE 不存在，从 .env.example 生成"
    cp .env.example "$ENV_FILE"
fi
current_domain="$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
if [[ -z "$current_domain" || "$current_domain" == "$DOMAIN_PLACEHOLDER" ]]; then
    if [[ -t 0 ]]; then
        read -rp "请输入生产域名 DOMAIN（如 bf.example.com）: " input_domain
        [[ -n "$input_domain" ]] || die "DOMAIN 不能为空"
        if grep -qE '^DOMAIN=' "$ENV_FILE"; then
            sed -i.bak -E "s|^DOMAIN=.*|DOMAIN=${input_domain}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
        else
            printf '\nDOMAIN=%s\n' "$input_domain" >>"$ENV_FILE"
        fi
        log "已写入 DOMAIN=${input_domain}"
    else
        die "$ENV_FILE 未设置有效 DOMAIN，且当前无交互终端。请手动编辑 $ENV_FILE 后重试"
    fi
fi

# ===== 3. 镜像 tag 覆盖（导出的环境变量优先于 --env-file）=====
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ -n "$IMAGE_TAG_OVERRIDE" ]]; then
    export IMAGE_TAG="$IMAGE_TAG_OVERRIDE"
    log "锁定镜像 tag: $IMAGE_TAG"
fi

# ===== 4. 拉镜像 + 起服务（migrate job 在 up 时自动 alembic upgrade head）=====
log "拉取镜像..."
"${COMPOSE[@]}" pull
log "启动 / 更新服务（含自动迁移）..."
"${COMPOSE[@]}" up -d

# ===== 5/6. 首个管理员检测（list-admins 同时充当后端 + DB 就绪探测）=====
if [[ $SKIP_ADMIN -eq 1 ]]; then
    log "按 --skip-admin 跳过管理员检测"
else
    log "等待后端就绪并检查管理员账号..."
    admins_output=""
    ready=0
    for _ in $(seq 1 30); do
        if admins_output="$("${COMPOSE[@]}" exec -T backend python -m app.cli list-admins 2>/dev/null)"; then
            ready=1
            break
        fi
        sleep 2
    done
    if [[ $ready -eq 0 ]]; then
        warn "后端 / 数据库 60s 内未就绪，跳过管理员检测。"
        warn "排查：${COMPOSE[*]} logs backend"
    elif printf '%s' "$admins_output" | grep -q "（无 admin）"; then
        log "当前没有管理员账号"
        if [[ -t 0 ]]; then
            read -rp "现在创建第一个本地管理员？输入用户名（留空跳过）: " admin_user
            if [[ -n "$admin_user" ]]; then
                # create-admin 用 getpass 交互式读密码，需要当前 TTY
                "${COMPOSE[@]}" exec backend python -m app.cli create-admin --username "$admin_user"
            else
                log "已跳过管理员创建"
            fi
        else
            warn "检测到无管理员，但当前无交互终端。请在交互式 shell 内运行："
            warn "  ${COMPOSE[*]} exec backend python -m app.cli create-admin --username <name>"
        fi
    else
        log "管理员已存在，跳过创建"
    fi
fi

log "部署完成。当前服务状态："
"${COMPOSE[@]}" ps
log "提示：EA 代查询账号（玩家查询 / 服管所需）用以下命令录入："
log "  ${COMPOSE[*]} exec backend python -m app.cli upsert-ea-account --persona-id <id> --stdin-json"
