/**
 * 从后端 OpenAPI 生成的类型 re-export
 *
 * 生成方式：
 *   1. 起后端：`make dev` 或 `cd apps/backend && uv run uvicorn app.main:app`
 *   2. 跑生成：`bash tools/generate-types.sh` 或 `pnpm --filter @bf-manager/shared-types generate`
 *   3. 提交 `packages/shared-types/src/api.d.ts`
 *
 * 前端使用：
 *   import type { paths, components } from "@bf-manager/shared-types/api";
 *   type ServerSummary = components["schemas"]["ServerSummary"];
 */

export type * from "./api.d.ts";
