# 构建 context：monorepo 根（仓库根目录）
# 通过 release.yml 指定 file: ./apps/web/Dockerfile + context: .

# ===== 依赖安装阶段 =====
FROM node:20-alpine AS deps

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# 拷 monorepo 顶层依赖描述 + web 子项目的 package.json
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/

# 只装 web 的依赖（含递归 workspace 依赖）
RUN pnpm install --frozen-lockfile --filter @bf-manager/web...

# ===== 构建阶段 =====
FROM node:20-alpine AS builder

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web ./apps/web

ARG NEXT_PUBLIC_DEFAULT_GAME=bf1
ENV NEXT_PUBLIC_DEFAULT_GAME=$NEXT_PUBLIC_DEFAULT_GAME \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN pnpm --filter @bf-manager/web build

# ===== 运行时阶段 =====
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Next.js monorepo standalone：next.config.ts 里 outputFileTracingRoot 指向仓库根
# 生成的 standalone 目录已经包含 apps/web/server.js + 整个 workspace 的 node_modules 子集
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1

# standalone 模式入口位于 apps/web/server.js（monorepo 路径会保留）
CMD ["node", "apps/web/server.js"]
