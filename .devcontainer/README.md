# 交大课录智析 · DevContainer

## 一键开发环境

克隆仓库后，用 VS Code 打开项目根目录，按提示选择 **"Reopen in Container"** 即可。

或手动操作：
1. 安装 [Dev Containers 扩展](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`

## 包含

- Python 3.12 + uv（后端依赖自动安装）
- Node 20 + npm（前端依赖自动安装）
- Playwright + Chromium（CAS 登录）
- ffmpeg（音视频处理）
- pytest / ruff / mypy（开发工具链）
- VS Code 扩展自动安装（Python / Ruff / ESLint / Tailwind 等）

## 端口

| 服务 | 端口 | 说明 |
|---|---|---|
| 后端 API | 8000 | http://localhost:8000/docs |
| 前端 Dev | 5173 | http://localhost:5173 |

## 热重载

- 后端：修改 `backend/app/` 下任意 .py 文件，uvicorn 自动重载
- 前端：修改 `frontend/src/` 下任意文件，Vite HMR 即时更新

## 不用 VS Code 也能开发

```bash
# 启动开发环境
docker compose -f docker-compose.dev.yml up --build

# 后端测试
docker compose -f docker-compose.dev.yml exec backend uv run pytest

# 后端 lint
docker compose -f docker-compose.dev.yml exec backend uv run ruff check app/

# 前端 lint
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit
```