# 06 · 环境变量清单说明

> 对应产出清单第 6 项。模板见根目录 `.env.example`，复制为 `.env`（被 `.gitignore` 排除，禁止入库）。

## 一、变量清单

### 应用基础
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_ENV` | dev | dev/prod，prod 关闭调试 |
| `APP_NAME` | BJTU-lecture-analy | 应用名 |
| `APP_HOST` / `APP_PORT` | 0.0.0.0 / 8000 | 监听地址 |
| `APP_LOG_LEVEL` | INFO | DEBUG/INFO/WARNING/ERROR |

### 数据库
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | sqlite:///./storage/db/app.db | SQLite 连接串 |

### 安全 / 鉴权
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | change-me... | JWT 签名密钥，生产必换强随机 |
| `JWT_ALGORITHM` | HS256 | JWT 算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 480 | Token 有效期（分钟）|
| `CORS_ORIGINS` | http://localhost:5173 | 跨域白名单，逗号分隔 |

### 本地存储与清理
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `STORAGE_ROOT` | ./storage | 存储根 |
| `VIDEO_CACHE_DIR` | ./storage/videos | 视频缓存 |
| `AUDIO_CACHE_DIR` | ./storage/audios | 音频缓存 |
| `LOG_DIR` | ./storage/logs | 日志目录 |
| `EXPORT_DIR` | ./storage/exports | 导出目录（P1）|
| `CACHE_RETENTION_DAYS` | 7 | 缓存保留天数 |
| `CLEANUP_AUDIO_AFTER_TASK` | true | 任务成功后是否立即删音频 |

### 讯飞 ASR
| 变量 | 说明 |
| --- | --- |
| `XFYUN_APP_ID` / `XFYUN_API_KEY` / `XFYUN_API_SECRET` | 讯飞控制台凭证 |
| `XFYUN_ASR_LANG` | zh-CN（默认）/ en-US |
| `XFYUN_ASR_TIMEOUT` | 单次请求超时（秒）|
| `XFYUN_ASR_MAX_RETRY` | 失败重试次数 |

### 硅基流动大模型
| 变量 | 说明 |
| --- | --- |
| `SILICONFLOW_API_KEY` | API Key |
| `SILICONFLOW_BASE_URL` | https://api.siliconflow.cn/v1 |
| `SILICONFLOW_MODEL` | Qwen/Qwen3-8B |
| `SILICONFLOW_TIMEOUT` / `SILICONFLOW_MAX_RETRY` | 超时与重试 |

### 课程平台对接（北交大 CAS + 平台 API）
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PLATFORM_BASE_URL` | http://123.121.147.7:88 | 北交大课程平台 API 根 |
| `PLATFORM_CAS_LOGIN_URL` | https://cas.bjtu.edu.cn/cas/login | CAS 统一认证登录页 |

> CAS 用户名/密码不在此配置，由用户打开网页后在前端登录页手动输入，通过 API 传给后端 `cas_login(username, password, captcha_code)`。

| `PLATFORM_VIDEO_SERVER` | http://lmt5.bjtu.edu.cn:8880 | 视频流服务器根（HLS m3u8/.ts）|
| `PLATFORM_CAPTCHA_MODE` | manual | 验证码模式：manual（人工输入）/ playwright（自动识别，需装 Playwright）|
| `PLATFORM_COOKIE_TTL` | 3600 | CAS Cookie 有效期（秒），过期自动重新登录 |
| `PLATFORM_VIDEO_FORMATS` | hls,mp4,flv | 优先下载格式（MVP 优先教师流 mp4）|
| `PLATFORM_REQUEST_TIMEOUT` | 60 | 平台 API 请求超时（秒）|

### 任务调度
| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TASK_TOTAL_TIMEOUT` | 3600 | 单任务整体超时（秒）|
| `TASK_MAX_CONCURRENT` | 2 | BackgroundTasks 并发上限 |
| `TIMESTAMP_TOLERANCE_SEC` | 2 | 跳转偏差容忍（NFR-02）|

### 可选：阿里云 OSS
| 变量 | 说明 |
| --- | --- |
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | OSS 凭证 |
| `OSS_ENDPOINT` / `OSS_BUCKET_NAME` | OSS 端点与桶 |
| `OSS_ENABLED` | false，开启后二进制资源上传 OSS |

## 二、安全要求

- `.env` **禁止入库**（已由 `.gitignore` 排除）。
- 生产环境 `SECRET_KEY` 必须替换为强随机值：`python -c "import secrets;print(secrets.token_urlsafe(32))"`。
- `APP_ENV=prod` 时关闭 FastAPI 调试与 `--reload`。
- 凭是 `*_KEY` / `*_SECRET` / `*_TOKEN` 字段，禁止硬编码到代码或提交到仓库。