# MVP 未实现内容与实现方案

> 基于当前项目骨架盘点，按前端、纯后端、AI 相关后端三类分类，给出每项的实现方案。

---

## 〇、开发环境部署

### 方式一：Docker 开发环境（推荐）

```bash
git clone <repo>
cd BJTU-lecture-analy
cp .env.example .env          # 填入讯飞/硅基流动 API 凭证
docker compose -f docker-compose.dev.yml up --build
```

- 后端 API：http://localhost:8000/docs（改 `backend/app/` 下 .py 自动重载）
- 前端页面：http://localhost:5173（改 `frontend/src/` 下文件 HMR 即时更新）
- 运行测试：`docker compose -f docker-compose.dev.yml exec backend uv run pytest`
- 代码检查：`docker compose -f docker-compose.dev.yml exec backend uv run ruff check app/`

### 方式二：VS Code DevContainer

用 VS Code 打开项目根目录 → 提示 **"Reopen in Container"** → 自动安装依赖、扩展、配置。详见 [`.devcontainer/README.md`](../.devcontainer/README.md)。

### 方式三：本地直接运行

```bash
# 后端
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端（另开终端）
cd frontend
npm ci
npm run dev
```

### 方式四：Docker 生产部署

```bash
cp .env.example .env          # 填入真实值，替换 SECRET_KEY
docker compose up --build -d
# 后端 API: http://localhost:8000/api/v1
# 前端页面: http://localhost:3000
```

---

## 一、前端

### F1：Player 视频地址硬编码空串

- **位置**：`frontend/src/pages/CourseDetail.tsx:30`
- **现状**：`<Player src="" onTimeUpdate={setCurrentSec} />`，src 固定为空串
- **方案**：CourseDetail 增加 course 数据获取，将 `course.video_url` 传入 Player

```tsx
const [course, setCourse] = useState<Course | null>(null);
useEffect(() => { getCourse(courseId).then(setCourse).catch(() => {}); }, [courseId]);
// 渲染时
<Player src={course?.video_url || ''} onTimeUpdate={setCurrentSec} />
```

- **前置**：`api/courses.ts` 需补充 `getCourse(id)` 单条查询封装

### F2：点击跳转不工作（onSeek 未传入）

- **位置**：`frontend/src/pages/CourseDetail.tsx:31-36`
- **现状**：Subtitle/Keypoints/Mindmap 组件均接受 `onSeek` prop，但 CourseDetail 未传入
- **方案**：通过 SeekContext 将 Player 的 seek 函数传递给子组件

```tsx
// CourseDetail.tsx
import { useContext } from 'react';
import { SeekContext } from '@/components/Player';

// 在 Player 子树内
const seek = useContext(SeekContext);
<Subtitle transcripts={transcripts} currentSec={currentSec} onSeek={seek} />
<Keypoints keypoints={keypoints} onSeek={seek} />
<MindmapView mindmap={mindmap} onSeek={seek} />
```

### F3：SeekContext.Provider 渲染空子节点

- **位置**：`frontend/src/components/Player/index.tsx:29`
- **现状**：`<SeekContext.Provider value={seek}>{null}</SeekContext.Provider>`，子组件无法消费
- **方案**：Player 接受 `children`，用 SeekContext 包裹

```tsx
interface PlayerProps {
  src: string;
  onTimeUpdate?: (t: number) => void;
  children?: React.ReactNode;
}
// 渲染时
{ready && <SeekContext.Provider value={seek}>{children}</SeekContext.Provider>}
```

CourseDetail 改为将 Subtitle/Keypoints/Summary/Mindmap 作为 Player 的 children 或在 Player 外层用 SeekContext.Provider 包裹。

### F4：开始解析无反馈

- **位置**：`frontend/src/pages/CourseList.tsx:20`
- **现状**：`onClick={() => startParse(c.id)}`，调用后无 loading/toast/跳转
- **方案**：加 loading 状态 + 调用后跳转到 CourseDetail 展示进度

```tsx
const [loadingId, setLoadingId] = useState<number | null>(null);
const navigate = useNavigate();
onClick={async () => {
  setLoadingId(c.id);
  try {
    const res = await startParse(c.id);
    navigate(`/courses/${c.id}`);
  } finally { setLoadingId(null); }
}}
// 按钮文本: {loadingId === c.id ? '解析中...' : '开始解析'}
```

### F5：CourseDetail 未展示解析进度

- **位置**：`frontend/src/pages/CourseDetail.tsx`
- **现状**：已导入 `useTask` hook 但未使用，TaskStatus 组件未渲染
- **方案**：CourseDetail 获取最新 task 并渲染 TaskStatus

```tsx
const [taskId, setTaskId] = useState<number | null>(null);
const task = useTask(taskId);
// useEffect 中获取课程最新 task: getLatestTask(courseId).then(t => setTaskId(t?.id ?? null))
// 渲染
<TaskStatus task={task ?? undefined} onRetry={() => startParse(courseId).then(r => setTaskId(r.id))} />
```

- **前置**：`api/tasks.ts` 需补充 `getLatestTask(courseId)` 封装；后端 `api/v1/tasks.py` 需补充按 courseId 查最新 task 的端点

### F6：未获取 course.video_url

- **位置**：`frontend/src/pages/CourseDetail.tsx`
- **现状**：只获取了 transcripts/keypoints/summary/mindmap，未获取 course 本身
- **方案**：同 F1，增加 `getCourse(courseId)` 调用

### 4.0 当前问题盘点

| # | 问题 | 位置 | 严重度 |
|---|---|---|---|
| U0 | `App.tsx` 未用 `Layout` 包裹路由，无全局 header/nav | `App.tsx` | 高 |
| U1 | `Course` 类型缺 `video_url`/`platform_course_id` 字段 | `types/index.ts:8-16` | 高 |
| U2 | Tailwind config 无自定义主题（配色/间距/字体均默认） | `tailwind.config.js` | 中 |
| U3 | 无加载/空状态/错误状态的统一组件 | 全局 | 中 |
| U4 | 无 toast/通知系统，`alert()` 原始弹窗 | `AdminAuth.tsx:11`、`CourseList.tsx` | 中 |
| U5 | 无响应式断点处理，小屏不可用 | 全局 | 低（MVP 桌面优先） |
| U6 | 无暗色模式 | 全局 | 低（P1） |

### 4.1 设计基础

#### 4.1.1 配色方案（Tailwind 主题扩展）

```js
// tailwind.config.js — theme.extend.colors
colors: {
  primary: {
    50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
    400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb',  // 主按钮/链接
    700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
  },
  accent: {
    500: '#8b5cf6', 600: '#7c3aed',  // AI 生成内容标识
  },
  success: { 500: '#22c55e', 600: '#16a34a' },  // 任务完成
  warning: { 500: '#f59e0b', 600: '#d97706' },  // 重试/注意
  danger:  { 500: '#ef4444', 600: '#dc2626' },  // 失败/错误
},
```

