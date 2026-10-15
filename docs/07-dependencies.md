# 07 · 核心依赖示例

> 对应产出清单第 7 项。后端 `pyproject.toml`（uv 锁定）与前端 `package.json`（npm 锁定）关键依赖示例。实际文件见 `backend/pyproject.toml` 与 `frontend/package.json`。

## 一、后端 pyproject.toml（uv 锁定）

```toml
[project]
name = "bjtu-lecture-analy-backend"
version = "0.1.0"
description = "交大课录智析后端 - 课程回放AI解析平台"
requires-python = ">=3.11"
readme = "README.md"

# 全部依赖锁定版本范围，uv.lock 锁定精确版本保证多电脑一致
dependencies = [
    # Web 框架
    "fastapi>=0.115,<0.116",
    "uvicorn[standard]>=0.32,<0.33",
    # 配置
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.6,<3",
    # 数据库 ORM
    "sqlalchemy>=2.0,<3",
    # 鉴权
    "passlib[bcrypt]>=1.7,<2",
    "python-jose[cryptography]>=3.3,<4",
    # HTTP 客户端（调用硅基流动 ASR/LLM/课程平台）
    "httpx>=0.27,<0.28",
    # 视频/音频处理
    "ffmpeg-python>=0.2,<0.3",
    # 日志
    "loguru>=0.7,<0.8",
    # 工具
    "python-multipart>=0.0.9",   # FastAPI 表单/文件上传
    "tenacity>=8.2,<9",          # 重试策略
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "pytest-asyncio>=0.24,<0.25",
    "pytest-cov>=5,<6",
    "httpx>=0.27,<0.28",         # 测试客户端
    "respx>=0.21,<0.22",         # mock httpx
    "ruff>=0.7,<0.8",
    "mypy>=1.13,<2",
]
captcha = [
    "playwright>=1.48,<2",       # CAS 验证码自动识别（PLATFORM_CAPTCHA_MODE=playwright 时启用）
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**锁定方式**：
```bash
cd backend
uv sync                 # 按 pyproject.toml + uv.lock 安装
uv add <pkg>            # 新增依赖会更新 uv.lock
uv lock --upgrade       # 升级锁
```
`uv.lock` **必须提交**，保证不同开发电脑依赖完全一致。

## 二、前端 package.json（npm 锁定）

```json
{
  "name": "bjtu-lecture-analy-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext ts,tsx",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0",
    "axios": "^1.7.7",
    "video.js": "^8.21.0",
    "markmap-lib": "^0.18.11",
    "markmap-view": "^0.18.0",
    "zustand": "^5.0.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "tailwindcss": "^3.4.14",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.13.0",
    "@typescript-eslint/eslint-plugin": "^8.11.0",
    "@typescript-eslint/parser": "^8.11.0"
  }
}
```

**锁定方式**：
```bash
cd frontend
npm ci                  # 按 package-lock.json 精确安装（CI/多电脑一致）
npm install <pkg>       # 新增依赖会更新 package-lock.json
```
`package-lock.json` **必须提交**。

## 三、外部运行时依赖（非包管理）

| 依赖 | 用途 | 部署要求 |
| --- | --- | --- |
| ffmpeg | 视频音频提取与降噪 | 容器内安装；本地开发需系统安装 ffmpeg |
| SQLite | 业务数据库 | Python 内置 sqlite3，无需单独部署 |
| Playwright（可选）| CAS 验证码自动识别 | `uv add playwright && uv run playwright install chromium`；仅 `PLATFORM_CAPTCHA_MODE=playwright` 时需要 |

`docker-compose.yml` 对应的 `backend/Dockerfile` 需 `apt-get install -y ffmpeg`。