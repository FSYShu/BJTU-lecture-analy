# 08 · P0 / P1 模块划分

> 对应产出清单第 9 项。明确标记 P0（MVP 必须实现）与 P1（仅预留目录占位，MVP 不编码实现）。

## 一、P0 必须实现模块（MVP 范围）

| 编号 | 功能 | 后端模块 | 前端模块 |
| --- | --- | --- | --- |
| P0-01 | 课程与回放入口 | `api/v1/courses.py`、`services/course_service.py`、`integrations/platform.py`（CAS 登录 + API 1 课次列表 + API 2 三路流地址 + API 3 平台知识点 + API 6 平台字幕）| `pages/CourseList.tsx` |
| P0-02 | 视频处理任务 | `api/v1/tasks.py`、`services/task_service.py`、`pipeline/steps/download.py`、`audio.py`、`workers/parse_worker.py` | `components/TaskStatus/` |
| P0-03 | AI 字幕 | `api/v1/transcripts.py`、`pipeline/steps/asr.py`、`integrations/siliconflow_asr.py`、`db/models/transcript.py` | `components/Subtitle/` |
| P0-04 | 重点时间点 | `api/v1/keypoints.py`、`pipeline/steps/llm.py`、`db/models/keypoint.py` | `components/Keypoints/` |
| P0-05 | 课程总结 | `api/v1/summaries.py`、`db/models/summary.py` | `components/Summary/` |
| P0-06 | 基硅思维导图 | `api/v1/mindmaps.py`、`db/models/mindmap.py` | `components/Mindmap/`（markmap）|
| P0-07 | 课程播放器 | — | `components/Player/`（Video.js）|
| P0-08 | 结果与异常管理 | `pipeline/steps/persist.py`、`core/exceptions.py`、`pipeline/retry.py` | `components/TaskStatus/`（重试）|
| P0-09 | 基硅权限 | `api/v1/auth.py`、`api/deps.py`、`core/security.py`、`services/auth_service.py`、`services/authorization_service.py`、`db/models/user.py`、`authorization.py` | `pages/Login.tsx`、`pages/AdminAuth.tsx` |
| — | 运维/健康检查 | `api/v1/health.py`、`scripts/init_db.py`、`scripts/cleanup_cache.py`、`core/cleanup.py`、`core/logging.py` | — |
| — | 大模型语义解析 | `integrations/siliconflow_llm.py` | — |
| — | 流水线编排 | `pipeline/orchestrator.py` | — |

## 二、P1 仅预留目录占位（MVP 不编码）

| 编号 | 功能 | 占位位置 |
| --- | --- | --- |
| P1-01 | 术语库与人工校正 | `backend/app/api/v1/p1/terms.py`、`review.py`、`services/p1/term_service.py`、`review_service.py`、`db/models/`（terms/transcript_revisions 表设计见 docs/03）|
| P1-02 | 字幕导出（SRT/VTT）| `backend/app/api/v1/p1/exports.py`、`services/p1/export_service.py`、`frontend/src/components/p1/Export/` |
| P1-03 | 导图导出（MD/图片）| 同 P1-02 |
| P1-04 | 复习题生成 | `backend/app/api/v1/p1/quiz.py`、`services/p1/quiz_service.py`、`frontend/src/components/p1/Quiz/`、`pages/p1/QuizPage.tsx` |
| P1-05 | 课内关键词检索 | `backend/app/api/v1/p1/search.py`、`services/p1/search_service.py`、`frontend/src/components/p1/Search/`、`pages/p1/SearchPage.tsx` |
| P1-06 | 个人笔记与书签 | `backend/app/api/v1/p1/notes.py`、`services/p1/note_service.py`、`frontend/src/components/p1/Note/`、`pages/p1/NotePage.tsx` |
| P1-07 | 移动网页适配 | 前端响应式样式调整（无独立目录，P1 阶段在现有组件上扩展）|
| P1-08 | 用户反馈与建议入口 | `backend/app/services/p1/feedback_service.py`、前端反馈组件（P1 阶段加入）|

### P1 占位文件规范

所有 `p1/` 目录下的占位文件**仅包含模块说明注释**，不实现任何业务逻辑，例如：

```python
# backend/app/api/v1/p1/terms.py
"""P1-01 术语库维护接口（MVP 不实现）。

进入条件：P0 解析结果稳定，并明确校审角色。
对应需求：FR-15 术语库维护 / P1-01。
"""
```

```tsx
// frontend/src/components/p1/Export/index.tsx
// P1-02/03 字幕与导图导出（MVP 不实现）。
// 对应需求：FR-11 字幕与导图导出 / P1-02 / P1-03。
export {};
```

## 三、MVP 范围外（不做占位）

以下能力明确不在首版及 P1 范围，**不预留目录**：

- 直播课堂实时字幕/实时重点/课堂互动
- 跨课程知识图谱、个性化推荐、自动学习路径
- 自动评分、正式成绩联动、未经教师确认的考试题发布
- 情绪/专注度/人脸/课堂行为识别
- 完整原生移动应用、公开社区、弹幕、复杂社交
- 首版即覆盖所有课程平台/所有流媒体协议/所有教务系统接口

## 四、验收对应

P0 验收对应需求文档 US-01 ~ US-06 的全部 AC（课程回放获取/智能解析/重点标注/内容总结/思维导图/AI 字幕）。P1 对应 US-07（字幕样式）/US-08（资料导出）等增强用户故事。