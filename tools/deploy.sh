#!/usr/bin/env bash
# 生产环境部署 / 更新 / 回滚脚本
#
# 首次运行：备齐 secrets、准备 .env.prod（交互填 DOMAIN）、拉镜像、起服务、无管理员时交互创建第一个管理员。
# 后续运行：把镜像锁定到某个 commit，有待执行的迁移先备份数据库，更新后等健康检查和冒烟通过，
#           再清掉本项目不再需要的旧镜像。幂等，可重复执行。
#
# 镜像由 CI 构建推送到 GHCR：push main 时 ci.yml 检查全过后调用 release.yml（标签为 7 位 commit 和 latest），
# 打 tag 时 release.yml 直接跑（标签为 vX.Y.Z）。本机只 pull，不 build。
# 部署的版本写进 .env.prod 的 IMAGE_TAG，手动跑 docker compose 也不会漂到别的版本；
# 上一个版本记在 .deploy-previous，--rollback 回到它。
#
# 用法：
#   bash tools/deploy.sh                 # 部署 main 的最新构建（解析 latest 对应的 commit 并锁定）
#   bash tools/deploy.sh --tag 249526d   # 部署指定 commit 或 vX.Y.Z
#   bash tools/deploy.sh --rollback      # 回到上一次部署的版本
#   bash tools/deploy.sh --skip-admin    # 跳过首个管理员检测 / 创建
#   bash tools/deploy.sh --help

set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

ENV_FILE=".env.prod"
COMPOSE_FILE="docker-compose.prod.yml"
SECRETS_DIR="secrets"
PREVIOUS_FILE=".deploy-previous"
REQUIRED_SECRETS=(postgres_password database_url ea_cred_encryption_key jwt_secret_key resend_api_key turnstile_secret_key)
# .env.example 里 DOMAIN 的占位值，等同于「未配置」
DOMAIN_PLACEHOLDER="bf-manager.example.com"
BACKEND_IMAGE="ghcr.io/g1331/bf-manager-backend"
WEB_IMAGE="ghcr.io/g1331/bf-manager-web"
# 只拉、只更新应用服务；postgres / redis 用浮动标签，顺手 pull 会在 up 时把数据库换成新的小版本
APP_SERVICES=(migrate backend web)
HEALTH_TIMEOUT=180

TAG_OVERRIDE=""
ROLLBACK=0
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
            TAG_OVERRIDE="${2:?--tag 需要一个值}"
            shift 2
            ;;
        --tag=*)
            TAG_OVERRIDE="${1#*=}"
            shift
            ;;
        --rollback)
            ROLLBACK=1
            shift
            ;;
        --skip-admin)
            SKIP_ADMIN=1
            shift
            ;;
        -h | --help)
            sed -n '2,18p' "$0"
            exit 0
            ;;
        *) die "未知参数: $1（用 --help 查看用法）" ;;
    esac
done
[[ $ROLLBACK -eq 1 && -n "$TAG_OVERRIDE" ]] && die "--rollback 和 --tag 只能二选一"

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

# 读 / 写 .env.prod 里的单个变量；值只允许不含空白和 | 的简单字符串
env_get() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
env_set() {
    if grep -qE "^$1=" "$ENV_FILE"; then
        sed -i.bak -E "s|^$1=.*|$1=$2|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    else
        printf '\n%s=%s\n' "$1" "$2" >>"$ENV_FILE"
    fi
}

current_domain="$(env_get DOMAIN)"
if [[ -z "$current_domain" || "$current_domain" == "$DOMAIN_PLACEHOLDER" ]]; then
    if [[ -t 0 ]]; then
        read -rp "请输入生产域名 DOMAIN（如 bf.example.com）: " input_domain
        [[ -n "$input_domain" ]] || die "DOMAIN 不能为空"
        env_set DOMAIN "$input_domain"
        log "已写入 DOMAIN=${input_domain}"
    else
        die "$ENV_FILE 未设置有效 DOMAIN，且当前无交互终端。请手动编辑 $ENV_FILE 后重试"
    fi
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

image_label() { docker image inspect "$1" --format "{{index .Config.Labels \"$2\"}}" 2>/dev/null || true; }

