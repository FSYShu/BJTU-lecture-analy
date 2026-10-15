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

## 三、AI 相关后端（2 项）

### A1：讯飞 ASR API 调用

- **位置**：`backend/app/integrations/xfyun_asr.py:18`
- **现状**：`NotImplementedError`
- **方案**：对接讯飞语音听写长音频 API

```python
import httpx
import hashlib
import hmac
import base64
import time
from app.config import settings

async def transcribe(audio_path: str) -> list[dict]:
    """讯飞 ASR：音频 → 句级时间戳字幕。

    返回 [{"text": "...", "start_sec": 12.5, "end_sec": 15.3}, ...]
    """
    # 1. 生成 HMAC-SHA256 签名
    ts = str(int(time.time()))
    signa = hmac.new(
        settings.xfyun_api_secret.encode(),
        (settings.xfyun_app_id + ts).encode(),
        hashlib.sha256,
    ).digest()
    signa = base64.b64encode(signa).decode()

    # 2. 上传音频文件（讯飞长音频接口要求先上传）
    async with httpx.AsyncClient(timeout=settings.xfyun_asr_timeout) as c:
        with open(audio_path, "rb") as f:
            upload_resp = await c.post(
                "https://api.xfyun.cn/v1/audios",
                headers={"X-Appid": settings.xfyun_app_id, "X-Signa": signa},
                files={"file": f},
            )
        upload_resp.raise_for_status()
        audio_id = upload_resp.json()["audioId"]

        # 3. 创建转写任务
        task_resp = await c.post(
            "https://api.xfyun.cn/v1/asr",
            headers={"X-Appid": settings.xfyun_app_id, "X-Signa": signa},
            json={"audio_id": audio_id},
        )
        task_resp.raise_for_status()
        order_id = task_resp.json()["orderId"]

        # 4. 轮询结果（每 5s 一次，最多重试 xfyun_asr_max_retry 次）
        for _ in range(settings.xfyun_asr_max_retry):
            await asyncio.sleep(5)
            r = await c.get(f"https://api.xfyun.cn/v1/asr/{order_id}")
            if r.json().get("status") == 3:  # 完成
                return _parse_xfyun_result(r.json())
    raise RuntimeError("ASR 转写超时")


def _parse_xfyun_result(data: dict) -> list[dict]:
    """解析讯飞返回的 lattice JSON → [{"text", "start_sec", "end_sec"}]。"""
    # 解析 bestPath 中的 word 列表，提取 text + bg（开始）+ ed（结束）
    ...
```

- **补充**：转写完成后与平台 API 6 已有 VTT 字幕做时间点对齐校验（偏差 ≤ 2s），优先使用平台字幕填充空缺段

### A2：硅基流动 LLM API 调用

- **位置**：`backend/app/integrations/siliconflow_llm.py:18`
- **现状**：`NotImplementedError`
- **方案**：对接硅基流动 Chat Completions API，一次调用生成重点/总结/思维导图

```python
import httpx
import json
from app.config import settings

async def generate_analysis(transcript_text: str) -> dict:
    """硅基流动 LLM：字幕文本 → 重点 + 总结 + 思维导图。

    返回 {"keypoints": [...], "summary": {...}, "mindmap": {...}}
    """
    prompt = f"""你是课堂分析助手。以下是一段课堂字幕，请分析并返回 JSON：
{{
  "keypoints": [{{"timestamp_sec": 120, "category": "concept", "title": "...", "summary": "..."}}],
  "summary": {{"overview": "...", "chapter_points": [...], "key_details": [...], "review_hints": [...]}},
  "mindmap": {{"root_topic": "...", "nodes": [{{"module": "...", "knowledge_points": [{{"name": "...", "timestamp_sec": 120}}]}}]}}
}}

字幕内容：
{transcript_text}
"""
    async with httpx.AsyncClient(timeout=settings.siliconflow_timeout) as c:
        resp = await c.post(
            f"{settings.siliconflow_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={
                "model": settings.siliconflow_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
```

- **补充**：生成后与平台 API 3 已有知识点（zsd）做时间点对齐校验（偏差 ≤ 2s），平台知识点设 `ai_generated=False, source_model='platform-zsd'` 与 LLM 结果并存

---

## 实现优先级

```
B1 CAS验证码 → B2 串联编排 → B3 视频下载 → B4 音频提取
                                              ↓
A1 讯飞ASR → A2 硅基LLM → B5 去重 → F1-F6 前端联调 → U0-U6 样式完善
```

先打通后端数据链路（B1→B4→A1→A2），再做前端联调（F1-F6），最后补去重（B5）和样式完善（U0-U6）。