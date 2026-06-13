# ===== 构建阶段 =====
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# 先只拷依赖文件，最大化层缓存
COPY pyproject.toml uv.lock* /app/

# 同步依赖（不装项目本身）
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

# 拷源码
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/
# 运维脚本（如 seed_ea_account.py）也需要随镜像分发，便于生产 exec 调用
COPY tools /app/tools

# ===== 运行时阶段 =====
FROM python:3.14-slim AS runtime

# 版本号注入：由 CI 从 git tag 派生（release.yml 的 build-args APP_VERSION=meta.outputs.version）。
# 默认 0.0.0 与 app/core/config.py 的 app_version 字段占位一致，本地直接 docker build 行为不变。
# 运行时 pydantic-settings 以 env source 覆盖字段 app_version，/api/v1/healthz 与 OpenAPI 即显真实版本。
ARG APP_VERSION=0.0.0
ENV APP_VERSION=${APP_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    LOG_LEVEL=INFO

# 运行时只需 ca-certificates（HTTPS 调 EA API）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户
RUN groupadd -r bfm && useradd -r -g bfm -d /app -s /sbin/nologin bfm

WORKDIR /app

# 从 builder 拷贝虚拟环境与代码
COPY --from=builder --chown=bfm:bfm /app /app

USER bfm

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/healthz', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
