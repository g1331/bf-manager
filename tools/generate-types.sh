#!/usr/bin/env bash
# 从后端 OpenAPI 生成 TypeScript 类型
# 用法：
#   make dev  # 先起后端
#   bash tools/generate-types.sh

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
OUTPUT_FILE="packages/shared-types/src/api.d.ts"

mkdir -p "$(dirname "$OUTPUT_FILE")"

echo "Fetching OpenAPI from $BACKEND_URL/api/v1/openapi.json ..."

if ! command -v pnpm >/dev/null 2>&1; then
    echo "ERROR: pnpm is required"
    exit 1
fi

pnpm dlx openapi-typescript@latest "$BACKEND_URL/api/v1/openapi.json" \
    -o "$OUTPUT_FILE" \
    --enum

echo ""
echo "Generated $OUTPUT_FILE"
echo "Run 'git diff $OUTPUT_FILE' to review changes."
