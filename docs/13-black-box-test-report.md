# 13 · 核心功能模块黑盒测试报告

| 项目 | 内容 |
|---|---|
| 被测系统 | 交大课录智析（BJTU-lecture-analy）后端 |
| 测试类型 | 黑盒测试（等价类划分 + 边界值分析） |
| 测试边界 | HTTP API（FastAPI TestClient），外部依赖（SSO/VE 平台、ASR/LLM、解析线程）在系统边界打桩 |
| 测试环境 | Windows 11 / Python 3.14.3 / uv 虚拟环境 / pytest 9.1.1 / 内存 SQLite |
| 用例规模 | 88 条（满足 30–1000 要求） |
| 执行结果 | 通过 80，失败 8（对应 5 个真实 BUG） |
| 用例代码 | `backend/tests/test_blackbox/test_core_modules.py` |
| 执行命令 | `cd backend && uv run --extra dev pytest tests/test_blackbox -q` |

---

## 1. 核心功能模块需求 / 设计描述

### 1.1 认证模块（/api/v1/auth）

| 端点 | 需求描述 |
|---|---|
| POST /auth/login | 用户名+密码登录。验证通过签发 JWT（含 sub=用户 id、role），返回 token 与用户信息；用户名不存在与密码错误返回一致的 401 提示（防用户枚举）；缺字段返回 422 |
| GET /auth/me | 凭 `Authorization: Bearer <token>` 返回当前用户。无头/非 Bearer 前缀/伪造或过期 token/用户已禁用或已删除均返回 401 |

### 1.2 课程模块（/api/v1/courses）

| 端点 | 需求描述 |
|---|---|
| GET /courses | 教师/管理员可见全部课程；学生仅见有效授权（未撤销、valid_from 已生效、未过期）的课程 |
| GET /courses/{course_key} | course_key 格式为 `{课程号}-{课序号后两位}`。课程不存在或未授权统一返回 404（不泄露存在性） |
| POST /courses/import | 教师手工导入课程（title、video_url 必填，duration_sec 等可选），source=manual，返回 201 |
| POST /courses/{course_key}/parse | 对课程发起 AI 解析。前置校验：AI 凭证缺失→400 AI_CREDENTIALS_MISSING；无视频地址→400 VIDEO_URL_MISSING；成功后创建 queued 任务返回 201 并异步执行流水线 |

### 1.3 解析任务模块（/api/v1/tasks）

| 端点 | 需求描述 |
|---|---|
| GET /tasks/{task_id} | 查询任务详情；不存在返回 404；非数字 id 返回 422 |
| GET /tasks/latest | 按 lecture_id 或 course_id 查最新任务；无任务返回 404 |
| GET /tasks/{task_id}/stream | SSE 推送任务进度；任务不存在必须先返回 404（不能返回 200+错误帧） |
| POST /tasks/{task_id}/retry | 仅 failed 任务可重试（否则 422 TASK_NOT_RETRYABLE）；新建 queued 任务，retry_count+1，指向父任务并继承视频/音频缓存 |
| POST /tasks/{task_id}/cancel | 取消进行中任务：标记 failed + error_code=CANCELLED 并终止子进程；已 succeeded/failed 的任务幂等返回、不改状态 |

### 1.4 解析结果模块（/api/v1/lectures、/api/v1/courses/{id}/...）

| 端点 | 需求描述 |
|---|---|
| GET /lectures/{id}/transcripts、keypoints | 返回列表；无数据返回 200 空数组 |
| GET /lectures/{id}/summary、mindmap | 未生成返回 404 与可读提示；已生成返回最新一条 |
| GET /lectures/{id}/overview | 首屏聚合接口：字幕元信息/重点/总结/导图/最新任务一次返回；未生成部分为 null 而非 404 |
| 权限 | 均要求课程级授权（teacher/admin 或有效 CourseAuthorization）；回放不存在返回 404，未授权返回 403 |

### 1.5 授权管理模块（/api/v1/admin）

