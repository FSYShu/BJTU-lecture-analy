# ============================================================
# 交大课录智析 · 后端 Dockerfile
# 基于 uv + FastAPI + Playwright（CAS 登录）
# ============================================================

FROM python:3.12-slim AS base

# 系统依赖：ffmpeg（音视频处理）+ Playwright Chromium 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    # Playwright Chromium 依赖
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# uv 安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依赖层（利用 Docker 缓存：仅 pyproject.toml/uv.lock 变化时重建）
COPY pyproject.toml uv.lock ./
COPY README.md ./
RUN uv sync --frozen --no-dev

# Playwright 浏览器安装（Chromium）
RUN uv run playwright install chromium

# 应用代码
COPY app ./app
COPY scripts ./scripts

# 运行时环境
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=prod
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]