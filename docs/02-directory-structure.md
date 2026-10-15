# 02 · 完整项目目录树与模块职责

> 对应产出清单第 2、3 项。目录树区分前端、后端、配置、缓存、参考文档；每个目录/模块说明作用。P1 模块仅预留目录占位，MVP 不编码。

## 一、完整目录树

```
BJTU-lecture-analy/
│
├── docs/                                    # 【参考文档目录】存放全部原始参考资料与设计文档
│   ├── 00-requirements-and-product-design.md   # 原始需求文档
│   ├── 00-requirements-and-product-design.pptx  # 原始 PPT 材料
│   ├── 01-architecture.md                   # 系统分层架构图
│   ├── 02-directory-structure.md            # 本文档：目录树 + 模块职责
│   ├── 03-data-model.md                     # SQLite 表设计
│   ├── 04-data-flow.md                      # 异步解析任务数据流
│   ├── 05-risk-handling.md                  # 风险代码层面处理
│   ├── 06-env-vars.md                       # 环境变量清单说明
│   ├── 07-dependencies.md                   # 依赖示例
│   └── 08-p0-p1-roadmap.md                  # P0/P1 模块划分
│
├── backend/                                 # 【后端目录】Python FastAPI
│   ├── pyproject.toml                       # uv 依赖定义（锁定版本）
│   ├── uv.lock                              # uv 锁文件（提交以保证一致）
│   ├── Dockerfile                           # 后端容器镜像
│   ├── README.md                            # 后端启动说明
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                          # FastAPI 应用入口、路由挂载、CORS、异常处理
│   │   ├── config.py                        # pydantic-settings 配置加载（读 .env）
│   │   │
│   │   ├── core/                            # 【核心基础设施】横切关注点
│   │   │   ├── __init__.py
│   │   │   ├── logging.py                   # 日志配置，输出到 storage/logs
│   │   │   ├── security.py                  # JWT 签发/校验、密码哈希
│   │   │   ├── exceptions.py                # 业务异常定义 + 全局异常处理器
│   │   │   └── cleanup.py                   # 视频/音频缓存自动清理策略
│   │   │
│   │   ├── db/                              # 【数据存储层】
│   │   │   ├── __init__.py
│   │   │   ├── base.py                      # SQLAlchemy Declarative Base
│   │   │   ├── session.py                   # 会话工厂 + get_db 依赖
│   │   │   ├── init_db.py                   # 建表 + 初始管理员
│   │   │   └── models/                      # ORM 模型（见 docs/03-data-model.md）
│   │   │       ├── __init__.py
│   │   │       ├── user.py                  # 用户
│   │   │       ├── course.py                # 课程
│   │   │       ├── authorization.py         # 课程授权（有效期/撤回）
│   │   │       ├── task.py                  # 解析任务
│   │   │       ├── transcript.py            # 转写字幕（句级时间戳）
│   │   │       ├── keypoint.py              # 重点时间点
│   │   │       ├── summary.py               # 课程总结（分层）
│   │   │       └── mindmap.py               # 思维导图记录（两级）
│   │   │
│   │   ├── schemas/                         # 【Pydantic 请求/响应模型】
│   │   │   ├── __init__.py
│   │   │   ├── user.py / course.py / task.py
│   │   │   ├── transcript.py / keypoint.py
│   │   │   └── summary.py / mindmap.py
│   │   │
│   │   ├── api/                             # 【API 路由层】
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                      # 依赖注入：当前用户、课程级权限校验
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py                # 路由聚合
│   │   │       ├── auth.py                  # 登录/Token（P0）
│   │   │       ├── courses.py               # 课程回放入口（P0）
│   │   │       ├── tasks.py                 # 解析任务状态/重试（P0）
│   │   │       ├── transcripts.py           # 字幕查询（P0）
│   │   │       ├── keypoints.py             # 重点时间点查询（P0）
│   │   │       ├── summaries.py             # 课程总结查询（P0）
│   │   │       ├── mindmaps.py              # 思维导图查询（P0）
│   │   │       ├── admin.py                 # 教师/管理员：授权管理/异常处理（P0）
│   │   │       ├── health.py                # 健康检查/最小运维页（P0）
│   │   │       └── p1/                      # 【P1 占位，MVP 不编码】
│   │   │           ├── __init__.py
│   │   │           ├── terms.py             # 术语库维护（P1-01）
│   │   │           ├── review.py            # 结果校审（P1-01）
│   │   │           ├── exports.py           # 字幕/导图导出（P1-02/03）
│   │   │           ├── search.py            # 课内关键词检索（P1-05）
│   │   │           ├── notes.py             # 个人笔记/书签（P1-06）
│   │   │           └── quiz.py              # 复习题生成（P1-04）
│   │   │
│   │   ├── services/                        # 【业务服务层】编排领域逻辑
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py              # 登录/Token 签发（P0）
│   │   │   ├── course_service.py            # 课程列表/导入/元数据（P0）
│   │   │   ├── task_service.py              # 任务创建/状态/重试（P0）
│   │   │   ├── authorization_service.py     # 授权/撤回/有效期校验（P0）
│   │   │   └── p1/                          # 【P1 占位】
│   │   │       ├── term_service.py / review_service.py
│   │   │       ├── export_service.py / search_service.py
│   │   │       ├── note_service.py / quiz_service.py
│   │   │       └── feedback_service.py      # 用户反馈入口（P1-08）
│   │   │
│   │   ├── pipeline/                        # 【解析流水线】核心引擎编排
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py              # 流水线编排：依次调用各 step
│   │   │   ├── retry.py                     # 指数退避重试策略
│   │   │   └── steps/                       # 流水线各阶段
│   │   │       ├── __init__.py
│   │   │       ├── metadata.py              # ① 拉取回放元数据
│   │   │       ├── download.py              # ② 视频下载（MP4/FLV/HLS）
│   │   │       ├── audio.py                 # ③ 音频提取 + 基础降噪（ffmpeg）
│   │   │       ├── asr.py                   # ④ 调用硅基流动 ASR 转写
│   │   │       ├── llm.py                   # ⑤ 调用大模型语义解析
│   │   │       └── persist.py               # ⑥ 持久化结构化结果
│   │   │
│   │   ├── integrations/                    # 【外部 API 客户端】
│   │   │   ├── __init__.py
│   │   │   ├── siliconflow_asr.py           # 硅基流动 ASR（XingChenASR，带时间戳转写）
│   │   │   ├── siliconflow_llm.py           # 硅基流动大模型（DeepSeek/Qwen）
│   │   │   └── platform.py                  # 课程平台对接（CAS 登录 + API 1/2/3/6：课次列表/三路流地址/平台知识点/平台字幕）
│   │   │
│   │   └── workers/                         # 【后台任务】
│   │       ├── __init__.py
│   │       └── parse_worker.py              # BackgroundTasks 入口：执行整条流水线
│   │
│   ├── tests/                               # 后端测试
│   │   ├── __init__.py / conftest.py
│   │   ├── test_api/                        # API 集成测试
│   │   ├── test_pipeline/                   # 流水线单元测试（mock 外部 API）
│   │   └── test_services/                   # 服务层测试
│   └── scripts/                             # 运维脚本
│       ├── init_db.py                       # 初始化数据库
│       └── cleanup_cache.py                 # 手动触发缓存清理
│
├── frontend/                                # 【前端目录】React + Vite + TS
│   ├── package.json                         # npm 依赖定义
│   ├── package-lock.json                    # npm 锁文件（提交）
│   ├── tsconfig.json / vite.config.ts
│   ├── tailwind.config.js / postcss.config.js
│   ├── Dockerfile                           # 前端容器镜像（构建后 nginx 托管）
│   ├── index.html
│   ├── public/                              # 静态资源
│   └── src/
│       ├── main.tsx                         # 应用入口
│       ├── App.tsx                          # 路由根
│       ├── api/                             # API 客户端（axios 封装）
│       │   ├── client.ts                    # axios 实例 + 拦截器（Token/错误）
│       │   ├── courses.ts / tasks.ts
│       │   ├── transcripts.ts / keypoints.ts
│       │   └── summaries.ts / mindmaps.ts
│       ├── components/                      # 通用组件
│       │   ├── Player/                      # Video.js 播放器封装（P0）
│       │   ├── Subtitle/                    # 字幕组件（开关/字号/联动）（P0）
│       │   ├── Keypoints/                   # 重点时间点列表（P0）
│       │   ├── Summary/                     # 分层课程总结（P0）
│       │   ├── Mindmap/                     # markmap 思维导图渲染（P0）
│       │   ├── TaskStatus/                  # 任务状态/重试（P0）
│       │   ├── Layout/                      # 页面布局/导航（P0）
│       │   └── p1/                          # 【P1 占位】
│       │       ├── Export/                  # 导出（P1-02/03）
│       │       ├── Search/                  # 课内检索（P1-05）
│       │       ├── Note/                    # 笔记/书签（P1-06）
│       │       └── Quiz/                    # 复习题（P1-04）
│       ├── pages/                           # 页面
│       │   ├── Login.tsx                    # 登录（P0）
│       │   ├── CourseList.tsx               # 课程回放列表（P0）
│       │   ├── CourseDetail.tsx             # 课程详情：播放+字幕+重点+总结+导图（P0）
│       │   ├── AdminAuth.tsx                # 教师/管理员授权管理（P0）
│       │   └── p1/                          # 【P1 占位】
│       │       ├── ExportPage.tsx / SearchPage.tsx
│       │       └── NotePage.tsx / QuizPage.tsx
│       ├── hooks/                           # 自定义 hooks（usePlayer/useTask...）
│       ├── store/                           # 状态管理（zustand）
│       ├── types/                           # TS 类型定义
│       ├── utils/                           # 工具函数（时间格式化/跳转校验）
│       └── styles/                          # 全局样式 + Tailwind 入口
│
├── storage/                                 # 【缓存/运行时目录】整体 gitignore
│   ├── db/                                  # SQLite 数据库文件（*.db 排除）
│   │   └── .gitkeep
│   ├── videos/                              # 下载的视频缓存（排除）
│   │   └── .gitkeep
│   ├── audios/                              # 提取的音频缓存（排除）
│   │   └── .gitkeep
│   ├── logs/                                # 日志目录（排除）
│   │   └── .gitkeep
│   └── exports/                             # 导出文件（P1，排除）
│       └── .gitkeep
│
├── .env.example                             # 环境变量模板（提交）
├── .gitignore                               # 忽略规则
├── docker-compose.yml                       # 一键容器化
└── README.md                                # 项目总说明
```

