# 05 · 风险对应的代码层面处理

> 对应产出清单第 8 项。针对需求文档"风险预估与应对措施"及 NFR，给出具体代码层面的处理提示。

## 一、外部 API 异常降级

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 硅基流动 ASR 超时/中断 | `integrations/siliconflow_asr.py` 设置 `SILICONFLOW_ASR_TIMEOUT`；`pipeline/retry.py` 指数退避重试 `SILICONFLOW_ASR_MAX_RETRY` 次；仍失败则任务 `failed`，`error_code=ASR_TIMEOUT`，保留已下载视频供重试 | integrations + pipeline |
| 硅基流动 LLM 超时/错误 | `integrations/siliconflow_llm.py` 设置 `SILICONFLOW_TIMEOUT`；重试 `SILICONFLOW_MAX_RETRY` 次；降级：若重点/总结/导图任一子任务失败，记录部分失败但任务整体可标记 `failed` 供重试，已生成的部分结果不回滚丢失 | integrations + pipeline |
| 课程平台接口不可达 | `integrations/platform.py` 设置 `PLATFORM_REQUEST_TIMEOUT`；失败标记 `PLATFORM_UNREACHABLE`；MVP 可用单条人工导入替代（FR-01）| integrations |
| API 限流/429 | retry.py 识别 429 状态码，按 `Retry-After` 头等待后重试 | pipeline/retry.py |

**降级原则**：外部 API 异常时保留任务状态与已缓存结果，提示用户重试，不将未完成结果标记为成功（AC-02-06）。

## 二、任务失败重试与失败隔离

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 单任务失败影响其他课程 | `workers/parse_worker.py` 每个任务独立 `try/except`，异常仅更新自身 `parse_tasks` 状态，不抛出到 BackgroundTasks 调度层 | workers |
| 失败可重试 | `POST /api/v1/tasks/{id}/retry` 新建任务，`parent_task_id` 指向原任务；复用已下载视频缓存，从失败步骤重新开始 | api/v1/tasks.py + services/task_service.py |
| 已缓存结果不丢失 | `pipeline/steps/persist.py` 用数据库事务，失败回滚但原任务记录保留；重试新建任务而非覆盖 | pipeline/steps/persist.py |
| 长视频超时 | `TASK_TOTAL_TIMEOUT` 整体超时控制；超时标记 `failed`，`error_code=TOTAL_TIMEOUT` | pipeline/orchestrator.py |
| 并发上限 | `TASK_MAX_CONCURRENT` 限制 BackgroundTasks 并发，超出排队 | config + workers |