# 线上正在跑的版本：.env.prod 已锁定就用它，否则（还是 latest）读运行中容器镜像的 commit
running_version() {
    local pinned container image rev
    pinned="$(env_get IMAGE_TAG)"
    if [[ -n "$pinned" && "$pinned" != "latest" ]]; then
        echo "$pinned"
        return
    fi
    container="$("${COMPOSE[@]}" ps -q backend 2>/dev/null || true)"
    [[ -n "$container" ]] || return 0
    image="$(docker inspect "$container" --format '{{.Image}}')"
    rev="$(image_label "$image" org.opencontainers.image.revision)"
    [[ -n "$rev" ]] && echo "${rev:0:7}"
    return 0
}

# ===== 3. 确定目标版本 =====
FROM_VERSION="$(running_version)"
if [[ $ROLLBACK -eq 1 ]]; then
    [[ -f "$PREVIOUS_FILE" ]] || die "没有 $PREVIOUS_FILE，不知道上一个版本是什么；请用 --tag <commit> 指定"
    TARGET="$(<"$PREVIOUS_FILE")"
    log "回滚：${FROM_VERSION:-未知} → $TARGET"
elif [[ -n "$TAG_OVERRIDE" ]]; then
    TARGET="$TAG_OVERRIDE"
else
    log "解析 main 最新构建对应的 commit..."
    docker pull -q "$BACKEND_IMAGE:latest" >/dev/null
    rev="$(image_label "$BACKEND_IMAGE:latest" org.opencontainers.image.revision)"
    [[ -n "$rev" ]] || die "latest 镜像上没有 revision 标签，请用 --tag 指定版本"
    TARGET="${rev:0:7}"
fi
[[ "$TARGET" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "非法的镜像标签: $TARGET"
[[ "$TARGET" == "latest" ]] && die "不再部署浮动的 latest，请指定 commit 或 vX.Y.Z"
export IMAGE_TAG="$TARGET"
log "目标版本: $TARGET（当前: ${FROM_VERSION:-未部署}）"

# ===== 4. 拉镜像 =====
log "拉取 $TARGET 的镜像..."
"${COMPOSE[@]}" pull -q "${APP_SERVICES[@]}"

# ===== 5. 核对生产 compose 与该版本仓库里的是否一致（回滚时跳过，compose 保持现状）=====
if [[ $ROLLBACK -eq 0 ]]; then
    revision="$(image_label "$BACKEND_IMAGE:$TARGET" org.opencontainers.image.revision)"
    source_url="$(image_label "$BACKEND_IMAGE:$TARGET" org.opencontainers.image.source)"
    raw_url="${source_url/https:\/\/github.com/https://raw.githubusercontent.com}/${revision}/${COMPOSE_FILE}"
    if [[ -n "$revision" && -n "$source_url" ]] && repo_compose="$(curl -fsSL --max-time 15 "$raw_url" 2>/dev/null)"; then
        if ! drift="$(diff <(printf '%s\n' "$repo_compose") "$COMPOSE_FILE")"; then
            printf '%s\n' "$drift" >&2
            die "本机 $COMPOSE_FILE 与 ${revision:0:7} 仓库里的不一致（上面 < 是仓库，> 是本机）。先同步再部署：curl -fsSL $raw_url -o $COMPOSE_FILE"
        fi
        log "compose 与仓库一致"
    else
        warn "取不到该版本仓库里的 $COMPOSE_FILE，跳过 compose 核对"
    fi
fi

# ===== 6. 有待执行的迁移先备份数据库 =====
if [[ -n "$("${COMPOSE[@]}" ps -q --status running postgres 2>/dev/null)" ]]; then
    if ! alembic_out="$("${COMPOSE[@]}" run --rm --no-deps -T migrate alembic current 2>&1)"; then
        printf '%s\n' "$alembic_out" | tail -5 >&2
        if grep -q "Can't locate revision" <<<"$alembic_out"; then
            die "数据库已经迁移到 $TARGET 不认识的版本。回滚到迁移之前的代码需要先手动 downgrade，脚本不自动做"
        fi
        die "读取数据库迁移版本失败"
    fi
    if grep -q "(head)" <<<"$alembic_out"; then
        log "没有待执行的迁移"
    else
        log "有待执行的迁移，先备份数据库..."
        PROJECT_DIR="$PWD" BACKUP_ROOT="$PWD/backups/pre-deploy" bash tools/backup.sh "$COMPOSE_FILE"
    fi
else
    log "数据库还没在运行（首次部署），跳过迁移前备份"
fi

# ===== 7. 更新服务（migrate job 在 up 时自动 alembic upgrade head）=====
log "启动 / 更新服务..."
"${COMPOSE[@]}" up -d

# ===== 8. 等健康检查 =====
wait_healthy() {
    local service="$1" container status waited=0
    container="$("${COMPOSE[@]}" ps -q "$service")"
    [[ -n "$container" ]] || die "$service 没有在运行"
    while :; do
        status="$(docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
        case "$status" in
            healthy) return 0 ;;
            unhealthy | exited | dead) break ;;
        esac
        ((waited >= HEALTH_TIMEOUT)) && break
        sleep 3
        waited=$((waited + 3))
    done
    "${COMPOSE[@]}" logs --tail 30 "$service" >&2 || true
    die "$service 状态 $status，未通过健康检查。需要的话：bash tools/deploy.sh --rollback"
}
log "等待 backend / web 健康检查..."
wait_healthy backend
wait_healthy web