## 二、模块职责划分

### 顶层
| 目录/文件 | 作用 |
| --- | --- |
| `docs/` | 全部原始参考资料（需求/PPT）+ 设计文档，供开发查阅，不参与运行 |
| `backend/` | FastAPI 后端，承载全部业务逻辑、解析流水线、外部 API 调用 |
| `frontend/` | React 前端，承载播放器、字幕、重点、总结、导图展示与跳转联动 |
| `storage/` | 运行时数据（数据库/视频/音频/日志/导出），整体被 `.gitignore` 排除，仅保留 `.gitkeep` 占位 |
| `.env.example` | 环境变量模板，复制为 `.env` 使用 |
| `docker-compose.yml` | 一键复现前后端环境，保证多电脑一致 |

### backend 内部
| 模块 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 入口，挂载路由、CORS、全局异常处理、日志初始化 |
| `app/config.py` | 用 pydantic-settings 从 `.env` 加载配置，类型校验 |
| `app/core/` | 横切关注点：日志、鉴权、异常、缓存清理 |
| `app/db/` | SQLAlchemy 会话与 ORM 模型，对应 SQLite 表 |
| `app/schemas/` | Pydantic 请求/响应模型，与 ORM 解耦 |
| `app/api/` | REST 路由 + 依赖注入（当前用户、课程级权限校验）|
| `app/services/` | 业务编排：任务创建、授权校验、状态流转 |
| `app/pipeline/` | 解析流水线核心：`orchestrator` 依次调度 `steps/`，`retry` 提供重试 |
| `app/integrations/` | 外部 API 客户端封装，隔离第三方 SDK 细节 |
| `app/workers/` | BackgroundTasks 入口，单任务独立执行，失败隔离 |
| `tests/` | API/流水线/服务层测试，外部 API 一律 mock |
| `scripts/` | 运维脚本：建库、清理缓存 |

