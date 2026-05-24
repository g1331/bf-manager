# ===== 依赖安装阶段 =====
FROM node:20-alpine AS deps

WORKDIR /app

# 启用 corepack 提供 pnpm
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# 只拷依赖描述文件
COPY package.json pnpm-lock.yaml* ./

# 安装生产依赖
RUN pnpm install --frozen-lockfile

# ===== 构建阶段 =====
FROM node:20-alpine AS builder

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# 从 deps 拷贝 node_modules
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# 注入构建期环境变量
ARG NEXT_PUBLIC_DEFAULT_GAME=bf1
ENV NEXT_PUBLIC_DEFAULT_GAME=$NEXT_PUBLIC_DEFAULT_GAME

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN pnpm build

# ===== 运行时阶段 =====
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# 非 root
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# standalone 输出包含运行时所需的最小依赖
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
