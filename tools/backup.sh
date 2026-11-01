#!/usr/bin/env bash
# 备份 Postgres 数据库到 <BACKUP_ROOT>/<date>/<db>.sql.gz，并删除超过保留天数的旧备份
#
# 用法：bash tools/backup.sh [compose-file]
#   默认备份生产库（docker-compose.prod.yml，自动带上 .env.prod）；传 docker-compose.yml 备份开发库
#
# 环境变量：
#   PROJECT_DIR  compose 文件所在目录，默认仓库根目录；生产机上指向 /srv/bf-manager
#   BACKUP_ROOT  备份存放目录，默认 $PROJECT_DIR/backups
#   KEEP_DAYS    保留天数，默认 7
#
# 定时执行见 tools/systemd/bf-manager-backup.{service,timer}

set -euo pipefail

COMPOSE_FILE="${1:-docker-compose.prod.yml}"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_DIR/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
POSTGRES_USER="${POSTGRES_USER:-bf}"
POSTGRES_DB="${POSTGRES_DB:-bf_manager}"

cd "$PROJECT_DIR"

# 生产 compose 里的 DOMAIN 等变量来自 .env.prod，不带上它 compose 连 exec 都会拒绝
compose=(docker compose -f "$COMPOSE_FILE")
if [[ "$COMPOSE_FILE" == *prod* && -f .env.prod ]]; then
    compose+=(--env-file .env.prod)
fi

BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/${POSTGRES_DB}.sql.gz"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_ROOT" "$BACKUP_DIR"
trap 'rm -f "$OUT.partial"; rmdir "$BACKUP_DIR" 2>/dev/null || true' ERR

echo "Backing up $POSTGRES_DB to $OUT ..."

# 先写临时文件，pg_dump 或 gzip 中途失败时不留下看似完整的半截备份
"${compose[@]}" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
    | gzip > "$OUT.partial"
gzip -t "$OUT.partial"
mv "$OUT.partial" "$OUT"
chmod 600 "$OUT"

echo "Backup saved: $OUT ($(du -h "$OUT" | cut -f1))"

# 只清理本脚本建的 YYYYmmdd_HHMMSS 目录，其他文件和目录不动
d6="[0-9][0-9][0-9][0-9][0-9][0-9]"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name "20${d6}_${d6}" \
    -mtime "+$KEEP_DAYS" -exec rm -rf {} +