- 主色 `primary-600` (#2563eb)：按钮、链接、活跃状态
- AI 标识 `accent-500` (#8b5cf6)：AI 生成内容的角标/标签
- 中性色用 Tailwind 默认 `gray` 系列

#### 4.1.2 间距与圆角

| 用途 | 值 | 说明 |
|---|---|---|
| 页面外边距 | `px-6 py-4` (24px/16px) | 桌面端页面容器 |
| 卡片内边距 | `p-4` (16px) | 带边框的内容区块 |
| 紧凑内边距 | `p-3` (12px) | 列表项、小卡片 |
| 组件间距 | `gap-4` / `space-y-4` | 同级组件垂直间距 |
| 卡片圆角 | `rounded-lg` (8px) | 边框容器 |
| 按钮圆角 | `rounded-md` (6px) | 按钮、输入框 |
| 小标签圆角 | `rounded` (4px) | badge、tag |

#### 4.1.3 字体

| 层级 | class | 用途 |
|---|---|---|
| 页面标题 | `text-2xl font-bold` | "课程回放列表"、"课程详情" |
| 区块标题 | `text-lg font-semibold` | "课程概览"、"重点列表" |
| 小节标题 | `text-base font-semibold` | Summary 内 "章节要点" |
| 正文 | `text-sm` (14px) | 列表项、描述文字 |
| 辅助文字 | `text-xs text-gray-500` | 时间戳、来源标识 |
| AI 角标 | `text-[10px] text-accent-500` | "AI" 小标签 |

#### 4.1.4 阴影与边框

| 用途 | class |
|---|---|
| 卡片 | `border border-gray-200 rounded-lg` |
| 悬浮卡片 | `shadow-md` (hover 时) |
| 弹出层 | `shadow-lg` |
| 输入框 | `border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500` |

---

### 4.2 页面路由层级

```
App.tsx（修复：用 Layout 包裹全部路由）
└── Layout（全局 header + nav + main + footer）
    ├── /                       → CourseList      （课程列表页）
    ├── /login                  → Login           （登录页，无 header）
    ├── /courses/:id            → CourseDetail    （课程详情页）
    └── /admin/auth             → AdminAuth       （授权管理页，仅 admin）
```

**修复方案（U0）**：

```tsx
// App.tsx
import Layout from './components/Layout';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/" element={<CourseList />} />
        <Route path="/courses/:id" element={<CourseDetail />} />
        <Route path="/admin/auth" element={<AdminAuth />} />
      </Route>
    </Routes>
  );
}
```

**修复方案（U1）**：

```ts
// types/index.ts — Course 补充字段
export interface Course {
  id: number;
  title: string;
  teacher_name?: string;
  session_label?: string;
  duration_sec?: number;
  video_url?: string;           // 新增：教师流 HLS 地址
  video_format?: string;
  platform_course_id?: string;  // 新增：平台 cId
  source: string;
}
```

---

### 4.3 Layout 布局

```
┌─────────────────────────────────────────────────────┐
│ Header (h-14, border-b, sticky top-0, bg-white)     │
│ ┌─────────────────┐         ┌──────────────────┐   │
│ │ 交大课录智析      │         │ 课程列表 授权管理  │   │
│ │ (font-bold)      │         │ (text-sm)         │   │
│ └─────────────────┘         └──────────────────┘   │
├─────────────────────────────────────────────────────┤
│ Main (flex-1, p-6, bg-gray-50)                      │
│ ┌─────────────────────────────────────────────────┐ │
│ │                                                 │ │
│ │              <Outlet /> 页面内容                 │ │
│ │                                                 │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ Footer (h-10, border-t, text-xs text-gray-400)      │
│ "AI 生成内容仅供参考" · 版本号                       │
└─────────────────────────────────────────────────────┘
```

```tsx
// Layout/index.tsx — 详细样式
<div className="min-h-screen flex flex-col bg-gray-50">
  <header className="h-14 border-b border-gray-200 bg-white sticky top-0 z-50 flex items-center justify-between px-6">
    <Link to="/" className="text-lg font-bold text-gray-800">交大课录智析</Link>
    <nav className="flex items-center gap-6 text-sm">
      <Link to="/" className="text-gray-600 hover:text-primary-600 transition-colors">课程列表</Link>
      {user?.role === 'admin' && (
        <Link to="/admin/auth" className="text-gray-600 hover:text-primary-600 transition-colors">授权管理</Link>
      )}
      {user && (
        <button onClick={logout} className="text-gray-400 hover:text-danger-600">退出</button>
      )}
    </nav>
  </header>
  <main className="flex-1 p-6"><Outlet /></main>
  <footer className="h-10 border-t border-gray-200 bg-white flex items-center justify-center text-xs text-gray-400">
    AI 生成内容仅供参考 · v0.1.0
  </footer>
</div>
```

---

### 4.4 各页面详细布局

#### 4.4.1 Login 页

```
┌─────────────────────────────────┐
│         (mt-32 居中)             │
│  ┌─────────────────────────┐    │
│  │  交大课录智析 (logo)     │    │
│  │  text-2xl font-bold     │    │
│  ├─────────────────────────┤    │
│  │  ┌───────────────────┐  │    │
│  │  │ 用户名            │  │    │
│  │  └───────────────────┘  │    │
│  │  ┌───────────────────┐  │    │
│  │  │ 密码              │  │    │
│  │  └───────────────────┘  │    │
│  │  ┌───────────────────┐  │    │
│  │  │      登录          │  │    │  bg-primary-600 text-white
│  │  └───────────────────┘  │    │
│  └─────────────────────────┘    │
│  max-w-sm, shadow-lg, p-8       │
└─────────────────────────────────┘
```

- 全屏背景 `bg-gray-100`，卡片 `bg-white shadow-lg rounded-xl p-8`
- 输入框：`w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500`
- 登录按钮：`w-full bg-primary-600 text-white rounded-md py-2.5 font-medium hover:bg-primary-700 transition-colors`
- 加载态：按钮禁用 + 文字变 "登录中..." + `animate-pulse`
- 错误态：输入框下方 `text-sm text-danger-600` 错误提示

#### 4.4.2 CourseList 页

```
┌─────────────────────────────────────────────────────┐
│  课程回放列表  (text-2xl font-bold mb-6)             │
│                                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │  高等数学 · 第3讲          [开始解析]           │  │
│  │  张教授 · 2024-03-15       (text-blue-600)     │  │
│  ├───────────────────────────────────────────────┤  │
│  │  线性代数 · 第5讲          [开始解析]           │  │
│  │  李教授 · 2024-03-14                          │  │
│  ├───────────────────────────────────────────────┤  │
│  │  ...                                          │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  每项: border rounded-lg p-4 hover:shadow-md        │
│  transition-shadow                                  │
└─────────────────────────────────────────────────────┘
```

- 列表项：`border border-gray-200 rounded-lg p-4 flex items-center justify-between hover:shadow-md transition-shadow cursor-pointer`
- 课程标题：`font-medium text-gray-800`
- 副信息：`text-sm text-gray-500`
- "开始解析"按钮：`text-sm text-primary-600 hover:text-primary-700 hover:underline`
- 加载态：`animate-pulse` 骨架屏（3 个灰色块）
- 空状态：居中 `text-gray-400` "暂无课程回放"

#### 4.4.3 CourseDetail 页（核心页面）

```
┌─────────────────────────────────────────────────────┐
│  ← 返回列表   高等数学 · 第3讲   [TaskStatus]        │
│  (text-2xl)   (text-gray-500)                        │
├─────────────────────────────────────────────────────┤
│ ┌──────────────────────────┐  ┌──────────────────┐ │
│ │                          │  │  重点列表         │ │
│ │     Video.js Player      │  │  (Keypoints)      │ │
│ │     (16:9, col-span-2)   │  │  h-64 overflow    │ │
│ │                          │  │  scroll-y         │ │
│ │                          │  ├──────────────────┤ │
│ ├──────────────────────────┤  │  课程总结         │ │
│ │  字幕 (Subtitle)          │  │  (Summary)        │ │
│ │  h-48 overflow-auto       │  │  概览/章节/详解   │ │
│ │  当前句 bg-primary-100    │  ├──────────────────┤ │
│ │  点击 → seek(t)           │  │  思维导图         │ │
│ └──────────────────────────┘  │  (Mindmap)        │ │
│                                │  h-96 svg         │ │
│                                │  节点点击 → seek  │ │
│                                └──────────────────┘ │
│  grid grid-cols-3 gap-6        col-span-1          │
│  左侧 col-span-2               col-span-1          │
└─────────────────────────────────────────────────────┘
```

**详细样式**：

```tsx
<div className="space-y-6">
  {/* 顶部标题栏 */}
  <div className="flex items-center justify-between">
    <div className="flex items-center gap-4">
      <Link to="/" className="text-gray-400 hover:text-gray-600">← 返回</Link>
      <h1 className="text-2xl font-bold">{course?.title}</h1>
      <span className="text-sm text-gray-500">{course?.teacher_name} · {course?.session_label}</span>
    </div>
    {task && <TaskStatus task={task} onRetry={handleRetry} />}
  </div>

  {/* 主体三栏布局 */}
  <div className="grid grid-cols-3 gap-6">
    {/* 左侧：播放器 + 字幕 */}
    <div className="col-span-2 space-y-4">
      <div className="border border-gray-200 rounded-lg overflow-hidden bg-black">
        <Player src={course?.video_url || ''} onTimeUpdate={setCurrentSec}>
          {/* children 在 SeekContext 内 */}
        </Player>
      </div>
      <Subtitle transcripts={transcripts} currentSec={currentSec} onSeek={seek} />
    </div>

    {/* 右侧：重点 + 总结 + 导图 */}
    <div className="col-span-1 space-y-4">
      <Keypoints keypoints={keypoints} onSeek={seek} />
      {summary && <SummaryView summary={summary} />}
      {mindmap && <MindmapView mindmap={mindmap} onSeek={seek} />}
    </div>
  </div>
</div>
```

**加载态**：各区域独立 `animate-pulse` 骨架屏，不互相阻塞
**空状态**：对应区域显示 `text-gray-400 text-sm` "暂无字幕"/"暂无重点"/"暂无总结"

#### 4.4.4 AdminAuth 页

```
┌─────────────────────────────────────────┐
│  课程授权管理  (text-2xl font-bold)      │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │  授权列表 (表格)                   │  │
│  │  课程 │ 学生 │ 状态 │ 操作          │  │
│  │  ...  │ ...  │ 有效  │ 撤销         │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │  新增授权                          │  │
│  │  [课程 ID] [学生 ID] [授权]        │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

- 表格：`w-full border-collapse`，表头 `bg-gray-50 text-sm text-gray-600`
- 输入框组：`flex gap-3 items-end`
- 授权按钮：`bg-primary-600 text-white rounded-md px-4 py-2`
- 撤销按钮：`text-sm text-danger-600 hover:underline`
- 成功/失败反馈：toast 通知（替代 `alert()`）

---

### 4.5 各组件详细样式

#### 4.5.1 Player（视频播放器）

```
┌──────────────────────────────────────┐
│                                      │
│        Video.js 16:9 播放器           │
│        (fluid: true)                 │
│                                      │
│  ── ── ── ── ── ── ── ── ── ── ──   │  控制栏（Video.js 默认）
│  ▶  00:12 / 45:30    🔊  ⛶  ⤢       │
└──────────────────────────────────────┘
外层: border rounded-lg overflow-hidden bg-black
```

- 容器：`border border-gray-200 rounded-lg overflow-hidden bg-black`
- Video.js 自带控制栏，无需自定义
- `SeekContext` 包裹 `children`，提供 `seek(t)` 函数
- src 为空时显示占位：`flex items-center justify-center h-64 text-gray-400 "暂无视频"`

#### 4.5.2 Subtitle（字幕）

```
┌──────────────────────────────────────┐
│  字幕                          [开关] │  header: flex justify-between
├──────────────────────────────────────┤
│  12:30  今天我们讲傅里叶变换          │  ← 当前句 bg-primary-100
│  15:20  首先回顾上节课的内容           │
│  18:45  傅里叶变换的定义是...    [AI]  │  ← AI 生成有角标
│  ...                                  │
│  h-48 overflow-y-auto                 │  固定高度，可滚动
└──────────────────────────────────────┘
```

- 容器：`border border-gray-200 rounded-lg`
- 头部：`flex items-center justify-between px-4 py-2 border-b`，标题 `text-sm font-medium`，开关用 `<button>`
- 列表区：`h-48 overflow-y-auto p-2`
- 每条字幕：`cursor-pointer px-2 py-1 rounded hover:bg-gray-100`
- 当前句：`bg-primary-100`（高亮）
- 时间戳：`text-xs text-gray-500` + `formatTime()`
- AI 角标：`ml-1 text-[10px] text-accent-500 bg-accent-50 px-1 rounded`
- 点击：`onSeek(t.start_sec)` 跳转播放器
- 自动滚动到当前句：`useEffect` + `scrollIntoView({ behavior: 'smooth' })`

#### 4.5.3 Keypoints（重点列表）

```
┌──────────────────────────────────────┐
│  重点列表                              │  header
├──────────────────────────────────────┤
│  12:30  [概念]  傅里叶变换定义    [AI]  │
│         将周期函数表示为...             │  summary (text-sm text-gray-600)
│  ──────────────────────────────────  │  border-b
│  18:45  [考点]  傅里叶系数公式        │
│         a₀ = (1/T)∫f(t)dt              │
│  ──────────────────────────────────  │
│  25:10  [例题]  求方波的傅里叶级数     │
│  ...                                  │
│  h-64 overflow-y-auto                 │
└──────────────────────────────────────┘
```

- 容器：`border border-gray-200 rounded-lg`
- 头部：`px-4 py-2 border-b text-sm font-medium "重点列表"`
- 列表区：`h-64 overflow-y-auto`
- 每条：`cursor-pointer py-2 px-4 border-b last:border-0 hover:bg-gray-50`
- 时间戳：`text-xs text-primary-600 font-medium`
- 分类标签：`text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600`
  - concept→"概念"(bg-blue-50 text-blue-600)
  - formula→"公式"(bg-purple-50 text-purple-600)
  - example→"例题"(bg-green-50 text-green-600)
  - exam_point→"考点"(bg-orange-50 text-orange-600)
- 标题：`font-medium text-gray-800`
- 摘要：`text-sm text-gray-600 mt-1`
- AI 角标：同 Subtitle
- 空状态：`text-gray-400 p-4 text-center "暂无可用重点"`

#### 4.5.4 Summary（分层总结）

```
┌──────────────────────────────────────┐
│  课程总结                         [AI] │
├──────────────────────────────────────┤
│  ▸ 课程概览                           │  section
│    本节课介绍了傅里叶变换的基本概念...  │  text-sm text-gray-700
│                                       │
│  ▸ 章节要点                           │  section
│    • 傅里叶级数定义                    │  list-disc
│    • 傅里叶变换性质                    │
│    • 典型信号变换                      │
│                                       │
│  ▸ 重点详解                           │  section
│    • 奇偶函数的傅里叶系数简化           │
│    • Parseval 定理的物理意义           │
│                                       │
│  ▸ 复习提示                           │  section
│    • 重点掌握傅里叶系数求解             │
│    • 理解频谱的物理意义                 │
└──────────────────────────────────────┘
```

- 容器：`border border-gray-200 rounded-lg p-4 space-y-4`
- AI 角标：右上角 `text-xs text-accent-500`
- 每个 section：`<section>` + `<h3 className="font-semibold text-base mb-1">` + 内容
- 概览：`text-sm text-gray-700 leading-relaxed`
- 列表：`text-sm list-disc pl-5 space-y-1 text-gray-700`
- 可折叠（MVP 可选）：`<details>` 原生折叠，`<summary>` 为标题

#### 4.5.5 Mindmap（思维导图）

```
┌──────────────────────────────────────┐
│  思维导图                         [AI] │
├──────────────────────────────────────┤
│         ┌── 傅里叶级数定义             │
│         │   ├── 狄利克雷条件 @12:30    │  ← 点击 seek
│ 概念    │   └── 收敛性 @15:20          │
│  │      │                             │
│  ├── 性质│── 线性性质 @18:45           │
│  │      │   时移性质 @20:10           │
│  │      └── 频移性质 @22:30           │
│  │                                    │
│  └── 应用── 信号滤波 @25:10           │
│           频谱分析 @28:30             │
│                                       │
│  svg: w-full h-96                     │  markmap 渲染
└──────────────────────────────────────┘
```

- 容器：`border border-gray-200 rounded-lg p-2`
- AI 角标：`text-xs text-accent-500 mb-1`
- SVG：`w-full h-96`，markmap 自动布局
- 节点点击：解析 `@timestamp` 后调用 `onSeek(timestamp)`
- 两级结构：root_topic → module → knowledge_points（MVP 限制两级）
- 空状态：`text-gray-400 p-4 text-center "暂无思维导图"`

#### 4.5.6 TaskStatus（任务状态）

```
正常进度:
┌──────────────────────────────────┐
│  语音识别中              45%      │  text-sm font-medium
│  ████████████░░░░░░░░░░░░░░░     │  h-2 bg-gray-200, inner bg-primary-500
└──────────────────────────────────┘

失败:
┌──────────────────────────────────┐
│  失败                    [重试]    │  text-danger-600
│  ████████░░░░░░░░░░░░░░░░░░░     │
│  ASR 转写超时，请重试              │  text-sm text-danger-600
└──────────────────────────────────┘

完成:
┌──────────────────────────────────┐
│  ✓ 已完成                         │  text-success-600
│  █████████████████████████████    │  bg-success-500
└──────────────────────────────────┘
```

- 容器：`border border-gray-200 rounded-lg p-3`
- 状态文字 + 百分比：`flex items-center justify-between`
- 进度条：`mt-2 h-2 bg-gray-200 rounded-full overflow-hidden`，内层 `h-2 bg-primary-500 rounded-full transition-all`
- 状态颜色映射：
  - queued/downloading/extracting_audio/asr_running/llm_running/persisting → `text-primary-600` + `bg-primary-500`
  - succeeded → `text-success-600` + `bg-success-500`
  - failed → `text-danger-600` + `bg-danger-500`
- 重试按钮：`text-sm text-primary-600 hover:underline`
- 错误信息：`mt-2 text-sm text-danger-600`

---

### 4.6 交互状态规范

| 状态 | 适用元素 | 样式 |
|---|---|---|
| **默认** | 所有 | 基础样式 |
| **hover** | 可点击元素 | `hover:bg-gray-50`（列表项）、`hover:text-primary-700`（链接）、`hover:shadow-md`（卡片） |
| **active** | 按钮 | `active:scale-95`（微缩放） |
| **focus** | 输入框 | `focus:ring-2 focus:ring-primary-500 focus:border-primary-500` |
| **disabled** | 按钮 | `disabled:opacity-50 disabled:cursor-not-allowed` |
| **loading** | 按钮/区域 | `animate-pulse`（骨架屏）、按钮文字变 "处理中..." |
| **error** | 输入框 | `border-danger-500 ring-1 ring-danger-500` |
| **empty** | 列表区域 | 居中 `text-gray-400 text-sm` + 提示文字 |

### 4.7 加载/空/错误状态统一组件

```tsx
// components/Loading.tsx — 骨架屏
function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 rounded ${className}`} />;
}

// components/Empty.tsx — 空状态
function Empty({ text }: { text: string }) {
  return <div className="text-gray-400 text-sm text-center py-8">{text}</div>;
}

// components/ErrorBanner.tsx — 错误提示
function ErrorBanner({ message }: { message: string }) {
  return <div className="bg-danger-50 border border-danger-200 rounded-md p-3 text-sm text-danger-600">{message}</div>;
}
```

### 4.8 Toast 通知系统（替代 alert）

```tsx
// store/toast.ts — Zustand
interface Toast { id: number; type: 'success' | 'error' | 'info'; message: string; }
export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  add: (type, message) => {
    const id = Date.now();
    set((s) => ({ toasts: [...s.toasts, { id, type, message }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3000);
  },
}));

// components/Toast.tsx — 渲染层（固定在右上角）
// 位置: fixed top-4 right-4 z-100 space-y-2
// success: bg-success-50 border-success-200 text-success-700
// error:   bg-danger-50 border-danger-200 text-danger-700
// info:    bg-primary-50 border-primary-200 text-primary-700
```

### 4.9 响应式设计（MVP 桌面优先，最低 1024px）

| 断点 | 布局变化 |
|---|---|
| `≥ 1280px` (xl) | CourseDetail 三栏：左 2/3 播放器+字幕，右 1/3 重点+总结+导图 |
| `1024px–1279px` (lg) | 同上，间距收紧 `gap-4` |
| `< 1024px` | MVP 不适配，显示提示 "建议使用桌面浏览器访问" |

```tsx
// CourseDetail 响应式
<div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
  <div className="lg:col-span-2 space-y-4">...</div>
  <div className="lg:col-span-1 space-y-4">...</div>
</div>
```

### 4.10 SeekContext 联动方案（F2+F3 完整实现）

```tsx
// Player/index.tsx
export const SeekContext = createContext<(t: number) => void>(() => {});

interface PlayerProps {
  src: string;
  onTimeUpdate?: (t: number) => void;
  children?: React.ReactNode;
}

export default function Player({ src, onTimeUpdate, children }: PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!videoRef.current || !src) return;
    playerRef.current = videojs(videoRef.current, { controls: true, fluid: true, sources: [{ src }] });
    playerRef.current.on('timeupdate', () => onTimeUpdate?.(playerRef.current.currentTime()));
    setReady(true);
    return () => playerRef.current?.dispose();
  }, [src]);

  const seek = (t: number) => playerRef.current?.currentTime(t);

  return (
    <div data-vjs-player>
      <video ref={videoRef} className="video-js" />
      {ready && <SeekContext.Provider value={seek}>{children}</SeekContext.Provider>}
    </div>
  );
}

// CourseDetail.tsx — 消费 SeekContext
import { useContext } from 'react';
import { SeekContext } from '@/components/Player';

// 在组件内
const seek = useContext(SeekContext);

// 渲染：Subtitle/Keypoints/Mindmap 的 onSeek={seek}
```

---

## 二、纯后端（5 项）

### B1：CAS 验证码处理

- **位置**：`backend/app/integrations/platform.py:56-58`
- **现状**：manual 和 ocr 模式均为 `NotImplementedError`
- **方案**：

**manual 模式**（MVP 默认，最可靠）：
1. 新增 API 端点 `POST /api/v1/platform/captcha/init` → Playwright 打开 CAS 页面，截图验证码区域，返回 `captcha_image_base64` + `session_key`
2. 新增 API 端点 `POST /api/v1/platform/captcha/submit` → 接收前端透传的 `captcha_code`，填入页面完成登录，返回 cookies
3. `cas_login(captcha_code: str, session_key: str)` 内填入验证码后提交

**ocr 模式**（可选自动化）：
```python
# pip install ddddocr
import ddddocr
ocr = ddddocr.DdddOcr()
captcha_code = ocr.classification(image_bytes)
```

### B2：fetch_course_meta 串联编排

- **位置**：`backend/app/integrations/platform.py:141`
- **现状**：`NotImplementedError`
- **方案**：

```python
async def fetch_course_meta(platform_course_id: str) -> dict:
    cookies, user_id = await cas_login()
    courses = await list_user_courses(cookies)
    # 找到目标课程
    target = next((c for c in courses if str(c["cId"]) == platform_course_id), None)
    if not target:
        raise ValueError(f"课程 cId={platform_course_id} 不在用户课程列表中")
    # 拉取课次列表
    replays = await list_replay_courses(cookies, target["cId"])
    # 逐节获取三路流地址
    result = []
    for r in replays:
        stream_map = await get_stream_map(cookies, r["id"], user_id)
        result.append({"replay": r, "stream_map": stream_map})
    return {"cookies": cookies, "user_id": user_id, "course": target, "replays": result}
```

### B3：视频下载

- **位置**：`backend/app/pipeline/steps/download.py:15`
- **现状**：`NotImplementedError`
- **方案**：用 ffmpeg-python 下载教师流 HLS → mp4

```python
import ffmpeg
from pathlib import Path
from app.config import settings

def download_video(stream_url: str, output_path: str) -> str:
    """下载教师流 HLS → mp4。MVP 优先 teaStreamHlsUrl。"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    (
        ffmpeg.input(stream_url, protocol_whitelist="https,http,tcp,tls")
        .output(output_path, codec="copy")
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path
```

- **注意**：下载前检查磁盘可用空间；流地址可能有时效性，失败时需重新调 API 2 刷新

### B4：音频提取 + 降噪

- **位置**：`backend/app/pipeline/steps/audio.py:13`
- **现状**：`NotImplementedError`
- **方案**：用 ffmpeg 提取 16kHz 单声道 PCM WAV（讯飞 ASR 要求）

```python
import ffmpeg

def extract_audio(video_path: str, audio_path: str) -> str:
    """从视频提取音频：16kHz 单声道 PCM WAV + afftdn 降噪。"""
    (
        ffmpeg.input(video_path)
        .filter("afftdn")  # 频域降噪
        .output(audio_path, acodec="pcm_s16le", ar="16000", ac=1)
        .overwrite_output()
        .run(quiet=True)
    )
    return audio_path
```

### B5：平台导入去重

- **位置**：`backend/app/services/course_service.py`
- **现状**：只有手动导入 `import_course`（source="manual"），缺平台拉取去重
- **方案**：新增 `import_from_platform` 方法，先查 `platform_course_id` 唯一索引

```python
def import_from_platform(db: Session, platform_course_id: str, meta: dict) -> Course:
    """平台课程导入：已存在则更新，不存在则新建。"""
    existing = db.query(Course).filter(
        Course.platform_course_id == platform_course_id
    ).first()
    if existing:
        # 更新元数据
        for k, v in meta.items():
            if v is not None:
                setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    course = Course(
        platform_course_id=platform_course_id,
        source="platform",
        **meta,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course
```

---

## 三、AI 相关后端（4 项）

> **本节修订说明**：原稿只有 A1（讯飞 ASR）、A2（硅基流动 LLM）两个函数级草图，缺少「现有代码契约、长文本分段、结果校验与规范化、平台字幕/知识点接入、失败降级与测试」等环节，且草图与当前代码签名不一致（`transcribe` 现为**同步**函数；LLM 客户端是**三个业务函数 + `_chat`**，并不存在 `generate_analysis`）。
> 本节依据 `docs/00`（FR-03/04/05/06、P0-03~P0-06、NFR-02/03/04/05/10、AC-02/03/04/05/06）、`docs/03`（四张结果表）、`docs/04`（Step 4/5/6 与状态机）、`docs/05`（异常降级与防幻觉）、`docs/10`（平台 API 3 知识点 / API 6 字幕）以及当前后端代码骨架重新补全为 4 项。

### A0：AI 步骤现有骨架与接口契约（动手前必读）

**已就绪、不要重复实现**：

| 环节 | 位置 | 现状 |
| --- | --- | --- |
| ASR 步骤 | `backend/app/pipeline/steps/asr.py:7-13` | `run_asr(audio_path, task_id)` 已由 `@with_retry(max_attempts=settings.xfyun_asr_max_retry, exceptions=(TimeoutError, RuntimeError), step_name="asr")` 包裹 |
| LLM 步骤 | `backend/app/pipeline/steps/llm.py:12-22` | `run_llm(transcripts, course, task_id)` 已接重试（`siliconflow_max_retry`），依次调用三个 LLM 函数 |
| 重试策略 | `backend/app/pipeline/retry.py:11-22` | tenacity 指数退避（2s 起、上限 30s、`reraise=True`） |
| 结果持久化 | `backend/app/pipeline/steps/persist.py:11-59` | 事务写入 transcripts/keypoints/summaries/mindmaps，统一写 `ai_generated=True`、`source_model`、`generated_at`；keypoint 时间戳越界时跳过（`:33-34`） |
| 编排与状态 | `backend/app/pipeline/orchestrator.py:39-48` | `asr_running(50)` → `llm_running(75)` → `persisting(90)` → `succeeded(100)`；异常走 `mark_failed`（`:57-59`） |
| 结果查询 API | `backend/app/api/v1/transcripts.py`、`keypoints.py`、`summaries.py`、`mindmaps.py` | 已实现，含 `require_course_access` 课程级鉴权 |
| 平台数据源 | `backend/app/integrations/platform.py:275-285`（`list_keypoints`）、`:287-294`（`get_subtitle_vtt`） | 已实现，但**当前没有任何调用方**（A3 负责接入） |

**待实现（即本节 A1~A4）**：

| 环节 | 位置 | 现状 |
| --- | --- | --- |
| ASR 客户端 | `backend/app/integrations/xfyun_asr.py:10-18` | 同步 `transcribe(audio_path) -> list[dict]`，仅校验凭证（`:16-17`）后 `raise NotImplementedError`（`:18`） |
| LLM 客户端 | `backend/app/integrations/siliconflow_llm.py:7-36` | `_SYSTEM_PROMPT`（`:7-10`，防幻觉）+ `_chat` 桩（`:13-18`）+ 三个业务函数（`:21-36`，prompt 已写好但返回空值） |
| 平台字幕/知识点接入 | `backend/app/pipeline/steps/metadata.py:10-19` | 只回写 `title`/`duration_sec`，未取 VTT/zsd，也没有保存 `rpId` |
| 校验/降级/测试 | `retry.py`、`orchestrator.py`、`backend/tests/test_pipeline/`（目前仅有 `__init__.py`） | 429、整任务超时、并发上限、AI 单测均未落地 |

**接口契约（实现时必须遵守，否则会波及已就绪代码）**：

| 契约 | 具体约定 |
| --- | --- |
| ASR 客户端签名 | `def transcribe(audio_path: str) -> list[dict]`，**同步**（与 `download.py`/`audio.py` 一致）。不要改成 `async`，否则 `asr.run_asr` 与编排层都要同步改动 |
| 转写元素字段 | `{"text": str, "start_sec": float, "end_sec": float}`（`persist.py:27` 直接读取）；`seq_index` 由 `persist.py:26` 按顺序生成，ASR 不必返回 |
| 重点元素字段 | `title` / `category` / `summary` / `timestamp_sec` / `source_transcript_ids`（`persist.py:36-40`） |
| 总结字段 | `overview` / `chapter_points` / `key_details` / `review_hints`（`persist.py:45-48`） |
| 导图字段 | `root_topic` / `nodes`（`persist.py:54-55`），`nodes` 为两级结构 `[{module, knowledge_points:[{name, timestamp_sec}]}]` |
| 枚举与范围约束 | `category ∈ {concept, formula, example, exam_point}`（`docs/03:121`）；`0 ≤ timestamp_sec ≤ duration_sec`（`docs/03:130`、AC-03-03）；`0 ≤ start_sec < end_sec ≤ duration_sec`（AC-06-02） |
| 来源标识 | ASR：`source_model='xfyun-asr'`、`ai_generated=True`（`persist.py:28`）；LLM：`ai_generated=True`、`source_model=settings.siliconflow_model`（`persist.py:39/49/56`）；平台数据：`ai_generated=False`（`docs/03:131`、`docs/10:977`） |
| 任务状态 | `asr_running` / `llm_running` / `persisting`（`docs/03:76`、`docs/04:96-101`）由编排层写入，AI 客户端不要自行改任务状态 |

**范围边界**：P1 的 AI 能力——术语库与术语校正（FR-15/P1-01，对应 AC-06-06 见 `docs/00:311`）、字幕与导图导出（FR-11/P1-02~03）、复习题生成（FR-12/P1-04）、课内关键词检索（FR-09/P1-05）——MVP 只预留目录、不编码（`docs/08:22-46`），本节不含其实现；需求中检索定义为**关键词检索**，不引入向量/embedding。

### A1：讯飞 ASR API 调用

- **位置**：`backend/app/integrations/xfyun_asr.py:10-18`
- **现状**：`transcribe()` 仅做凭证校验后 `raise NotImplementedError`；而 `asr.run_asr` 的重试、编排层的 `asr_running(50)` 状态、`persist.py` 的入库都已就绪，**实际只需把 `transcribe` 填实**
- **目标**：输入 `storage/audios/{task_id}.wav`（16kHz 单声道，已由 `audio.extract_and_denoise` 降噪），输出句级时间戳转写 `[{text, start_sec, end_sec}]`，满足 FR-03、AC-02-01~05、AC-06-01~02

**实现步骤**：

1. **参数与语言**：显式传入 `settings.xfyun_asr_lang`（`config.py:37`、`.env.example:44`）选择中文/英文模型，否则英文课程识别质量会下降。
2. **鉴权签名**：按 `xfyun_asr.py:13` 的 TODO 用 HMAC + Base64 生成签名，请求携带 `appId` 与 `ts`/`signa`。
3. **上传音频**：先校验文件存在、格式与大小在接口限制内；超过单文件上限时按静音边界**分片**上传（长音频接口要求）。
4. **轮询结果**：用上传返回的任务 ID 轮询，间隔 5s；轮询总时长受 `settings.xfyun_asr_timeout`（`config.py:38`）与整任务 `TASK_TOTAL_TIMEOUT` 双重约束。**注意**：`settings.xfyun_asr_max_retry`（`config.py:39`）已被 `asr.py:7-11` 的重试装饰器占用，轮询次数不要再复用它，否则最坏耗时 = 轮询次数 × 重试次数 × 单次超时。
5. **解析结果**：把返回的 lattice / `bestPath` 中词级 `bg`/`ed`（开始/结束）按标点与停顿聚合为**句级** `{text, start_sec, end_sec}`（秒，保留 2 位小数）。
6. **结果校验**（AC-06-02、NFR-02）：句级时间戳单调不减、`start_sec < end_sec`、不超过课程 `duration_sec`；越界句截断到 `duration_sec` 并告警；相邻空洞 > 10s 记 warning 便于排查。

**代码骨架**（保持现有同步签名）：

```python
def transcribe(audio_path: str) -> list[dict]:
    """讯飞 ASR：音频 → 句级时间戳转写 [{"text", "start_sec", "end_sec"}]。"""
    # 1) 签名：ts + appId + secret（算法以控制台开通的接口为准）
    # 2) 上传：files={"file": open(audio_path, "rb")}，带 fileName/fileSize/duration/language
    # 3) 轮询：interval=5s，deadline 由 xfyun_asr_timeout / TASK_TOTAL_TIMEOUT 控制
    # 4) 解析：lattice → bestPath → 词级 bg/ed → 聚合为句级
    # 5) 校验：单调递增、0 ≤ start < end ≤ duration_sec、空洞告警
    return sentences
```

**配置项**：`XFYUN_APP_ID` / `XFYUN_API_KEY` / `XFYUN_API_SECRET`、`XFYUN_ASR_LANG`、`XFYUN_ASR_TIMEOUT`、`XFYUN_ASR_MAX_RETRY`（`.env.example:39-48`、`docs/06:39-45`）。

**注意事项**：

- 长音频转写（语音转写 / LFASR）与实时听写（IAT）是**两套接口，域名、路径、签名算法都不同**。原稿写的 `https://api.xfyun.cn/v1/audios` + `X-Appid/X-Signa` 请求头，与代码里 `lattice`/`bestPath` 的解析要求并不匹配，实现前必须以控制台实际开通的接口文档为准（若签名实为 `HmacSHA1(MD5(appId+ts), secretKey)`，就不是 SHA256）。
- 长音频接口通常只用到 `APPID + API_SECRET`，`XFYUN_API_KEY` 可能不参与签名：配置保留以便将来切换接口，但不要假定三者都必需。
- 降噪与重采样已在 Step 3 的 `audio.extract_and_denoise` 完成，ASR 侧不要重复处理音频。
- 失败时必须抛出 `TimeoutError` 或 `RuntimeError`，否则不会被 `asr.py:9` 的 `exceptions=(TimeoutError, RuntimeError)` 捕获、也就不会触发重试。
- **实现前需同步修正的两处细节**：`xfyun_asr.py:16` 目前只校验 `xfyun_app_id` / `xfyun_api_key`，未校验签名必需的 `xfyun_api_secret`；`:5` 的 `import httpx` 目前完全未使用，实现后才会用上。
- **占位实现会被重试放大**：`NotImplementedError` 是 `RuntimeError` 的子类，会被 `asr.py:9` 的 `exceptions=(TimeoutError, RuntimeError)` 捕获，所以现在跑流水线会先白等一轮指数退避才失败；填实实现后不受影响。

### A2：硅基流动 LLM API 调用

- **位置**：`backend/app/integrations/siliconflow_llm.py:7-36`
- **现状**：`_SYSTEM_PROMPT`（`:7-10`）与三个业务函数的 prompt（`:22`、`:28`、`:34`）都已写好，但 `_chat`（`:13-18`）是桩，三个函数调完 `_chat` 后**丢弃返回值**、恒返回 `[]` / `{}`；`llm.run_llm`（`llm.py:12-22`）的重试与编排状态已就绪
- **目标**：以转写为**唯一输入**生成重点时间点、分层总结、两级思维导图（FR-04/05/06、P0-04~P0-06），并满足 `docs/00:129` 的"大模型按文本分段"

**A2-1 输入必须带时间戳（当前实现的缺陷）**

`llm.py:18` 现在是 `text = "\n".join(t["text"] for t in transcripts)`，只有文本、没有时间；而 `siliconflow_llm.py:9` 的系统提示要求"所有时间点必须来自转写提供的时间戳"，三个 prompt 也都要求返回 `timestamp_sec`，AC-03-04/AC-05-05 还要求节点能跳转（NFR-02 偏差 ≤ 2s）。**没有时间信息的输入，模型只能编造时间点。** 必须先改输入构造，例如：

```python
text = "\n".join(f"[{t['start_sec']:.1f}] {t['text']}" for t in transcripts)
```

**A2-2 长文本分段（60–120 分钟课程必需）**

单节回放的转写约 0.8–2 万字，一次全量投喂会遇到上下文上限、时延与成本问题（`docs/00:98` NFR-10 按量付费、`docs/00:378` 成本监控）。建议：

1. 先用整段模式跑通；当转写字符数超过阈值（建议 12000 字）再切分段模式。
2. 分段：按时间窗口 10–15 分钟切块，相邻块重叠 30–60 秒，避免跨块知识被截断。
3. map→reduce：每块分别抽重点/总结要点，再合并去重（`timestamp_sec` 邻近的合并）、全局按时间重新排序。
4. 成本与调用次数：记录每次调用的 `model`、输入字符数、耗时，便于估算用量与配额。

**A2-3 `_chat` 实现要点**

`settings.siliconflow_base_url` + `/chat/completions`；`Authorization: Bearer <SILICONFLOW_API_KEY>`；`model=settings.siliconflow_model`；`messages=[{"role":"system","content":_SYSTEM_PROMPT},{"role":"user","content":user_prompt}]`（**system 角色不能省**，防幻觉约束就在这里）；`temperature=0.3`；`response_format={"type":"json_object"}`；超时用 `settings.siliconflow_timeout`（`config.py:44`）。

**A2-4 JSON 解析容错**

模型可能返回 ```json 围栏、前后解释文字或截断的 JSON。解析顺序：去围栏 → 截取第一个 `{` 到最后一个 `}` → `json.loads`；失败时把报错信息回灌重试一次；仍失败则抛 `RuntimeError`，交给 `llm.py` 的重试与失败处理。

**A2-5 结果规范化（防幻觉的真正落地环节）**

| 规范化项 | 规则 | 依据 |
| --- | --- | --- |
| `category` | 必须落在 `KEYPOINT_CATEGORIES = ("concept","formula","example","exam_point")` 内（`db/models/keypoint.py:9`），非法值归为 `concept`；`category` 列在模型中可空且无 CHECK 约束（`keypoint.py:24`），校验只能放在代码里 | `docs/03:121` |
| `timestamp_sec` | 缺失或越界时对齐到最接近的转写句 `start_sec`；仍无匹配则丢弃该条 | AC-03-03、AC-03-06 |
| `source_transcript_ids` | **不要信任模型输出**：由本地用 `timestamp_sec` 匹配 ± `TIMESTAMP_TOLERANCE_SEC`（2s）内的转写句 id 生成 | `docs/03:126`、`docs/05:49` |
| 思维导图结构 | 强制两级 `{root_topic, nodes:[{module, knowledge_points:[{name, timestamp_sec}]}]}`，多余层级拍平 | `docs/03:159`、AC-05-01/02 |
| 空结果 | 允许返回空列表/空对象，前端按"暂无"提示展示；**不得**用其他课程内容或占位假数据填充 | AC-03-06、AC-04-07、AC-05-06 |

**代码骨架**（保持现有三个函数契约，不再引入 `generate_analysis`）：

```python
import json
import httpx
from app.config import settings

def _chat(user_prompt: str) -> str:
    if not settings.siliconflow_api_key:
        raise RuntimeError("硅基流动 API Key 未配置")
    with httpx.Client(timeout=settings.siliconflow_timeout) as c:
        resp = c.post(
            f"{settings.siliconflow_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={
                "model": settings.siliconflow_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()   # 429/5xx 的等待重试见 A4-2
        return resp.json()["choices"][0]["message"]["content"]


def _loads(content: str) -> dict:
    """去 ```json 围栏、截取首尾花括号后解析；失败抛出便于重试。"""
    ...

# 三个函数必须改为使用 _chat 的返回值并做规范化：
#   extract_keypoints -> [{"title", "category", "summary", "timestamp_sec", "source_transcript_ids"}]
#   generate_summary  -> {"overview", "chapter_points", "key_details", "review_hints"}
#   generate_mindmap  -> {"root_topic", "nodes"}
```

**配置与一致性注意**：`config.py:43` 的默认模型是 `deepseek-ai/DeepSeek-V3`，而 `.env.example:54` 与 `docs/06:52` 写的是 `Qwen/Qwen3-8B`（`docs/01:25` 又写"DeepSeek/Qwen"、`docs/03:125` 以 `deepseek-v3` 作为 `source_model` 示例）。由于 `persist.py:39/49/56` 会把 `settings.siliconflow_model` 直接写进 `source_model`，**这四处口径必须先统一**，否则同一批数据的来源标识会不一致。

### A3：平台字幕（VTT）与知识点（zsd）接入

- **位置**：`backend/app/integrations/platform.py:275-285`（`list_keypoints`，API 3）、`:287-294`（`get_subtitle_vtt`，API 6）——两者**已实现但全项目无调用方**；接入点在 `pipeline/steps/metadata.py`、Step 4 之前与 Step 5 之后
- **依据**：`docs/10:947-948`（zsd 作为 LLM 重点的补充/校验来源，与 LLM 结果做时间点对齐校验，偏差 ≤ 2s；平台 VTT 可直接复用，作为 ASR 结果的补充/校验，无则走 ASR 生成）、`docs/10:977`（zsd 写入 keypoints：`timestamp_sec = zsd_wait_time`、`source_model='platform-zsd'`、`ai_generated=False`、`category` 按内容归类）、`docs/03:131`
- **前置阻塞（必须先修）**：`metadata.py:16-17` 读取的是 `meta.get("title")` / `meta.get("duration_sec")`，但 `platform.fetch_course_meta()` 返回的是 `{"cookies","user_id","course","replays"}`（`platform.py:267-272`）——**键名不匹配**，且从未把三路流地址写入 `course.video_url`（而 `orchestrator.py:31` 依赖它）。这一处不修，A1/A2 在平台课程上根本跑不到

**前置缺口：`rpId` 无处存放**

API 3 / API 6 都需要 `videoId`（即 `rpId`）（`docs/10:205-206`），但 `courses` 表当前字段（`docs/03:36-47`）只有 `platform_course_id`（= `cId`），没有回放 id 字段。两种落地方式：

1. **推荐**：给 `courses` 增加 `platform_replay_id`（TEXT），Step 1 取三路流地址时一并写入；A3、以及"重试复用缓存"都能直接复用。
2. 临时方案：Step 1 把 `rpId` 放进任务上下文（内存）传递，不落库——但重试会新建任务（`docs/04:109-116`），上下文丢失，不满足"跳过 Step 1/2/3"的复用要求。

**三个接入点**

| 接入点 | 时机 | 动作 |
| --- | --- | --- |
| Step 1 元数据 | `metadata.fetch_metadata` | 修正键名映射，保存 `rpId`（可顺带预取 VTT/zsd 缓存到任务上下文） |
| Step 4 之前 | ASR 之前 | 有平台 VTT → 解析为转写（`ai_generated=False`、`source_model='platform-vtt'`）；ASR 结果与之逐句对齐，缺失段落用 ASR 补全（`docs/10:948`） |
| Step 5 之后 | LLM 之后、`persist` 之前 | zsd → keypoints（`timestamp_sec=zsd_wait_time`、`source_model='platform-zsd'`、`ai_generated=False`），与 LLM 重点按 ≤ `TIMESTAMP_TOLERANCE_SEC` 去重后**并存展示**（`docs/10:977`、`docs/03:131`） |

**对齐与合并（伪代码）**

```python
def parse_vtt(vtt_text: str) -> list[dict]:        # VTT → [{text, start_sec, end_sec}]
def map_zsd(zsd_items: list[dict]) -> list[dict]:   # zsd → [{title, category, summary, timestamp_sec, ai_generated=False}]
def align(ai_items: list[dict], platform_items: list[dict], tol: int) -> list[dict]:
    """偏差 ≤ tol（默认 TIMESTAMP_TOLERANCE_SEC=2s）视为同一时间点：
    平台条目保留（按平台时间点），AI 条目并入 summary 等补充信息，不重复打点。"""
```

**注意**：`platform.py` 这两个函数是 `async def`，而流水线与 `transcribe` / `_chat` 都是同步的；调用方式参照 `metadata.py:15` 的 `asyncio.run(...)` 先例，不要在已有事件循环内嵌套调用。

### A4：结果校验、失败降级与测试

- **位置**：`pipeline/retry.py`、`pipeline/orchestrator.py`、`pipeline/steps/persist.py`、`backend/tests/test_pipeline/`
- **依据**：`docs/05:5-14`（外部 API 降级）、`docs/05:12`（429 按 `Retry-After`）、`docs/05:23-24`（整任务超时、并发上限）、`docs/05:49-52`（防幻觉与越界校验）、`docs/02:123`（流水线单测 mock 外部 API）、`docs/00:378-379`

**A4-1 持久化前的校验清单**

| 校验 | 规则 | 失败处理 | 依据 |
| --- | --- | --- | --- |
| 转写时间戳 | 单调不减、`0 ≤ start_sec < end_sec ≤ duration_sec` | 越界截断/丢弃 + warning | AC-06-02、NFR-02 |
| 重点时间戳 | `0 ≤ timestamp_sec ≤ duration_sec` | 丢弃 + **告警**（`persist.py:33-34` 现在静默 `continue`，需补日志） | AC-03-03、`docs/05:51` |
| `category` | 落在 `KEYPOINT_CATEGORIES` 白名单内（`keypoint.py:9`） | 归为 `concept` | `docs/03:121` |
| 必填字段 | `text` / `title` / `timestamp_sec` / `start_sec` 等非空 | 丢弃该条并告警 | `docs/03:92-165` |
| AI 标识 | `ai_generated` / `source_model` / `generated_at` 必须写入 | 视为 `PERSIST_FAIL` | `docs/00:377`、`docs/05:50` |
| 空结果 | 允许为空并如实展示"暂无" | 不写占位假数据 | AC-03-06、AC-04-07、AC-05-06 |

**A4-2 失败、重试与降级矩阵**

| 场景 | 现状 | 待补 |
| --- | --- | --- |
| ASR 超时/报错 | `asr.py:7-11` 指数退避重试 `XFYUN_ASR_MAX_RETRY` 次；仍失败由 `orchestrator.py:57-59` 标 failed | 错误码固定为 `ASR_TIMEOUT` / `ASR_ERROR`（现在取异常类名大写，会得到 `TIMEOUTERROR`，与 `docs/03:79`、`docs/04:63` 不一致） |
| LLM 超时/报错 | `llm.py:12-16` 重试 `SILICONFLOW_MAX_RETRY` 次 | 错误码固定为 `LLM_TIMEOUT` / `LLM_ERROR`；**部分失败降级**：重点/总结/导图任一失败时，已成功的结果先落库、失败项留空并在 `error_message` 说明，任务整体仍标 `failed` 供重试，且"已生成的部分结果不回滚丢失"（`docs/05:10`）——注意 `persist.save_results` 当前要求四类结果齐全，需要支持 `None` / 空值 |
| 429 限流 | 未处理：`retry.py:16` 只对 `(TimeoutError, RuntimeError)` 重试，`httpx.HTTPStatusError`（429）不会重试 | 增加 429 分支，按 `Retry-After` 头等待后重试（`docs/05:12`） |
| 整任务超时 | 未落地：`config.py:58` 有 `task_total_timeout`，全项目无使用 | 在编排层对下载+ASR+LLM 累计耗时设上限，超时标 `TOTAL_TIMEOUT`（`docs/05:23`） |
| 并发上限 | 未落地：`config.py:59` 有 `task_max_concurrent`，`parse_worker.py` 未使用 | 限制同时运行的任务数，超出排队（`docs/05:24`、`docs/10:1016`） |
| 重试复用缓存 | 未落地：`task_service.py:26` 复制了 `video_cache_path`，但 `orchestrator.py:31` 无条件重新下载，从不读取该字段 | 按 `docs/04:115` 跳过 Step 1/2/3 从失败步骤续跑；否则一次 LLM 阶段失败会连带重复消耗 ASR 额度 |
| 凭证缺失 | `xfyun_asr.py:16-17`、`siliconflow_llm.py:14-15` 已抛 `RuntimeError` | 建议在建任务前前置校验，给出可读提示，而不是等到 ASR 步骤才失败 |

**A4-3 可观测性与成本**

- 每次 AI 调用记录：`task_id`、步骤名、模型、输入字符数（估算 token）、耗时、重试次数、返回条数——服务 NFR-10 与 `docs/00:378` 的"成本监控"（当前无任何 token/成本字段）。
- 越界丢弃、时间戳空洞、空结果、平台对齐偏差 > 2s 均写 warning，便于试点期评估 NFR-03（字错率 ≤ 20%）与 NFR-04（重点有效性 ≥ 80%）。

**A4-4 单元测试清单**

`backend/tests/test_pipeline/` 目前只有 `__init__.py`，AI 相关测试覆盖为 0；`pyproject.toml:29` 已声明 `respx`（httpx mock）但全项目未使用，`conftest.py` 已提供内存 SQLite 的 `client` fixture，基础设施是现成的。按 `docs/02:123` 要求 mock 外部 API（不产生真实调用、不消耗额度）：

| 测试 | 断言 |
| --- | --- |
| ASR 结果解析 | lattice 样例 → 句级时间戳正确、单调递增、范围合法 |
| ASR 超时重试 | 连续失败按 `XFYUN_ASR_MAX_RETRY` 重试后抛错，落库错误码为 `ASR_TIMEOUT` |
| LLM JSON 容错 | ```json 围栏 / 带解释文字 / 截断 三种输入下的解析与重试 |
| 结果规范化 | 非法 `category` → `concept`；越界 `timestamp_sec` → 对齐或丢弃；`source_transcript_ids` 由本地生成 |
| 部分失败降级 | 导图失败时重点与总结仍落库、任务标 failed、部分结果不丢 |
| 持久化 | 四表字段与 `ai_generated`/`source_model`/`generated_at` 正确；越界 keypoint 被丢弃且有告警 |
| 平台接入 | VTT 解析、zsd 映射、≤ 2s 去重合并 |

**A4-5 验收对照**

| 验收点 | 阈值 | 依据 |
| --- | --- | --- |
| 字幕/重点/导图跳转偏差 | ≤ 2s | NFR-02、`docs/00:90` |
| 转写字错率 | ≤ 20% | NFR-03、`docs/00:91` |
| 重点有效性 | ≥ 80% | NFR-04、`docs/00:92` |
| 任务完成率 | ≥ 95% | NFR-05、`docs/00:93` |
| 未完成结果不得标记为成功 | — | AC-02-06、`docs/00:242`、`docs/05:14` |
| 时间点必须落在有效时长内 | — | AC-03-03、AC-06-02 |
| 全部 AI 内容带生成标识 | 100% | `docs/00:377`、`docs/05:50` |

### A5：实现前需统一的不一致项（本次检验结论）

| 不一致项 | 事实 | 处理建议 |
| --- | --- | --- |
| 模型口径 | `config.py:43` = `deepseek-ai/DeepSeek-V3`；`.env.example:54` / `docs/06:52` = `Qwen/Qwen3-8B`；`docs/03:125` 示例用 `deepseek-v3` | 统一为同一个模型 id，并让 `source_model` 记录真实模型 |
| 错误码 | `orchestrator.py:59` 用 `type(exc).__name__.upper()`；`docs/03:79`、`docs/04:43/53/63/78/87` 要求 `ASR_TIMEOUT`、`ASR_ERROR`、`LLM_TIMEOUT`、`LLM_ERROR`、`PERSIST_FAIL` 等固定码 | 在步骤层抛带 `error_code` 的异常，或维护异常类型 → 错误码映射表 |
| 重试续跑 | `task_service.py:26` 复制 `video_cache_path`，但 `orchestrator.py:31` 无条件重新下载；`audio_cache_path` 未复制 | 与 `docs/04:115` 对齐，实现"跳过已完成的 Step 1/2/3" |
| 平台元数据映射 | `metadata.py:16-17` 的键名与 `platform.py:267-272` 返回结构不匹配；`course.video_url` 未被写入 | 先修映射，否则 AI 链路在平台课程上不可达（前置阻塞） |
| 已定义未使用的 AI 配置 | `config.py` 的 `xfyun_api_secret:36`、`xfyun_asr_lang:37`、`xfyun_asr_timeout:38`、`siliconflow_timeout:44`、`timestamp_tolerance_sec:60`，以及 `task_total_timeout:58`、`task_max_concurrent:59` | 在 A1/A2/A3/A4 中逐一接线，避免"配置写了但行为没变" |
| 已定义未使用的常量 | `KEYPOINT_CATEGORIES`（`keypoint.py:9`）、`TASK_STATUSES`（`task.py:9-13`）除定义处外无引用，也未落成 DB CHECK | 在 A2-5 规范化与状态更新校验中使用 |
| 平台知识点的 `source_transcript_ids` 恒为空 | `persist.py:40` 写入 `k.get("source_transcript_ids", [])`，而 LLM 结果恒为 `[]` | A2-5 的本地溯源生成落地后自然修复 |

---

## 实现优先级

```
B1 CAS验证码 → B2 串联编排 → B3 视频下载 → B4 音频提取
                                                ↓
A1 讯飞ASR → A2 硅基LLM → A4 校验/降级/测试 → B5 去重 → F1-F6 前端联调 → U0-U6 样式完善
     ↑
A3 平台字幕/知识点接入（与 A1/A2 并行；需先修平台元数据映射）
```

先打通后端数据链路（B1→B4→A1→A2），再做前端联调（F1-F6），最后补去重（B5）和样式完善（U0-U6）。

AI 侧建议顺序：**A1**（先让 ASR 产出真实转写）→ **A2**（LLM 产出结构化结果，含 A2-1 时间戳注入）→ **A4** 的校验与部分失败降级（保证 AC-02-06 不被违反）→ **A3** 平台字幕/知识点接入（可与 A1 并行开发，但要等元数据映射修好、拿到真实 `rpId` 才能联调）；**A5** 的不一致项在动手前先统一。