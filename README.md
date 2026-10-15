# 交大课录智析 · 课程回放 AI 解析平台

> 北京交通大学课程回放 AI 解析平台 MVP。将 60–120 分钟课程回放压缩为 15 分钟高效复习，提供 AI 字幕、重点时间点跳转、分层课程总结、可跳转思维导图。

## 业务目标

把单节 60–120 分钟课程回放，通过 AI 解析转化为：带句级时间戳字幕、重点时间点、分层课程总结、两级可跳转思维导图，让学生点击任意结构化结果即可精准跳回视频对应位置，跳转偏差不超过 2 秒。

## 技术栈（MVP）

| 层 | 技术 |
| --- | --- |
| 前端 | React + TypeScript + Vite + Tailwind CSS + Video.js + markmap |
| 后端 | Python + FastAPI + BackgroundTasks（无重型消息队列）|
| AI 能力 | 讯飞 ASR API（语音转写）+ 硅基流动大模型 API（DeepSeek / Qwen，语义解析）|
| 存储 | SQLite（业务库）+ 本地磁盘（视频/音频缓存，可选阿里云 OSS）|
| 依赖锁定 | 后端 `uv` + `pyproject.toml`；前端 `package-lock.json` |

**无 GPU 依赖**，全部 AI 能力调用外部云 API，普通云服务器即可运行。

## 目录结构

```
BJTU-lecture-analy/
├── docs/          # 参考文档（需求/PPT/架构/数据模型/数据流/P0-P1）
├── backend/       # FastAPI 后端（pyproject.toml + uv 锁定）
├── frontend/      # React 前端（package-lock.json 锁定）
├── storage/       # 运行时数据（db/videos/audios/logs/exports，已 gitignore）
├── .env.example   # 环境变量模板
├── docker-compose.yml
└── README.md
```

完整目录树与模块职责见 [`docs/02-directory-structure.md`](docs/02-directory-structure.md)。

## 快速启动

### 1. 准备环境变量

```bash
cp .env.example .env
# 编辑 .env，填入讯飞 / 硅基流动api
```

### 2. 后端（Python + uv）

```bash
cd backend
uv sync                 # 按 pyproject.toml + uv.lock 安装锁定依赖
uv run python scripts/init_db.py   # 初始化 SQLite 表
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

### 3. 前端（React + Vite）

```bash
cd frontend
npm ci                  # 按 package-lock.json 安装锁定依赖
npm run dev
```

前端：http://localhost:5173

### 4. 一键容器化（可选，保证多电脑环境一致）

```bash
docker compose up --build
```

### 5. Docker 开发环境（推荐：热重载 + 开发工具链）

```bash
# 开发环境（源码挂载 + 热重载 + dev 依赖）
docker compose -f docker-compose.dev.yml up --build
```

- 后端 API：http://localhost:8000/docs（改 `backend/app/` 下 .py 自动重载）
- 前端页面：http://localhost:5173（改 `frontend/src/` 下文件 HMR 即时更新）
- 运行测试：`docker compose -f docker-compose.dev.yml exec backend uv run pytest`
- 代码检查：`docker compose -f docker-compose.dev.yml exec backend uv run ruff check app/`

#### VS Code DevContainer（一键远程开发）

用 VS Code 打开项目根目录 → 提示 **"Reopen in Container"** → 自动安装依赖、扩展、配置。详见 [`.devcontainer/README.md`](.devcontainer/README.md)。

## 环境变量说明

完整清单见 [`.env.example`](.env.example) 与 [`docs/06-env-vars.md`](docs/06-env-vars.md)。关键项：

- `XFYUN_*`：讯飞 ASR 凭证
- `SILICONFLOW_*`：硅基流动大模型凭证与模型选择
- `PLATFORM_*`：北京交通大学课程平台对接（CAS 登录 + API 1/2/3/6，含 `PLATFORM_CAS_LOGIN_URL`/`PLATFORM_VIDEO_SERVER` 等；CAS 用户名/密码由前端登录页输入）
- `SECRET_KEY` / `JWT_*`：鉴权
- `CACHE_RETENTION_DAYS` / `CLEANUP_AUDIO_AFTER_TASK`：缓存自动清理

## MVP 功能（P0）

- 课程回放入口（已授权列表 + 单条人工导入）
- 后台解析任务（下载 → 音频提取降噪 → ASR → 大模型语义解析），状态可见、失败可重试
- AI 字幕（句级时间戳，跳转偏差 ≤ 2 秒）
- 重点时间点（核心概念/公式/例题/考点，点击跳转）
- 分层课程总结（概览/章节要点/重点详解/复习提示）
- 两级思维导图（课程主题—知识模块—知识点，节点可跳转）
- Video.js 播放器（与字幕/重点/导图联动）
- 课程级授权与访问控制
- 结果持久化，刷新不丢失

P1（术语库、导出、检索、笔记、复习题、移动端、反馈入口）**仅预留目录占位，MVP 不编码**，划分见 [`docs/09-p0-p1-roadmap.md`](docs/09-p0-p1-roadmap.md)。

## 部署说明

### 网络环境要求

- **校外部署需 VPN**：北交大使用 **MotionPro**（Array Networks SSL VPN）。
- **前端访问者需在校内网络或 VPN 环境下**：视频流由前端 `<video>` 直连学校服务器，不走本机带宽，但要求访问者网络可达 `lmt5.bjtu.edu.cn`。

### 其他

- SQLite 单文件数据库，位于 `storage/db/app.db`。
- 视频/音频缓存位于 `storage/videos`、`storage/audios`，按 `CACHE_RETENTION_DAYS` 自动清理，任务完成可选立即删除中间音频（`CLEANUP_AUDIO_AFTER_TASK`）。
- 日志独立目录 `storage/logs/`。
- 生产环境务必替换 `SECRET_KEY` 为强随机值，关闭 `--reload`。
- 容器化部署见 `docker-compose.yml`。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/01-architecture.md](docs/01-architecture.md) | 系统分层整体架构图（输入/处理/引擎/输出层）|
| [docs/02-directory-structure.md](docs/02-directory-structure.md) | 完整目录树 + 模块职责 |
| [docs/03-data-model.md](docs/03-data-model.md) | SQLite 表设计 |
| [docs/04-data-flow.md](docs/04-data-flow.md) | 异步解析任务完整数据流 |
| [docs/05-risk-handling.md](docs/05-risk-handling.md) | 风险对应的代码层面处理 |
| [docs/06-env-vars.md](docs/06-env-vars.md) | 环境变量清单说明 |
| [docs/07-dependencies.md](docs/07-dependencies.md) | pyproject.toml / package.json 依赖示例 |
| [docs/08-p0-p1-roadmap.md](docs/08-p0-p1-roadmap.md) | P0/P1 模块划分 |
| [docs/00-requirements-and-product-design.md](docs/00-requirements-and-product-design.md) | 原始需求文档 |
| [docs/10-platform-feasibility-analysis.md](docs/10-platform-feasibility-analysis.md) | 北交大课程平台抓取可行性分析 |

## 核心约束

- 跳转偏差 ≤ 2 秒（NFR-02）
- 单任务失败不干扰其他课程，失败可重试，已缓存结果不丢失（NFR-05/06）
- 课程级授权校验，未授权无法查看视频/转写/解析结果（NFR-07）
- 所有 AI 生成内容记录来源时间戳，前端展示 AI 生成标识
- 思维导图首版仅两级结构，不做跨课程知识图谱