### frontend 内部
| 模块 | 职责 |
| --- | --- |
| `api/` | axios 封装，统一 Token 注入与错误处理 |
| `components/Player/` | Video.js 封装，暴露 `currentTime(t)` 供跳转 |
| `components/Subtitle/` | 字幕渲染，按播放进度联动，支持开关/字号 |
| `components/Keypoints/` | 重点时间点列表，点击调用 `player.currentTime` |
| `components/Summary/` | 分层总结展示（概览/章节/重点详解/复习提示）|
| `components/Mindmap/` | markmap 渲染两级导图，节点点击跳转 |
| `pages/` | 路由页面：登录/列表/详情/管理员授权 |
| `hooks/` | `usePlayer`、`useTask` 等复用逻辑 |
| `store/` | zustand 全局状态（用户/当前课程）|

## 三、P0 / P1 目录标记

- **P0（MVP 必须实现）**：上述所有非 `p1/` 目录。
- **P1（仅预留占位，MVP 不编码）**：所有 `p1/` 子目录，包括 `backend/app/api/v1/p1/`、`backend/app/services/p1/`、`frontend/src/components/p1/`、`frontend/src/pages/p1/`。每个 P1 占位文件仅含模块说明注释，不实现逻辑。

详细 P0/P1 划分见 `docs/08-p0-p1-roadmap.md`。