# @bf-manager/shared-types

由后端 FastAPI 的 OpenAPI 定义生成的 TypeScript 类型，供前端 `apps/web` 引用。

## 生成

```bash
# 1. 起后端
make dev

# 2. 生成类型
bash tools/generate-types.sh
# 或者
pnpm --filter @bf-manager/shared-types generate
```

生成结果写到 `src/api.d.ts`。该文件被 git 跟踪，每次后端 schema 改动后应重新生成并提交。

## 使用

```ts
import type { components, paths } from "@bf-manager/shared-types/api";

type ServerSummary = components["schemas"]["ServerSummary"];
type ListServersResponse = paths["/api/v1/bf1/servers"]["get"]["responses"]["200"]["content"]["application/json"];
```

## 状态

当前阶段（MVP 收尾）：包结构与生成脚本就位，但前端 `lib/api/*.ts` 仍是手写类型。
后续迭代中逐步把手写类型替换为生成类型，确保前后端 schema 不会飘。
