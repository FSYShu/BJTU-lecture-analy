# 03 · 关键数据模型设计（SQLite）

> 对应产出清单第 4 项。SQLite 表设计覆盖：用户、课程授权、解析任务、转写字幕、重点时间点、课程总结、思维导图记录。所有 AI 生成内容均记录来源时间戳与 `ai_generated` 标识。

## 一、ER 关系总览

```
users ──< course_authorizations >── courses ──< parse_tasks ──< transcripts
                                       │            │            └── keypoint
                                       │            │            └── summary
                                       │            │            └── mindmap
                                       │            └── (任务状态机)
                                       └── (课程元数据)
```

- 一个 `course` 可被授权给多个 `user`（课程级授权，含有效期/撤回）。
- 一个 `course` 可有多个 `parse_tasks`（重复解析/重试），但同一时刻仅一个进行中。
- 一个 `parse_task` 成功后产出一组 `transcripts`（句级字幕）、`keypoints`（重点）、`summary`（分层总结，单条）、`mindmap`（两级导图，单条）。

## 二、表结构定义

### 1. users — 用户

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK, AUTOINCREMENT | 主键 |
| username | TEXT | UNIQUE, NOT NULL | 登录名（学号/工号）|
| hashed_password | TEXT | NOT NULL | bcrypt 哈希 |
| role | TEXT | NOT NULL, CHECK in ('student','teacher','admin') | 角色 |
| display_name | TEXT | | 姓名 |
| is_active | BOOLEAN | DEFAULT 1 | 是否启用 |
| created_at | DATETIME | DEFAULT now | 创建时间 |

### 2. courses — 课程

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| title | TEXT | NOT NULL | 课程名 |
| teacher_name | TEXT | | 授课教师 |
| session_label | TEXT | | 课次标签（如"第3周第1讲"）|
| duration_sec | INTEGER | | 回放时长（秒）|
| video_url | TEXT | NOT NULL | 视频源地址（MP4/FLV/HLS）|
| video_format | TEXT | CHECK in ('mp4','flv','hls') | 格式 |
| source | TEXT | CHECK in ('platform','manual') | 来源：平台拉取/人工导入 |
| platform_course_id | TEXT | | 课程平台原始 ID（用于去重）|
| created_at | DATETIME | DEFAULT now | |

- 唯一索引：`(platform_course_id)` 用于重复导入识别（FR-01）。
- `platform_course_id` 来源于平台 API 1 返回的 `cId` 字段；`video_url` 来源于 API 2 返回的三路 HLS 地址（MVP 优先教师流）。

### 3. course_authorizations — 课程授权（P0，FR-13）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程 |
| user_id | INTEGER | FK→users.id, NOT NULL | 被授权用户（student）；teacher/admin 默认全权限 |
| granted_by | INTEGER | FK→users.id | 授权人（teacher/admin）|
| valid_from | DATETIME | NOT NULL | 授权生效时间 |
| valid_until | DATETIME | | 授权有效期截止，NULL 表示长期 |
| is_revoked | BOOLEAN | DEFAULT 0 | 是否撤回 |
| revoked_at | DATETIME | | 撤回时间 |
| created_at | DATETIME | DEFAULT now | |

- 复合唯一索引：`(course_id, user_id)`。
- **鉴权查询**：用户访问课程时校验 `is_revoked=0 AND now BETWEEN valid_from AND valid_until`，否则 403（NFR-07）。

### 4. parse_tasks — 解析任务（P0，FR-07/14）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程 |
| initiated_by | INTEGER | FK→users.id | 发起人 |
| status | TEXT | NOT NULL, CHECK in ('queued','downloading','extracting_audio','asr_running','llm_running','persisting','succeeded','failed') | 任务状态机 |
| progress | INTEGER | DEFAULT 0 | 进度百分比 0–100 |
| current_step | TEXT | | 当前执行步骤名 |
| error_code | TEXT | | 失败错误码（如 `ASR_TIMEOUT`、`LLM_ERROR`、`DOWNLOAD_FAIL`）|
| error_message | TEXT | | 失败原因（前端展示）|
| retry_count | INTEGER | DEFAULT 0 | 已重试次数 |
| parent_task_id | INTEGER | FK→parse_tasks.id | 重试任务的父任务（保留原任务记录，NFR-06）|
| video_cache_path | TEXT | | 下载视频本地路径（storage/videos）|
| audio_cache_path | TEXT | | 提取音频本地路径（storage/audios）|
| started_at | DATETIME | | 开始执行时间 |
| finished_at | DATETIME | | 完成/失败时间 |
| created_at | DATETIME | DEFAULT now | |

- 索引：`(course_id, status)`、`(status)` 用于管理员监控。
- **状态机**：`queued → downloading → extracting_audio → asr_running → llm_running → persisting → succeeded`；任一步异常 → `failed`，记录 `error_code/message`，可发起重试（新建任务，`parent_task_id` 指向原任务）。

