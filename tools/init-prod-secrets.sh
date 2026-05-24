#!/usr/bin/env bash
# 初始化生产环境密钥到 ./secrets/
# 用法：bash tools/init-prod-secrets.sh
#
# 生成的文件：
#   secrets/postgres_password         - Postgres 密码
#   secrets/database_url              - 完整 asyncpg URL（嵌入密码）
#   secrets/ea_cred_encryption_key    - AES-256-GCM key（base64 32 字节）
#   secrets/jwt_secret_key            - JWT 签名密钥（hex 32 字节）

set -euo pipefail

SECRETS_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets"
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

POSTGRES_USER="${POSTGRES_USER:-bf}"
POSTGRES_DB="${POSTGRES_DB:-bf_manager}"

gen_if_missing() {
    local file="$1"
    local generator="$2"
    if [[ -f "$file" ]]; then
        echo "  [skip] $file already exists"
    else
        eval "$generator" > "$file"
        # 0644：容器里非 root 的 bfm 用户需要读 bind-mount 过来的 secret 文件；
        # 真实的边界由父目录 secrets/ (mode 0700) 把守，外部用户进不了目录
        chmod 644 "$file"
        echo "  [ok] generated $file"
    fi
}

echo "Initializing secrets in $SECRETS_DIR ..."

gen_if_missing "$SECRETS_DIR/postgres_password" \
    "openssl rand -base64 32 | tr -d '/+=' | head -c 32"

POSTGRES_PASSWORD=$(cat "$SECRETS_DIR/postgres_password")
gen_if_missing "$SECRETS_DIR/database_url" \
    "echo -n 'postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}'"

gen_if_missing "$SECRETS_DIR/ea_cred_encryption_key" \
    "openssl rand -base64 32"

gen_if_missing "$SECRETS_DIR/jwt_secret_key" \
    "openssl rand -hex 32"

echo ""
echo "Done. The following files are now in $SECRETS_DIR:"
ls -la "$SECRETS_DIR"
echo ""
echo "IMPORTANT: secrets/ is in .gitignore. Never commit these files."
echo "Back them up securely (e.g., to a password manager or KMS)."