## 三、权限鉴权拦截

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 未授权访问课程 | `api/deps.py` 提供 `require_course_access(course_id, user)` 依赖：校验 `course_authorizations` 中 `is_revoked=0 AND now BETWEEN valid_from AND valid_until`，否则 403 | api/deps.py |
| 越权查看视频/转写/解析结果 | 所有 `transcripts/keypoints/summaries/mindmaps` 接口先过 `require_course_access`；查询 SQL 带 `course_id` 过滤，AC-04-06/AC-06-07 保证不返回其他课程数据 | api/v1/* |
| Token 伪造/过期 | `core/security.py` JWT 签发/校验；`SECRET_KEY` 强随机；过期返回 401 | core/security.py |
| 授权撤回 | `authorization_service.revoke()` 置 `is_revoked=1, revoked_at=now`；被撤回课程对学生立即不可见（FR-13）| services/authorization_service.py |
| 角色越权 | 路由级 `require_role('teacher','admin')` 依赖，管理员接口单独校验 | api/deps.py |

## 四、资源清理

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 磁盘被视频/音频缓存撑爆 | `core/cleanup.py` 按 `CACHE_RETENTION_DAYS` 清理过期文件；`scripts/cleanup_cache.py` 手动触发 | core/cleanup.py |
| 中间音频残留 | 任务成功且 `CLEANUP_AUDIO_AFTER_TASK=true` 时立即删除音频；失败任务保留视频供重试 | pipeline + cleanup |
| 日志膨胀 | 日志按大小/时间轮转（logging 配置 RotatingFileHandler），独立目录 `storage/logs/` | core/logging.py |
| 数据库文件膨胀 | SQLite `VACUUM` 可由运维脚本定期执行；WAL 模式自动 checkpoint | scripts/ |

## 五、内容质量与防幻觉

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 大模型生成课程未出现的信息 | `pipeline/steps/llm.py` Prompt 明确"仅基于以下转写文本生成，不得引入外部知识"；结果记录 `source_transcript_ids` 溯源 | pipeline/steps/llm.py |
| AI 内容无标识 | 所有 AI 生成记录 `ai_generated=1, source_model, generated_at`；响应 schema 强制返回这些字段，前端展示"AI 生成"标识 | db/models + schemas + 前端 |
| 重点时间点越界 | 持久化前校验 `0 ≤ timestamp_sec ≤ duration_sec`，越界丢弃并告警（AC-03-03）| pipeline/steps/persist.py |
| 跳转偏差超 2 秒 | ASR 句级时间戳与视频对齐；前端跳转用 `player.currentTime(t)`；`TIMESTAMP_TOLERANCE_SEC=2` 作为校验阈值（NFR-02）| integrations/siliconflow_asr.py + 前端 |

## 六、安全与合规

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| 密钥硬编码 | 全部走 `.env`，`.env` 被 `.gitignore` 排除；`.env.example` 仅占位 | config.py + .gitignore |
| 数据最小化 | 不采集与回放解析无关的学生行为数据（NFR-08）；MVP 不做行为埋点 | — |
| 版权合规 | 只处理已授权课程（`course_authorizations` 校验）；支持有效期与撤回（NFR-12）| authorization_service |
| 日志审计 | 关键操作（登录/授权/撤回/任务创建/重试）写审计日志，含 user_id + 时间 | core/logging.py |
## 七、课程平台与 VPN 对接风险

| 风险 | 代码处理 | 位置 |
| --- | --- | --- |
| CAS 登录验证码 | `PLATFORM_CAPTCHA_MODE=manual` 时日志输出验证码图片路径，等待人工输入；`playwright` 模式用 Playwright 自动识别（需额外安装）；验证码失败重试 3 次后标记 `CAS_CAPTCHA_FAILED` | integrations/platform.py |
| CAS Cookie 过期 | `platform.py` 缓存 Cookie 并记录获取时间，超过 `PLATFORM_COOKIE_TTL` 自动重新登录；API 返回 302 跳转登录页时触发重新登录 | integrations/platform.py |
| VPN 断连（MotionPro）| 平台 API 请求超时/连接失败时标记 `PLATFORM_UNREACHABLE`；运维层面需保证 VPN 拨号脚本存活（systemd/守护进程）| integrations/platform.py |
| 校外访问限制 | 视频流服务器 `lmt5.bjtu.edu.cn:8880` 仅校内可达；前端 `<video>` 直连学校服务器，校外用户无法播放——部署文档需注明"前端访问者需在校内网络或 VPN 环境下" | 前端 + 部署文档 |
| 三路流磁盘占用 | 教师流 mp4 通常 200–500MB/节；`download.py` 下载前检查磁盘可用空间，不足时标记 `DISK_FULL`；`CACHE_RETENTION_DAYS` 定期清理 | pipeline/steps/download.py + core/cleanup.py |
| 平台 IP 并发限制 | `platform.py` 串行调用平台 API（加 asyncio.Lock）；避免短时间大量请求触发平台限流/封禁 | integrations/platform.py |
| 三路流地址失效 | API 2 返回的 HLS 地址可能有时效性；`download.py` 下载失败时重新调用 API 2 刷新地址后重试 | pipeline/steps/download.py |