| 端点 | 需求描述 |
|---|---|
| GET /admin/authorizations | 教师/管理员查看授权列表；学生 403，未登录 401 |
| POST /admin/authorizations | 授权学生访问课程（可选 valid_until 有效期），返回 201；授权立即生效 |
| POST /admin/authorizations/{id}/revoke | 撤销授权，立即生效；授权不存在返回 404 AUTH_NOT_FOUND |
| GET /admin/tasks/failed | 查看全部失败任务及错误码 |

### 1.6 平台对接模块（/api/v1/platform）

| 端点 | 需求描述 |
|---|---|
| POST /platform/sso-login | SSO 统一身份认证（主入口，无验证码）。成功按学号 upsert 用户（role=teacher）、持久化平台 cookies、签发 JWT；重复登录不重复建号；平台认证失败返回 502 及错误码 |
| POST /platform/sync-courses | 凭已存 cookies 从 VE 平台同步课程（按 platform_course_id 去重 upsert）；无 cookies 返回 400 NO_PLATFORM_COOKIES |
| GET /platform/courses/{key}/replays | 拉取回放列表并落库 Lecture，标注 has_result 与最新任务状态；课程缺 cId 返回 400 NO_COURSE_ID |
| POST .../replays/{id}/stream | 获取视频流地址；已缓存且未强制刷新时直接返回缓存（不调浏览器）；force=true 重新取流并落库 |
| POST .../replays/{id}/parse | 取流并发起解析（前置校验同 1.2 parse） |

---

## 2. 等价类划分及边界值分析

### 2.1 登录输入

| 输入 | 有效等价类 | 无效等价类 | 边界值 |
|---|---|---|---|
| username | 已注册（A-01） | 未注册（A-03）、缺失（A-05）、空串（A-06，长度 0） | 长度 0 |
| password | 正确（A-01） | 错误（A-02）、缺失（A-04）、空串（A-06） | 长度 0 |
| 请求体 | 完整 JSON | 空对象 {}（A-07） | — |

### 2.2 JWT / Authorization 头

| 输入 | 有效等价类 | 无效等价类 | 边界值 |
|---|---|---|---|
| 头存在性 | Bearer + 有效 token（A-08） | 无头（A-09）、非 Bearer 前缀（A-10） | — |
| token | 未过期（A-08） | 签名篡改（A-11）、过期（A-12）、sub 用户不存在（A-14） | exp = now−1s（过期下边界）；`"Bearer "` 后空串（A-15） |
| 用户状态 | is_active=true | is_active=false（A-13） | — |

### 2.3 course_key

| 等价类 | 用例 |
|---|---|
| 合法 `{num}-{seq}` 且存在 | C-07 |
| 格式合法但不存在 | C-08 |
| 无连字符（格式边界） | C-09 |
| 课程无 course_num/fz_id（手工课程） | C-10 |
| 存在但未授权（学生） | C-11 |

### 2.4 课程导入字段

| 输入 | 有效等价类 | 无效等价类 | 边界值 |
|---|---|---|---|
| title | 非空（C-12） | 缺失（C-13）、空串（C-15） | 长度 0 |
| video_url | 非空 URL（C-12） | 缺失（C-14） | — |
| duration_sec | 正整数、缺省 null | 负数（C-16） | -1（负数上边界） |

### 2.5 task_id 与任务状态机

| 输入 | 等价类 | 边界值 |
|---|---|---|
| task_id | 存在（T-01）/ 不存在（T-02）/ 非数字（T-04） | id=0（T-03，自增下界之下） |
| retry × 状态 | failed 可重试（T-08）；succeeded（T-09）/queued（T-10）不可；不存在（T-11） | — |
| cancel × 状态 | queued 可取消（T-12）；succeeded（T-13）/failed（T-14）幂等；不存在（T-15） | 终态边界 |
| latest 参数 | lecture_id / course_id / 均无（T-07） | 无参数 |

### 2.6 课程授权（有效期维度）

| 等价类 | 用例 | 边界值 |
|---|---|---|
| 无授权 | C-02、R-06、R-07 | — |
| 有效授权（valid_until 为 null，永久） | C-03、M-04 | — |
| 已撤销 | C-04、M-05 | — |
| 未过期 | M-08 | valid_until = now+7d |
| 已过期 | C-05、M-09 | valid_until = now−1s（过期上边界） |

