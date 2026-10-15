# ============================================================
# 交大课录智析 · 前端 Dockerfile
# 多阶段构建：Node 构建 → nginx 提供静态文件 + API 反代
# ============================================================

# ---- 阶段 1：构建 React 产物 ----
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# VITE_API_BASE_URL 在构建时注入；生产环境前端通过 nginx 反代 /api，故设为相对路径
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ---- 阶段 2：nginx 提供静态文件 + API 反代 ----
FROM nginx:alpine

# 自定义 nginx 配置（API 反代到后端）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]