# ===== 9. 冒烟：后端报的版本对得上，前端首页能打开 =====
backend_addr="$("${COMPOSE[@]}" port backend 8000)"
web_addr="$("${COMPOSE[@]}" port web 3000)"
health="$(curl -fsS --max-time 10 "http://$backend_addr/api/v1/healthz")" || die "后端 /api/v1/healthz 请求失败"
reported="$(sed -nE 's/.*"version":"([^"]*)".*/\1/p' <<<"$health")"
if [[ "$reported" == "$TARGET" ]]; then
    log "后端版本 $reported"
elif [[ "$reported" == "main" ]]; then
    warn "后端镜像是旧构建，版本号只有 main，无法核对 commit"
else
    die "后端报告版本 $reported，与目标 $TARGET 不符"
fi
web_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "http://$web_addr/")"
[[ "$web_code" == "200" ]] || die "前端首页返回 $web_code"
log "前端首页 200"

# ===== 10. 记录版本 =====
env_set IMAGE_TAG "$TARGET"
if [[ -n "$FROM_VERSION" && "$FROM_VERSION" != "$TARGET" ]]; then
    echo "$FROM_VERSION" >"$PREVIOUS_FILE"
fi
log "已锁定 IMAGE_TAG=$TARGET${FROM_VERSION:+，上一个版本 $FROM_VERSION 可用 --rollback 回去}"

# ===== 11. 首个管理员检测（list-admins 同时充当后端 + DB 就绪探测）=====
if [[ $SKIP_ADMIN -eq 1 ]]; then
    log "按 --skip-admin 跳过管理员检测"
else
    admins_output=""
    if ! admins_output="$("${COMPOSE[@]}" exec -T backend python -m app.cli list-admins 2>/dev/null)"; then
        warn "管理员检测失败，跳过。排查：${COMPOSE[*]} logs backend"
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
    fi
fi

# ===== 12. 清理本项目的旧镜像：留当前、上一个版本和 latest，其余标签和悬空镜像删掉 =====
keep=("$TARGET" "latest")
[[ -f "$PREVIOUS_FILE" ]] && keep+=("$(<"$PREVIOUS_FILE")")
removed=0
for repo in "$BACKEND_IMAGE" "$WEB_IMAGE"; do
    while read -r tag; do
        [[ -z "$tag" || "$tag" == "<none>" ]] && continue
        [[ " ${keep[*]} " == *" $tag "* ]] && continue
        docker rmi "$repo:$tag" >/dev/null 2>&1 && removed=$((removed + 1))
    done < <(docker images "$repo" --format '{{.Tag}}')
done
source_label="org.opencontainers.image.source=$(image_label "$BACKEND_IMAGE:$TARGET" org.opencontainers.image.source)"
while read -r id; do
    [[ -n "$id" ]] && docker rmi "$id" >/dev/null 2>&1 && removed=$((removed + 1))
done < <(docker images -q --filter dangling=true --filter "label=$source_label" | sort -u)
log "清理旧镜像 $removed 个"

log "部署完成。当前服务状态："
"${COMPOSE[@]}" ps