### 2.7 平台对接

| 输入 | 有效等价类 | 无效等价类 |
|---|---|---|
| SSO 凭证 | 正确→建号/更新（P-01/02） | 错误→502（P-03）、缺字段→422（P-04） |
| 平台 cookies | 存在（P-06/10/12） | 缺失→400 NO_PLATFORM_COOKIES（P-05/09） |
| platform_c_id | 存在 | 缺失→400 NO_COURSE_ID（P-08） |
| lecture.video_url 缓存 | 有→直接用缓存（P-11）；force=true→重新取流（P-12） | 课程不存在→404（P-13） |

---

## 3. 测试用例设计与执行结果

共 88 条用例，全部实现为可重复执行的 pytest 用例（用例编号见代码 docstring）。

| 模块 | 用例编号 | 数量 | 通过 | 失败 |
|---|---|---|---|---|
| 健康检查 | TC-H-01 | 1 | 1 | 0 |
| 认证 | TC-A-01 ~ A-15 | 15 | 15 | 0 |
| 课程 | TC-C-01 ~ C-22 | 22 | 19 | 3 |
| 任务 | TC-T-01 ~ T-18 | 18 | 16 | 2 |
| 解析结果 | TC-R-01 ~ R-10 | 10 | 10 | 0 |
| 授权管理 | TC-M-01 ~ M-09 | 9 | 7 | 2 |
| 平台对接 | TC-P-01 ~ P-13 | 13 | 12 | 1 |
| **合计** | | **88** | **80** | **8** |

执行输出：

```
8 failed, 80 passed, 8 warnings in 81.88s
FAILED TC-C-05  test_list_courses_student_expired_grant
FAILED TC-C-15  test_import_course_empty_title
FAILED TC-C-16  test_import_course_negative_duration
FAILED TC-C-22  test_parse_student_unauthorized_course
FAILED TC-T-16  test_get_task_student_cross_course
FAILED TC-T-17  test_cancel_student_cross_course
FAILED TC-M-08  test_grant_future_valid_until
FAILED TC-M-09  test_grant_expired_valid_until
```

---

## 4. BUG 分析与整改计划

8 个失败用例归因于 **5 个真实 BUG**（4.1–4.5），均已定位到具体代码。

### 4.1 BUG-01：授权过期后学生仍能看到课程（TC-C-05）

- **现象**：授权 `valid_until` 已过期，学生 `GET /courses` 仍列出该课程；预期空列表，实际 200 含课程。
- **根因**：`course_service.list_accessible_courses` 与 `get_accessible_course`（backend/app/services/course_service.py:9-42）只过滤 `is_revoked` 和 `valid_from`，**未过滤 `valid_until`**；而 `require_course_access`（deps.py:55）检查了 `valid_until`。同一授权存在两种判定口径，课程元信息越权可见（结果数据仍被拦）。
- **严重度**：中（越权范围限于课程元信息）。
- **整改**：两处查询补充 `valid_until IS NULL OR valid_until > now` 条件，与 `require_course_access` 口径统一；以 TC-C-05 作为回归用例。

### 4.2 BUG-02：课程导入缺少业务校验（TC-C-15、TC-C-16）

- **现象**：`title=""`、`duration_sec=-1` 均返回 201 成功落库；预期 422。
- **根因**：`CourseImportIn`（backend/app/schemas/course.py:24-30）仅有类型约束，无 `min_length`/`ge` 等业务约束；`import_course` 也未做二次校验。
- **严重度**：低（脏数据进入库，影响展示与解析前置判断）。
- **整改**：schema 加约束——`title: str = Field(min_length=1, max_length=255)`、`video_url: str = Field(min_length=1)`、`duration_sec: int | None = Field(default=None, ge=0)`。

### 4.3 BUG-03：学生可对未授权课程发起解析（TC-C-22）

