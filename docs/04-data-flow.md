# 04 · 异步解析任务完整数据流

> 对应产出清单第 5 项。描述从拉取回放元数据到持久化全部结构化结果的端到端数据流，含状态流转、失败隔离、重试与缓存清理。

## 一、触发入口

```
学生/管理员 → POST /api/v1/courses/{id}/parse
            → task_service.create_task(course_id, user_id)
            → 写入 parse_tasks(status='queued')
            → BackgroundTasks.add_task(parse_worker.run, task_id)
            → 立即返回 {task_id, status:'queued'}（前端轮询/SSE 查进度）
```

- 使用 FastAPI `BackgroundTasks`（MVP 不引入 RabbitMQ/Redis）。
- 同一课程若已有进行中任务，拒绝重复创建并提示。

## 二、流水线六步数据流

`parse_worker.run(task_id)` 调用 `pipeline/orchestrator.py`，依次执行 `pipeline/steps/` 六个步骤。每步更新 `parse_tasks.status` 与 `current_step`，任一步异常 → `failed`。

```
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1  拉取回放元数据   pipeline/steps/metadata.py                  │
│   输入: course_id                                                      │
│   前置: 若服务器在校外，先 MotionPro VPN 按需拨号连入校园网            │
│   动作: integrations/platform.py                                       │
│         ① cas_login() → Playwright 登录 CAS，导出 Cookie 给 httpx      │
│         ② list_replay_courses() API1 拉课次列表(cId→platform_course_id)│
│         ③ get_stream_map()   API2 取三路 HLS(教师/学生/课件)           │
│   产物: course 元数据更新到 courses 表；video_url=教师流 HLS           │
│   状态: queued → (校验通过)                                            │
│   失败: CAS_FAIL / PLATFORM_UNREACHABLE → failed                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 2  视频下载        pipeline/steps/download.py                   │
│   输入: 教师流 HLS URL (teaStreamHlsUrl，三路中音轨最清晰)             │
│   动作: ffmpeg-python 拉 HLS → storage/videos/{task_id}.mp4            │
│         (学生/课件流 MVP 不下载；课件流 P1 可截图做重点配图)           │
│   产物: video_cache_path                                              │
│   状态: → downloading                                                  │
│   失败: DOWNLOAD_FAIL / DOWNLOAD_TIMEOUT → failed                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 3  音频提取+降噪    pipeline/steps/audio.py                      │
│   输入: video_cache_path (教师流 mp4)                                 │
│   动作: ffmpeg 抽 16kHz 单声道 wav + highpass/afftdn 降噪             │
│         → storage/audios/{task_id}.wav                                │
│   产物: audio_cache_path                                              │
│   状态: → extracting_audio                                            │
│   失败: AUDIO_EXTRACT_FAIL → failed                                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 4  讯飞 ASR 转写    pipeline/steps/asr.py                        │
│   输入: audio_cache_path                                              │
│   动作: 调用 integrations/xfyun_asr.py，输出句级时间戳转写             │
│   产物: List[{seq_index, text, start_sec, end_sec}]                    │
│   状态: → asr_running                                                  │
│   重试: pipeline/retry.py 指数退避，最多 XFYUN_ASR_MAX_RETRY 次        │
│   失败: ASR_TIMEOUT / ASR_ERROR → failed                               │
│   降级: 多次重试仍失败 → 标记 failed，保留已下载视频，提示用户重试      │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 5  大模型语义解析   pipeline/steps/llm.py                        │
│   输入: 转写文本（按时间分段）                                         │
│   动作: 调用 integrations/siliconflow_llm.py，并行/串行生成：          │
│         - 重点时间点（concept/formula/example/exam_point）             │
│         - 分层课程总结（概览/章节要点/重点详解/复习提示）               │
│         - 两级思维导图（主题—模块—知识点，节点带时间戳）               │
│   约束: 仅基于本节转写生成；每条结果记录 source_model + generated_at   │
│   产物: keypoints / summary / mindmap 结构化对象                       │
│   状态: → llm_running                                                  │
│   重试: 最多 SILICONFLOW_MAX_RETRY 次                                  │
│   失败: LLM_TIMEOUT / LLM_ERROR → failed                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Step 6  持久化结构化结果 pipeline/steps/persist.py                    │
│   输入: 转写 + 重点 + 总结 + 导图                                      │
│   动作: 事务写入 transcripts / keypoints / summaries / mindmaps       │
│         全部带 ai_generated=1, source_model, generated_at              │
│   状态: → persisting → succeeded                                       │
│   失败: PERSIST_FAIL → 回滚，标记 failed，已下载视频不删除             │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
                    任务完成，触发缓存清理
```

## 三、状态机

```
queued ──→ downloading ──→ extracting_audio ──→ asr_running ──→ llm_running ──→ persisting ──→ succeeded
   │            │                │                   │                │               │
   └────────────┴────────────────┴───────────────────┴────────────────┴───────────────┴──→ failed
                                                                                    │
                                                              用户发起重试 → 新建任务(parent_task_id=原任务)
```

- 状态查询接口：`GET /api/v1/tasks/{id}` 返回 `status/progress/current_step/error_code/error_message`。
- 失败任务**不影响其他课程**：每个 BackgroundTasks 任务独立 try/except，异常仅更新自身状态（NFR-05/06）。

## 四、失败重试

```
学生 → POST /api/v1/tasks/{id}/retry
      → 校验原任务 status='failed'
      → 新建 parse_tasks(status='queued', parent_task_id=原任务.id, retry_count=原任务.retry_count+1)
      → BackgroundTasks.add_task(parse_worker.run, new_task_id)
```

- 重试复用已下载的视频/音频缓存（若仍存在），跳过 Step 1/2/3，从失败步骤重新开始。
- 原失败任务记录保留，不丢失（NFR-06）。

## 五、缓存清理策略

| 时机 | 动作 | 配置 |
| --- | --- | --- |
| 任务成功且 `CLEANUP_AUDIO_AFTER_TASK=true` | 立即删除 `storage/audios/{task_id}.wav` | `.env` |
| 任务成功 | 保留视频缓存（供重试/再解析），按保留天数清理 | `CACHE_RETENTION_DAYS` |
| 定时/手动 `scripts/cleanup_cache.py` | 清理超过 `CACHE_RETENTION_DAYS` 的 videos/audios/exports | `CACHE_RETENTION_DAYS` |
| 任务失败 | **不删除**已下载视频，供重试复用 | — |

- 清理逻辑在 `app/core/cleanup.py`，日志记录删除文件。
- 已持久化到 SQLite 的解析结果**不受缓存清理影响**，刷新页面不丢失（FR-08）。

## 六、前端联动数据流

```
GET /api/v1/courses/{id}/transcripts   → 字幕列表（按 start_sec）
GET /api/v1/courses/{id}/keypoints     → 重点列表（按 timestamp_sec）
GET /api/v1/courses/{id}/summary       → 分层总结
GET /api/v1/courses/{id}/mindmap       → 两级导图
```

前端 Video.js 播放器监听 `timeupdate`，按当前进度高亮字幕/重点；用户点击字幕句/重点/导图节点 → `player.currentTime(t)`，偏差 ≤ 2 秒。所有 AI 内容展示 `AI 生成` 标识。