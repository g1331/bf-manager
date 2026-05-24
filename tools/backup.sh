#!/usr/bin/env bash
# 备份 Postgres 数据库到 ./backups/<date>/
# 用法：bash tools/backup.sh [compose-file]
#
# 默认使用 docker-compose.prod.yml；传入 docker-compose.yml 可备份开发库

set -euo pipefail

COMPOSE_FILE="${1:-docker-compose.prod.yml}"
DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$(cd "$(dirname "$0")/.." && pwd)/backups/$DATE"

mkdir -p "$BACKUP_DIR"

POSTGRES_USER="${POSTGRES_USER:-bf}"
POSTGRES_DB="${POSTGRES_DB:-bf_manager}"

echo "Backing up $POSTGRES_DB to $BACKUP_DIR ..."

docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
    | gzip > "$BACKUP_DIR/${POSTGRES_DB}.sql.gz"

echo ""
echo "Backup saved: $BACKUP_DIR/${POSTGRES_DB}.sql.gz"
du -h "$BACKUP_DIR/${POSTGRES_DB}.sql.gz"

# 保留最近 14 天备份
find "$(dirname "$BACKUP_DIR")" -maxdepth 1 -type d -name "20*" -mtime +14 -exec rm -rf {} \; 2>/dev/null || true