### 5. transcripts — 转写字幕（P0，FR-03，句级时间戳）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| task_id | INTEGER | FK→parse_tasks.id, NOT NULL | 来源任务 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程（冗余，加速查询）|
| seq_index | INTEGER | NOT NULL | 句序号 |
| text | TEXT | NOT NULL | 句文本 |
| start_sec | REAL | NOT NULL | 句起始时间（秒，浮点）|
| end_sec | REAL | NOT NULL | 句结束时间（秒）|
| ai_generated | BOOLEAN | DEFAULT 1 | AI 生成标识 |
| source_model | TEXT | | 来源模型（如 `xfyun-asr`）|
| generated_at | DATETIME | DEFAULT now | AI 生成时间戳 |
| (P1) revised_text | TEXT | | 人工校正文本（P1-01，MVP 留空）|
| (P1) revised_by | INTEGER | FK→users.id | 校正人（P1）|

- 索引：`(course_id, start_sec)` 用于按播放进度查询当前字幕。
- **跳转约束**：`start_sec` 与原视频时间对齐，偏差 ≤ `TIMESTAMP_TOLERANCE_SEC`（2 秒，NFR-02）。

### 6. keypoints — 重点时间点（P0，FR-04）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| task_id | INTEGER | FK→parse_tasks.id, NOT NULL | 来源任务 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程 |
| seq_index | INTEGER | NOT NULL | 按时间排序序号 |
| title | TEXT | NOT NULL | 重点名称（如"傅里叶变换定义"）|
| category | TEXT | CHECK in ('concept','formula','example','exam_point') | 类型：概念/公式/例题/考点 |
| summary | TEXT | | 一句话摘要 |
| timestamp_sec | REAL | NOT NULL | 对应视频时间点（秒）|
| ai_generated | BOOLEAN | DEFAULT 1 | AI 生成标识 |
| source_model | TEXT | | 来源模型（如 `deepseek-v3`）|
| source_transcript_ids | TEXT | | 关联转写句 ID（JSON 数组，溯源）|
| generated_at | DATETIME | DEFAULT now | |

- 索引：`(course_id, timestamp_sec)`、`(course_id, category)`。
- 约束：`0 ≤ timestamp_sec ≤ courses.duration_sec`（AC-03-03）。
- **平台知识点复用**：平台 API 3 返回的已有知识点（zsd）可直接写入本表，设 `ai_generated=0, source_model='platform-zsd'`，与 LLM 生成的重点（`ai_generated=1, source_model='deepseek-v3'`）并存展示。

### 7. summaries — 课程总结（P0，FR-05，分层）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| task_id | INTEGER | FK→parse_tasks.id, NOT NULL | 来源任务 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程 |
| overview | TEXT | | 课程概览 |
| chapter_points | TEXT | | 章节要点（JSON 数组：[{chapter, points:[]}]) |
| key_details | TEXT | | 重点详解（JSON 数组）|
| review_hints | TEXT | | 复习提示（JSON 数组）|
| ai_generated | BOOLEAN | DEFAULT 1 | AI 生成标识 |
| source_model | TEXT | | 来源模型 |
| generated_at | DATETIME | DEFAULT now | |

- 一个课程一个任务对应一条 summary（最新任务结果覆盖展示）。
- 内容**仅基于本节转写**生成，`source_model` 记录来源，前端展示 AI 标识（防幻觉）。

### 8. mindmaps — 思维导图记录（P0，FR-06，两级）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | INTEGER | PK | 主键 |
| task_id | INTEGER | FK→parse_tasks.id, NOT NULL | 来源任务 |
| course_id | INTEGER | FK→courses.id, NOT NULL | 课程 |
| root_topic | TEXT | NOT NULL | 中心节点：课程主题 |
| nodes | TEXT | NOT NULL | 两级结构 JSON：[{module, knowledge_points:[{name, timestamp_sec}]}] |
| ai_generated | BOOLEAN | DEFAULT 1 | AI 生成标识 |
| source_model | TEXT | | 来源模型 |
| generated_at | DATETIME | DEFAULT now | |

- **两级结构**：课程主题 → 知识模块 → 知识点。知识点可携带 `timestamp_sec`，点击跳转视频。
- 不做跨课程知识图谱（MVP 范围外）。

## 三、P1 扩展表（仅设计，MVP 不建表）

| 表 | 用途 | 对应 P1 |
| --- | --- | --- |
| `terms` | 课程专业术语库 | P1-01 |
| `transcript_revisions` | 转写/重点/总结人工校正记录 | P1-01 |
| `exports` | 导出文件记录（SRT/VTT/MD/图片）| P1-02/03 |
| `notes` / `bookmarks` | 个人笔记与书签 | P1-06 |
| `quizzes` | 复习题（教师确认后发布）| P1-04 |
| `feedbacks` | 用户反馈与建议 | P1-08 |

## 四、初始化与索引

- 建表脚本：`backend/scripts/init_db.py`，使用 `app/db/base.py` 的 metadata.create_all。
- SQLite 启用 `WAL` 模式（`PRAGMA journal_mode=WAL`）提升并发读。
- 关键查询索引已在上表标注，保证按课程 + 时间点查询的低延迟。