- **现象**：未授权学生 `POST /courses/M1001-01/parse` 返回 201 并创建解析任务；预期 403/404。
- **根因**：`start_parse`（backend/app/api/v1/courses.py:38-46）仅校验登录，**未做课程授权校验**，与 `get_course`（同文件 22-30 行有校验）不一致。平台侧 `parse_replay`（platform.py:300）同样无校验。
- **严重度**：高（横向越权 + 直接消耗 ASR/LLM 计费额度）。
- **整改**：在两个 parse 端点引入 `require_course_access`（teacher/admin 或有效授权学生）校验；以 TC-C-22 回归。

### 4.4 BUG-04：任务查询/取消/重试无越权校验（TC-T-16、TC-T-17）

- **现象**：学生对未授权课程的任务 `GET /tasks/{id}` 返回 200、`POST /tasks/{id}/cancel` 返回 200 且任务被实际取消（状态变 failed/CANCELLED）；预期 403/404。
- **根因**：`get_task` / `cancel_task` / `retry_task`（backend/app/api/v1/tasks.py:42-91）只校验登录与任务存在性，未按 `task.course_id` 做课程授权校验。cancel 具有破坏性（可终止他人正在运行的解析）。
- **严重度**：高（越权读取 + 越权破坏性操作）。
- **整改**：三个端点按 `task.course_id` 调用 `require_course_access`；以 TC-T-16/17 回归。

### 4.5 BUG-05：带有效期的授权导致 500 内部错误（TC-M-08、TC-M-09）

- **现象**：授权含 `valid_until` 时，学生访问任何课程资源均返回 `500 INTERNAL_ERROR`；预期未过期 200 / 已过期 403。有效期功能完全不可用。
- **根因**：SQLite 的 `DateTime` 读回为 **naive datetime**（不带时区），而 `require_course_access`（backend/app/api/deps.py:55）将其与 `datetime.now(timezone.utc)`（aware）比较：`auth.valid_until < now` 抛出 `TypeError: can't compare offset-naive and offset-aware datetimes`，被全局异常处理器兜成 500。
- **严重度**：高（功能不可用 + 500 暴露内部实现）。
- **整改**：比较前归一化时区，例如 `vu = auth.valid_until.replace(tzinfo=timezone.utc) if auth.valid_until.tzinfo is None else auth.valid_until`；或统一在模型层使用 `DateTime(timezone=True)`/自定义 UTCDateTime 类型；以 TC-M-08/09 回归。

### 4.6 整改计划汇总

| 编号 | 严重度 | 整改项 | 涉及文件 | 回归用例 | 优先级 |
|---|---|---|---|---|---|
| BUG-03 | 高 | parse 端点补课程授权校验 | api/v1/courses.py、api/v1/platform.py | TC-C-22 | P0 |
| BUG-04 | 高 | 任务读/取消/重试补课程授权校验 | api/v1/tasks.py | TC-T-16/17 | P0 |
| BUG-05 | 高 | 授权有效期时区归一化 | api/deps.py（或 db 模型层） | TC-M-08/09 | P0 |
| BUG-01 | 中 | 课程列表/详情查询补 valid_until 过滤 | services/course_service.py | TC-C-05 | P1 |
| BUG-02 | 低 | 导入 schema 加业务约束 | schemas/course.py | TC-C-15/16 | P2 |

**验证方式**：整改完成后重跑 `uv run --extra dev pytest tests/test_blackbox -q`，88 条用例应全部通过；BUG 对应用例从失败转通过即视为修复闭环。

---

## 5. 附：测试说明

- **打桩边界**：`app.integrations.platform`（SSO 登录、课程同步、回放列表、取流）与解析 worker 线程在系统边界打桩，硅基流动 API Key 等配置经 monkeypatch 注入；被测系统内部不做任何 mock，符合黑盒原则。
- **数据隔离**：每条用例使用独立内存 SQLite（StaticPool），互不影响，可重复执行。
- **遗留观察项（非 BUG）**：pydantic v2 `class Config` 弃用警告 ×6（建议迁移 `ConfigDict`）；`TaskOut` 不暴露 `parent_task_id`/缓存路径属设计取舍，缓存继承正确性经 DB 侧断言验证（TC-T-08）。
