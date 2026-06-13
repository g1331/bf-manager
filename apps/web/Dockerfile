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
# next.config.ts 的 rewrites() 在构建阶段被调用一次，结果会被烘焙到
# .next/routes-manifest.json / required-server-files.json / server.js 里，
# 运行时不会再重新求值。默认指向 compose 服务名 backend，让任何 docker-compose
# 形态（含没有外部反代的 dev 栈）都能正常代理 /api/v1/* → backend:8000。
# prod 走 host openresty 在 web 容器前面拦截 /api/v1/*，Next.js 的 rewrite
# 实际是死代码，这个默认值对其无影响。
ARG BACKEND_API_URL=http://backend:8000
# 版本号注入：由 CI 从 git tag 派生（release.yml 的 build-args NEXT_PUBLIC_APP_VERSION=meta.outputs.version）。
# NEXT_PUBLIC_ 前缀在构建阶段被内联进 client bundle，运行时不可再改；默认 0.0.0 表示开发版。
# 与后端镜像注入的 APP_VERSION 取同一 metadata.version，保证前后端版本号统一。
ARG NEXT_PUBLIC_APP_VERSION=0.0.0
ENV NEXT_PUBLIC_DEFAULT_GAME=$NEXT_PUBLIC_DEFAULT_GAME \
    BACKEND_API_URL=$BACKEND_API_URL \
    NEXT_PUBLIC_APP_VERSION=$NEXT_PUBLIC_APP_VERSION \
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

# BusyBox wget 解析 localhost 时优先走 IPv6 (::1)，但 Next.js standalone
# 仅监听 HOSTNAME=0.0.0.0 的 IPv4，会拿到 Connection refused 误判 unhealthy。
# 显式用 127.0.0.1 强制走 IPv4。
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/ || exit 1

# standalone 模式入口位于 apps/web/server.js（monorepo 路径会保留）
CMD ["node", "apps/web/server.js"]
