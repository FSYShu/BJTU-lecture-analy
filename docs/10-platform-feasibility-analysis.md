# 北交大课程平台回放抓取 — 全流程可行性分析报告

> 探索日期: 2026-09-18  
> 入口: `mis.bjtu.edu.cn`  
> 课程平台: `123.121.147.7:88` (独立服务器)  
> 视频服务器: `lmt5.bjtu.edu.cn:8880` (Wowza 流媒体服务器)  
> 技术栈对齐: 本项目 FastAPI + BackgroundTasks + SQLite + httpx + ffmpeg-python + 讯飞 ASR + 硅基流动 LLM + React + Video.js + markmap（第 10 节已按本项目栈重写，第 11 节给出集成映射）

---

## 目录

1. [总体结论](#1-总体结论)
2. [全流程步骤详解](#2-全流程步骤详解)
3. [API 接口完整文档](#3-api-接口完整文档)
4. [视频流架构分析](#4-视频流架构分析)
5. [音频流架构分析](#5-音频流架构分析)
6. [视频 URL 结构与命名规则](#6-视频-url-结构与命名规则)
7. [播放器技术架构](#7-播放器技术架构)
8. [认证机制分析](#8-认证机制分析)
9. [自动化可行性评估](#9-自动化可行性评估)
10. [技术方案建议](#10-技术方案建议)
11. [与本项目（交大课录智析）集成映射](#11-与本项目交大课录智析集成映射)

---

## 1. 总体结论

| 评估维度 | 结论 | 说明 |
|---------|------|------|
| 整体可行性 | **可行** | 从登录到下载全链路已验证通过 |
| 自动化程度 | **4/5 步骤可自动** | 仅 CAS 验证码需人工或 OCR 辅助 |
| 视频可下载性 | **可下载** | HLS 流 (m3u8 + .ts) 均返回 200，无额外鉴权 |
| 多路音频 | **3 路音轨** | 教师/学生/课件各一路，嵌入在 .ts 分段中 |
| 多路视频 | **3 路视频流** | 教师/学生/课件三路同步 HLS 流 |
| API 驱动 | **完全 API 化** | 登录后所有数据获取通过 JSON API |

---

## 2. 全流程步骤详解

### 步骤 1: CAS 统一身份认证 (手动 — 唯一障碍)

- **URL**: `https://cas.bjtu.edu.cn/auth/login/?next=/o/authorize/?response_type=code&client_id=...&redirect_uri=https://mis.bjtu.edu.cn/auth/callback/?redirect_to=/`
- **表单字段**:
  - 用户名 (`textbox "用户名"`)
  - 密码 (`textbox "密码"`)
  - 图形验证码 (`img "captcha"` + `textbox` 验证码输入框)
- **登录按钮**: `button "登录"`
- **返回结果**: 重定向至 `https://mis.bjtu.edu.cn/home/`，设置 CAS Session Cookie
- **障碍**: 图形验证码无法纯自动识别

### 步骤 2: MIS 门户 → 课程平台跳转 (自动)

- **MIS 首页 URL**: `https://mis.bjtu.edu.cn/home/`
- **关键链接**: "29.交大课程平台" → `/module/module/28/`
- **跳转机制**: 点击后打开新标签页，URL 为:
  ```
  http://123.121.147.7:88/ve/back/coursePlatform/coursePlatform.shtml?method=toCoursePlatformIndex&sessionId={SESSION_ID}
  ```
- **Session 传递**: `sessionId` 通过 URL 参数传递，与 CAS Cookie 关联

### 步骤 3: 获取课程列表 (自动 — API 驱动)

课程平台首页显示用户所有课程。每门课程的 `courseItem` div 有 `onclick` 属性:
```javascript
// 示例: 操作系统课程
onclick="goPage('131266','M310105B','2026-2027-1-2M310105B01','2026202701')"
```

`goPage` 函数实现:
```javascript
function goPage(id, num, fz_id, xq_code) {
    window.open(
        'http://123.121.147.7:88/ve/back/coursePlatform/coursePlatform.shtml' +
        '?method=toCoursePlatform' +
        '&courseId=' + num +       // 课程编号: M310105B
        '&dataSource=1' +
        '&cId=' + id +              // 课程ID: 131266
        '&xkhId=' + fz_id +         // 班级ID: 2026-2027-1-2M310105B01
        '&xqCode=' + xq_code        // 学期代码: 2026202701
    );
}
```

### 步骤 4: 进入视频回放页面 (自动)

课程详情页左侧导航菜单包含以下分类:
- 课程信息 / 课程介绍 / 教学大纲 / 教学日历 / 课程通知
- 教师信息 / 我的分组
- 课程资源: 电子课件 / 教案设计 / MOOC资源 / 实验 / 思政案例 / 试卷库 / 教材教辅
- **课程视频** (父分类)
  - **视频回放** ← 目标入口
- 课程考核: 作业 / 课程报告 / 实验 / 平时测验 / 期末考试成绩
- 答疑讨论 / 学习档案 / 过程考核成绩

"视频回放"菜单项的 `onclick`:
```javascript
onclick="newModuleGoTo('/back/coursePlatform/coursePlatform.shtml?method=toCoursePlatform&courseToPage=10480')"
```

`newModuleGoTo` 函数实现:
```javascript
function newModuleGoTo(url) {
    var courseId = 'M310105B';
    var cId = '131266';
    var xkhId = '2026-2027-1-2M310105B01';
    var xqCode = '2026202701';
    var teacherId = '7930';
    // 构造完整 URL
    window.location.href = 
        'http://123.121.147.7:88/ve' + url +
        '&courseId=' + courseId +
        '&dataSource=1' +
        '&cId=' + cId +
        '&xkhId=' + xkhId +
        '&xqCode=' + xqCode +
        '&teacherId=' + teacherId;
}
```

**视频回放完整 URL**:
```
http://123.121.147.7:88/ve/back/coursePlatform/coursePlatform.shtml
    ?method=toCoursePlatform
    &courseToPage=10480
    &courseId=M310105B
    &dataSource=1
    &cId=131266
    &xkhId=2026-2027-1-2M310105B01
    &xqCode=2026202701
    &teacherId=7930
```

---

## 3. API 接口完整文档

### API 1: 获取课程录像列表

获取某门课程的所有录像课次列表。

```
GET http://123.121.147.7:88/ve/back/rp/common/teachCalendar.shtml
    ?method=toDisplyTeachCourses
    &courseId={courseId}
```

**参数**:
| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| method | string | 固定值 | `toDisplyTeachCourses` |
| courseId | int | 课程ID (cId) | `131266` |

**响应示例**:
```json
{
  "courseSchedList": [
    {
      "videoId": "279BA250E1F94CE882C1211C75C9243E",
      "id": 1802058,
      "classRoom": "YF613",
      "courseId": 131266,
      "courseName": "操作系统",
      "courseNum": "M310105B",
      "courseType": 1,
      "teachTimeStr": "20260907",
      "teacherId": 3127,
      "teacherName": "邢薇薇",
      "classBeginTime": "2026-09-07 10:30:00",
      "classEndTime": "2026-09-07 12:20:00",
      "courseBetween": "2026-09-07 10:30-12:20",
      "uuid": "90F492ECBA404066A9BA060EA69CB58B",
      "classroomId": 440953,
      "courseSort": 1,
      "content": "A View of Operating System Services, Multiprogramming...",
      "params": { "videoId": "279BA250E1F94CE882C1211C75C9243E" }
    },
    {
      "videoId": "724183BEE25944FD91E9D68AC61CF5F9",
      "id": 1804873,
      "teachTimeStr": "20260909",
      "classBeginTime": "2026-09-09 14:10:00",
      "classEndTime": "2026-09-09 16:00:00",
      "courseBetween": "2026-09-09 14:10-16:00",
      "uuid": "5BD1AA47B50E4E7EAD2CA513CE2D0D4C"
    },
    {
      "videoId": "119C10AB6AA2454E9DD032F69CDFEF30",
      "id": 1808350,
      "teachTimeStr": "20260914",
      "classBeginTime": "2026-09-14 10:30:00",
      "classEndTime": "2026-09-14 12:20:00",
      "courseBetween": "2026-09-14 10:30-12:20",
      "uuid": "9055169D27F84A87BF41193B01BA7CEC"
    }
  ]
}
```

**关键字段**:
| 字段 | 说明 | 用途 |
|------|------|------|
| `id` | 课次ID (courseSchedId) | 用于调用 API 2 获取视频流地址 |
| `uuid` | 时间表ID (timeTableId) | 用于调用知识点 API |
| `videoId` | 录像ID (rpId) | 用于知识点和字幕 API |
| `classBeginTime` | 上课开始时间 | 文件命名 |
| `classRoom` | 教室 | 文件命名 |
| `teacherName` | 教师姓名 | URL 路径和文件命名 |
| `teachTimeStr` | 教学日期 (YYYYMMDD) | URL 路径和文件命名 |

---

### API 2: 获取视频流地址 (核心 API)

获取某节课的视频流地址 (HLS + RTMP)。

```
GET http://123.121.147.7:88/ve/back/rp/common/teachCalendar.shtml
    ?method=toDisplyCourseSchedDetail
    &courseSchedId={courseSchedId}
    &userLevel=1
    &userId={userId}
```

**参数**:
| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| method | string | 固定值 | `toDisplyCourseSchedDetail` |
| courseSchedId | int | 课次ID (来自 API 1 的 `id`) | `1808350` |
| userLevel | int | 用户等级 (1=学生) | `1` |
| userId | int | 用户ID | `148042` |

**完整响应**:
```json
{
  "res": {
    "streamMap": {
      "haveStream": "1",
      "rpId": "119C10AB6AA2454E9DD032F69CDFEF30",
      "rpSize": "3953.8",
      "rpStatus": 0,
      "publicRpType": "2,3",
      "videoVoice": "2",
      "data_source": "1",
      "openPath": "",
      "showOtherVideo": "0",
      "pdfb": false,

      "teaStreamHlsUrl": "https://lmt5.bjtu.edu.cn:8880/vod11/_definst_//自动录制_关联课表/2026-20272026-2027第一学期/2026/09/14/海淀西校区/2019年级/2019级2026-2027-1-2M310105B01/操作系统/邢薇薇_20260914102500000/操作系统_邢薇薇_教师_20260914102205983.mp4/playlist.m3u8",
      "stuStreamHlsUrl": "https://lmt5.bjtu.edu.cn:8880/vod11/_definst_//自动录制_关联课表/2026-20272026-2027第一学期/2026/09/14/海淀西校区/2019年级/2019级2026-2027-1-2M310105B01/操作系统/邢薇薇_20260914102500000/操作系统_邢薇薇_学生_20260914102205983.mp4/playlist.m3u8",
      "vgaStreamHlsUrl": "https://lmt5.bjtu.edu.cn:8880/vod11/_definst_//自动录制_关联课表/2026-20272026-2027第一学期/2026/09/14/海淀西校区/2019年级/2019级2026-2027-1-2M310105B01/操作系统/邢薇薇_20260914102500000/操作系统_邢薇薇_课件_20260914102205983.mp4/playlist.m3u8",

      "teaStreamUrl": "rtmp://123.121.147.15:1935/vod11/mp4:/自动录制_关联课表/.../操作系统_邢薇薇_教师_20260914102205983.mp4",
      "stuStreamUrl": "rtmp://123.121.147.15:1935/vod11/mp4:/自动录制_关联课表/.../操作系统_邢薇薇_学生_20260914102205983.mp4",
      "vgaStreamUrl": "rtmp://123.121.147.15:1935/vod11/mp4:/自动录制_关联课表/.../操作系统_邢薇薇_课件_20260914102205983.mp4",

      "teaCloseUpStreamHlsUrl": "",
      "stuCloseUpStreamHlsUrl": "",
      "teaCloseUpStreamUrl": "",
      "stuCloseUpStreamUrl": "",
      "movieStreamHlsUrl": "",
      "movieStreamUrl": ""
    },
    "pointStatus": "no",
    "courseSched": {
      "id": 1808350,
      "courseId": 131266,
      "courseName": "操作系统",
      "courseNum": "M310105B",
      "courseSort": 1,
      "courseType": 1,
      "teacherId": 3127,
      "teacherName": "邢薇薇",
      "classRoom": "YF613",
      "classroomId": 440953,
      "classBeginTime": "2026-09-14 10:30:00",
      "classEndTime": "2026-09-14 12:20:00",
      "courseBetween": "2026-09-14 10:30-12:20",
      "teachTimeStr": "20260914",
      "uuid": "9055169D27F84A87BF41193B01BA7CEC",
      "semesterId": 1,
      "courseState": 2,
      "params": {
        "isSubtitle": "",
        "isSupport": "0",
        "isCollect": "0",
        "support": 0,
        "commentCount": 0
      }
    }
  },
  "STATUS": "0",
  "message": "成功"
}
```

**streamMap 字段说明**:

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `haveStream` | string | 是否有流 ("1"=有, "0"=无权限) | `"1"` |
| `rpId` | string | 录像资源ID | `"119C10AB6AA2454E9DD032F69CDFEF30"` |
| `rpSize` | string | 录像大小 (MB) | `"3953.8"` |
| `rpStatus` | int | 录像状态 | `0` |
| `publicRpType` | string | 公开类型 | `"2,3"` |
| `videoVoice` | string | 默认音源 (推测: 2=学生) | `"2"` |
| `teaStreamHlsUrl` | string | **教师视频 HLS 地址** | m3u8 URL |
| `stuStreamHlsUrl` | string | **学生视频 HLS 地址** | m3u8 URL |
| `vgaStreamHlsUrl` | string | **课件视频 HLS 地址** | m3u8 URL |
| `teaStreamUrl` | string | 教师视频 RTMP 地址 | rtmp URL |
| `stuStreamUrl` | string | 学生视频 RTMP 地址 | rtmp URL |
| `vgaStreamUrl` | string | 课件视频 RTMP 地址 | rtmp URL |
| `teaCloseUpStreamHlsUrl` | string | 教师特写 HLS (可选) | 通常为空 |
| `stuCloseUpStreamHlsUrl` | string | 学生特写 HLS (可选) | 通常为空 |
| `movieStreamHlsUrl` | string | 电影流 HLS (可选) | 通常为空 |

---

### API 3: 获取知识点列表

获取某节课的知识点 (章节标记) 列表，用于视频内导航。

```
GET http://123.121.147.7:88/ve/webservices/qxkt.shtml
    ?method=queryVeRpInfoZsd
    &rpId={rpId}
```

**参数**: `rpId` = streamMap 中的 `rpId` 值

**响应示例**:
```json
{
  "zsdJson": [
    {
      "zsd_name": "History Phase 4 (1989—):",
      "rp_id": "119C10AB6AA2454E9DD032F69CDFEF30",
      "id": "B4A6F5CA638A4DE186B9025F84422629",
      "zsd_wait_time": 288,
      "sfm": "00:04:48"
    },
    {
      "zsd_name": "History Phase 5 (1995-): Mobile Systems",
      "zsd_wait_time": 910,
      "sfm": "00:15:10"
    },
    {
      "zsd_name": "Open-Source Operating Systems",
      "zsd_wait_time": 982,
      "sfm": "00:16:22"
    }
  ]
}
```

**字段说明**:
| 字段 | 说明 |
|------|------|
| `zsd_name` | 知识点名称 |
| `zsd_wait_time` | 跳转时间点 (秒) |
| `sfm` | 跳转时间点 (HH:MM:SS 格式) |

---

### API 4: 获取课程时间表 ID

获取 courseSchedId 和录像开始时间。

```
GET http://123.121.147.7:88/ve/back/knowledgeCenter/knowledgeCenterDetail.shtml
    ?method=getCourseIdAndStartTime
    &timeTableId={uuid}
```

**响应**:
```json
{
  "msg": "success",
  "STATUS": "0",
  "data": {
    "courseSchedId": 1808350,
    "recordStart": "2026-09-14 10:25:00"
  }
}
```

---

### API 5: 获取水印状态

```
GET http://123.121.147.7:88/ve/cn/core/common/configCommonMetbod.shtml?method=getWaterMarkStatus
```

**响应**:
```json
{
  "STATUS": "0",
  "waterMark": "1"  // "1"=启用水印, "0"=关闭
}
```

---

### API 6: 获取字幕文件

```
GET http://123.121.147.7:88/ve/webservices/qxkt.shtml
    ?method=getSubtitleFile
    &rpId={rpId}
    &type=vtt
```

返回 WebVTT 字幕文件。

---

### API 7: 观看时长记录 (心跳)

播放器每隔 300 秒自动发送一次，记录用户观看时长。

```
POST http://123.121.147.7:88/ve/back/tqa/tqaListenRecord.shtml?method=insertListenRecord
```

**参数**: `userId`, `timetableId`, `type=1`, `infoId`, `cId`

---

## 4. 视频流架构分析

### 4.1 流媒体服务器

| 服务器 | 地址 | 协议 | 用途 |
|--------|------|------|------|
| HLS 服务器 | `https://lmt5.bjtu.edu.cn:8880` | HTTPS + HLS | Web 播放 |
| RTMP 服务器 | `rtmp://123.121.147.15:1935` | RTMP | 直播/推流 |

### 4.2 HLS 流结构

每路视频流由以下部分组成:

```
m3u8 播放列表 (playlist.m3u8)
  ├── seg-1-v1-a1.ts  (第1段: 视频 v1 + 音频 a1)
  ├── seg-2-v1-a1.ts  (第2段)
  ├── seg-3-v1-a1.ts  (第3段)
  └── ...
```

- **m3u8**: HLS 主播放列表文件，描述可用的变体流和分段
- **.ts 分段**: MPEG-TS 容器，包含视频帧 (H.264) 和音频帧 (AAC)
- **命名规则**: `seg-{段号}-v{视频轨}-a{音频轨}.ts`

### 4.3 三路视频流

每节课录制 3 路同步视频流:

| 流类型 | HLS 字段 | 文件名后缀 | 内容 |
|--------|---------|-----------|------|
| 教师流 | `teaStreamHlsUrl` | `_教师_` | 教师讲课画面 |
| 学生流 | `stuStreamHlsUrl` | `_学生_` | 学生/教室全景 |
| 课件流 | `vgaStreamHlsUrl` | `_课件_` | 投影/PPT 画面 |

**可选流** (通常为空):
| 流类型 | HLS 字段 | 说明 |
|--------|---------|------|
| 教师特写 | `teaCloseUpStreamHlsUrl` | 教师面部特写 |
| 学生特写 | `stuCloseUpStreamHlsUrl` | 学生面部特写 |
| 电影流 | `movieStreamHlsUrl` | 电影模式 |

---

## 5. 音频流架构分析

### 5.1 音频架构结论

**每路视频流内嵌一路独立音轨，无独立音频流。**

具体而言:
- 3 路视频流 (教师/学生/课件) 各自有独立的音频轨道
- 音频与视频 **复用 (muxed)** 在同一个 `.ts` 分段中
- `.ts` 文件名中的 `a1` 表示音频轨 1
- 不存在独立的音频流请求

### 5.2 网络请求验证

通过网络请求分析确认:
- 所有请求均为 `.m3u8` 或 `.ts` 文件
- 无独立的 `.aac` / `.mp3` / `audio-only` 请求
- 三路流各自独立请求 `.ts` 分段

**网络请求样例**:
```
请求 1: .../操作系统_邢薇薇_教师_...mp4/seg-1-v1-a1.ts → 200
请求 2: .../操作系统_邢薇薇_学生_...mp4/seg-1-v1-a1.ts → 200
请求 3: .../操作系统_邢薇薇_课件_...mp4/seg-1-v1-a1.ts → 200
```

### 5.3 音源切换机制

播放器 UI 提供 3 路音源选择:

```html
<div class="jyd-radioShift" id="jyd-radioShift">
    <span>音源</span>
    <div class="jyd-radioShiftBox">
        <div id="jyd-teacherVoice" class="jyd-radioShiftSelected">老师</div>
        <div id="jyd-studentVoice">学生</div>
        <div id="jyd-courseVoice">课件</div>
    </div>
</div>
```

**切换原理**:
1. 播放器同时加载 3 个 `<video>` 元素 (3 路 HLS 流)
2. 默认播放教师流音频 (CSS 类 `jyd-radioShiftSelected`)
3. 切换音源时: 静音当前流的 `<video>`，取消静音目标流的 `<video>`
4. 三路视频画面始终同步播放，仅音频输出切换

### 5.4 videoVoice 字段

API 返回的 `videoVoice: "2"` 字段推测含义:
- `"1"` = 教师音源
- `"2"` = 学生音源
- `"3"` = 课件音源

可能用于设置默认音源，但实际播放器中默认选中 "老师"。

### 5.5 下载音频的影响

由于音频嵌入在视频 .ts 中:
- 下载教师流 → 获得教师音轨
- 下载学生流 → 获得学生音轨
- 下载课件流 → 获得课件音轨
- **如需所有 3 路音轨，需分别下载 3 路视频流**

---

## 6. 视频 URL 结构与命名规则

### 6.1 完整 URL 模式

```
https://lmt5.bjtu.edu.cn:8880/vod11/_definst_//{录制类型}/{学期}/{年}/{月}/{日}/{校区}/{年级}/{班级ID}/{课程名}/{教师名}_{时间戳}/{课程名}_{教师名}_{流类型}_{时间戳}.mp4/playlist.m3u8
```

### 6.2 URL 路径分解

以实际 URL 为例:

```
https://lmt5.bjtu.edu.cn:8880
  /vod11/_definst_//
  自动录制_关联课表/                    ← 录制类型
  2026-20272026-2027第一学期/           ← 学期 (学年+学期名)
  2026/09/14/                           ← 日期 (YYYY/MM/DD)
  海淀西校区/                           ← 校区
  2019年级/                             ← 入级年份
  2019级2026-2027-1-2M310105B01/        ← 班级ID (入学年级+学期+课程号+课序号)
  操作系统/                             ← 课程名称
  邢薇薇_20260914102500000/             ← 教师名_录制开始时间戳
  操作系统_邢薇薇_教师_20260914102205983.mp4/   ← 文件名
  playlist.m3u8                         ← HLS 播放列表
```

### 6.3 时间戳规则

文件名中的时间戳格式: `YYYYMMDDHHMMSSmmm`

| 时间戳 | 含义 |
|--------|------|
| `20260914102500000` | 录制开始: 2026-09-14 10:25:00.000 |
| `20260914102205983` | 文件创建: 2026-09-14 10:22:05.983 |

### 6.4 RTMP URL 模式

```
rtmp://123.121.147.15:1935/vod11/mp4:/{录制类型}/.../{文件名}.mp4
```

与 HLS URL 路径一致，仅前缀和协议不同。

---

## 7. 播放器技术架构

### 7.1 播放器库

| 文件 | 用途 |
|------|------|
| `jyd20241210.min.js` | 主播放器库 (jydH5Player) |
| `jydH5Player.min.js` | 播放器核心 |
| `jydQuery.min.js` | 内部 DOM 操作库 (类似 jQuery) |

播放器加载地址:
```
http://123.121.147.7:88/ve/ui/jydH5Player/jyd20241210.min.js
http://123.121.147.7:88/ve/ui/jydH5Player/jydH5Player.min.js
```

### 7.2 播放器初始化

```javascript
function playStream(teacherVideoUrl, studentVideoUrl, courseVideoUrl,
                    teacherDetailVideoUrl, studentDetailVideoUrl,
                    movieVideoUrl, rpSize, publicRpType, pointStatus) {

    var option = {
        element: 'videoBox',
        videoSize: rpSize,                    // "3953.8"
        publicRpType: publicRpType,           // "2,3"
        teacherVideoUrl: teacherVideoUrl,     // 教师 HLS URL
        studentVideoUrl: studentVideoUrl,     // 学生 HLS URL
        courseVideoUrl: courseVideoUrl,       // 课件 HLS URL
        teacherDetailVideoUrl: teacherDetailVideoUrl,  // 教师特写 (空)
        studentDetailVideoUrl: studentDetailVideoUrl,  // 学生特写 (空)
        movieVideoUrl: movieVideoUrl,         // 电影流 (空)
        enablePic: pointStatus,               // 打点功能
        getPicInfoUrl: '.../qxkt.shtml?method=getPicInfo',
        getPicInfoId: rpId,
        checkPlayerDuring: true,              // 观看时长监控
        checkInterval: 300,                  // 300秒心跳
        duringUrl: '.../tqaListenRecord.shtml?method=insertListenRecord',
        duringParam_userId: '24301060',
        duringParam_timetableId: timeTableId,
        duringParam_type: '1',
        duringParam_cId: '131266',
        enableCaption: true,                  // 字幕功能
        teacherCaption: '.../qxkt.shtml?method=getSubtitleFile&rpId=' + rpId + '&type=vtt',
        sessionId: '...',
        enableWaterMark: enableWaterMark,     // 水印
        waterMarkText: '24301060/刁博文/2026-09-18'  // 水印内容
    };

    jydH5PlayerObj = new jydH5Player(option);
}
```

### 7.3 播放器 UI 功能

| 功能 | HTML 元素 ID | 说明 |
|------|-------------|------|
| 音源切换 | `jyd-teacherVoice` / `jyd-studentVoice` / `jyd-courseVoice` | 老师/学生/课件 |
| 倍速播放 | `jyd-speed200` ~ `jyd-speed075` | 2.0X/1.5X/1.25X/1.0X/0.75X |
| 板书 | - | 记忆黑板/交互平板 |
| 字幕 | - | 打开/关闭字幕 |
| 全屏 | - | 全屏播放 |
| 音量 | `jyd-currentVolumeBar` | 音量控制 |

### 7.4 视频元素

页面有 3 个 `<video>` 元素，使用 MSE (Media Source Extensions) + Blob URL:

```javascript
// 每个 video 元素的 src 是 blob URL
<video src="blob:http://123.121.147.7:88/b3a1699d-..."></video>  <!-- 教师 -->
<video src="blob:http://123.121.147.7:88/3ef9ad7a-..."></video>  <!-- 学生 -->
<video src="blob:http://123.121.147.7:88/7af6cce1-..."></video>  <!-- 课件 -->
```

播放器使用 hls.js 库将 m3u8 流加载到 MSE Buffer 中，生成 Blob URL 供 `<video>` 元素播放。

---

## 8. 认证机制分析

### 8.1 认证流程

```
用户 → CAS 登录 (cas.bjtu.edu.cn)
         ↓ 账号+密码+验证码
     CAS 验证成功
         ↓ 重定向 + Set-Cookie
     MIS 门户 (mis.bjtu.edu.cn)
         ↓ CAS Session Cookie
     课程平台 (123.121.147.7:88)
         ↓ Cookie 传递 + sessionId URL 参数
     API 调用 + 视频服务器 (lmt5.bjtu.edu.cn:8880)
```

### 8.2 Cookie 机制

- CAS 登录后，浏览器获得 CAS Session Cookie
- 该 Cookie 在 `mis.bjtu.edu.cn` 和 `123.121.147.7:88` 域名间共享
- API 调用仅需携带 Cookie，无需额外 Token/Header
- 视频服务器 (lmt5.bjtu.edu.cn:8880) 的 m3u8 和 .ts 请求**无需任何认证**，直接返回 200

### 8.3 URL 参数认证

课程平台使用 `sessionId` URL 参数进行会话跟踪:
```
?sessionId=6264B6E14F334D7482314E1DAF9D3106
```

该 sessionId 与 CAS Cookie 关联，但 API 调用主要依赖 Cookie 认证。

---

## 9. 自动化可行性评估

### 9.1 步骤评估矩阵

| 步骤 | 操作 | 自动化 | 难度 | 说明 |
|------|------|--------|------|------|
| 1 | CAS 登录 | 部分 | 中 | 账号密码可自动填写，验证码需 OCR 或人工 |
| 2 | 跳转课程平台 | 自动 | 低 | 点击链接，浏览器自动跳转 |
| 3 | 获取课程列表 | 自动 | 低 | API 调用返回 JSON |
| 4 | 获取视频流地址 | 自动 | 低 | API 调用返回 streamMap JSON |
| 5 | 下载视频 | 自动 | 低 | ffmpeg 下载 HLS 流 |

### 9.2 验证码问题

**现状**: CAS 登录页面包含图形验证码 (`<img>` 标签加载验证码图片)

**解决方案**:

| 方案 | 可行性 | 优点 | 缺点 |
|------|--------|------|------|
| OCR 自动识别 | 中 | 全自动 | 准确率受限 (约 60-80%) |
| 打码平台 | 高 | 准确率高 (>95%) | 需付费 |
| 用户手动完成 | 高 | 最可靠 | 非完全自动 |
| 利用现有 Cookie | 高 | 跳过登录 | Cookie 有时效性 |

### 9.3 API 调用链 (自动化核心)

登录后的完整 API 调用链:

```
1. GET /teachCalendar.shtml?method=toDisplyTeachCourses&courseId={courseId}
   → 获取课次列表 [{id, uuid, classBeginTime, ...}]

2. 遍历每节课:
   GET /teachCalendar.shtml?method=toDisplyCourseSchedDetail&courseSchedId={id}&userLevel=1&userId={userId}
   → 获取 streamMap {teaStreamHlsUrl, stuStreamHlsUrl, vgaStreamHlsUrl}

3. 下载视频:
   ffmpeg -i "{teaStreamHlsUrl}" -c copy "{课程名}_{日期}_教师.mp4"
   ffmpeg -i "{stuStreamHlsUrl}" -c copy "{课程名}_{日期}_学生.mp4"
   ffmpeg -i "{vgaStreamHlsUrl}" -c copy "{课程名}_{日期}_课件.mp4"
```

---

## 10. 技术方案建议

### 10.1 推荐架构

```
┌─────────────────────────────────────────────────┐
│                   Web 前端                       │
│  (React + Vite + Tailwind + Video.js + markmap)  │
└──────────────────────┬──────────────────────────┘
                       │ REST API
┌──────────────────────┴──────────────────────────┘
│                   后端服务                       │
│  (Python FastAPI + BackgroundTasks)              │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ CAS 登录 │→│ API 调用 │→│ 视频下载调度  │  │
│  │ 模块     │  │ 模块     │  │ (ffmpeg)     │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │     Playwright (无头浏览器, 可选依赖)      │   │
│  │     - CAS 登录 (含验证码 OCR/人工处理)     │   │
│  │     - Cookie 管理 (复用至 httpx 会话)       │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │     存储 / 数据库                         │   │
│  │     - 课程信息 (SQLite + SQLAlchemy)       │   │
│  │     - 后台任务 (BackgroundTasks, 无 Redis) │   │
│  │     - 视频存储 (本地磁盘 / 可选阿里云 OSS) │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

### 10.2 核心代码示例

> 以下示例已对齐本项目技术栈：`httpx`（替代 requests）、`ffmpeg-python`（替代 subprocess 裸调）、对接到 `app/integrations/platform.py` 与 `app/pipeline/steps/`。Playwright 作为可选依赖（`uv add playwright`）仅用于 CAS 登录这一步。

**CAS 登录 (Playwright) — 对接 `app/integrations/platform.py` 的登录前置**:
```python
from playwright.async_api import async_playwright

async def cas_login(browser, username: str, password: str):
    """登录北交大 CAS，返回带 Cookie 的 page。

    Cookie 后续导出给 httpx.AsyncClient 复用，使 API 调用与视频下载
    都走同一会话，避免重复登录。对应 app/integrations/platform.py。
    """
    page = await browser.new_page()
    await page.goto("https://mis.bjtu.edu.cn")

    await page.fill('input[placeholder="用户名"]', username)
    await page.fill('input[placeholder="密码"]', password)

    # 验证码方案 A: OCR 自动识别（准确率 ~70%，失败重试最多 3 次后回退方案 B）
    captcha_img = await page.query_selector('img[alt="captcha"]')
    await captcha_img.screenshot(path="captcha.png")
    captcha_code = ocr_recognize("captcha.png")
    await page.fill('input[required]:nth-of-type(3)', captcha_code)

    # 验证码方案 B: 弹出图片让用户手动输入（前端透传，最可靠）
    # captcha_code = await request_user_captcha_input("captcha.png")

    await page.click('button:has-text("登录")')
    await page.wait_for_url("**/mis.bjtu.edu.cn/home/**")
    return page
```

**API 调用获取视频流 — 对接 `app/integrations/platform.py`**:
```python
import httpx
from app.config import settings

async def get_course_sessions(client: httpx.AsyncClient, course_id: int = 131266) -> list[dict]:
    """获取课程录像列表。对应 API 1。"""
    url = f"{settings.platform_base_url}/back/rp/common/teachCalendar.shtml"
    params = {"method": "toDisplyTeachCourses", "courseId": course_id}
    resp = await client.get(url, params=params, timeout=settings.platform_request_timeout)
    resp.raise_for_status()
    return resp.json()["courseSchedList"]

async def get_stream_urls(client: httpx.AsyncClient, course_sched_id: int, user_id: int = 148042) -> dict:
    """获取三路视频流地址。对应 API 2，返回 streamMap。"""
    url = f"{settings.platform_base_url}/back/rp/common/teachCalendar.shtml"
    params = {
        "method": "toDisplyCourseSchedDetail",
        "courseSchedId": course_sched_id,
        "userLevel": 1,
        "userId": user_id,
    }
    resp = await client.get(url, params=params, timeout=settings.platform_request_timeout)
    resp.raise_for_status()
    return resp.json()["res"]["streamMap"]
```

**视频下载 — 对接 `app/pipeline/steps/download.py`（用 ffmpeg-python 拉 HLS）**:
```python
import ffmpeg
from pathlib import Path
from app.config import settings

def download_hls_stream(hls_url: str, out_path: Path) -> Path:
    """下载单路 HLS 流为 mp4。

    本项目 MVP 优先下载教师流（教师音轨最清晰，直接送 ASR）。
    如需三路，分别对 teaStreamHlsUrl/stuStreamHlsUrl/vgaStreamHlsUrl 调用本函数。
    对应 app/pipeline/steps/download.py，由 pipeline/retry.py 包裹重试。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    (
        ffmpeg.input(hls_url, protocol_whitelist="file,http,https,tcp,tls")
        .output(str(out_path), codec="copy", bsf_a="aac_adtstoasc")
        .overwrite_output()
        .run(quiet=True)
    )
    return out_path
```

**音频提取 — 对接 `app/pipeline/steps/audio.py`（ffmpeg 抽人声 + 降噪，送讯飞 ASR）**:
```python
import ffmpeg

def extract_and_denoise(video_path: str, out_path: str) -> str:
    """从教师流 mp4 抽取 16kHz 单声道 wav 并基础降噪，供讯飞 ASR。"""
    (
        ffmpeg.input(video_path)
        .output(out_path, ar=16000, ac=1, af="highpass=f=80,afftdn=nr=12")
        .overwrite_output()
        .run(quiet=True)
    )
    return out_path
```

### 10.3 用户交互流程建议（对接本项目 BackgroundTasks + pipeline）

```
学生在前端登录（本系统账号，非 CAS）
    ↓
首次配置课程平台凭证：前端弹出 CAS 账号密码
    ↓
后端 BackgroundTasks 启动 Playwright 无头浏览器 → CAS 登录页
    ↓
┌─ 方案 A: OCR 自动识别验证码 (准确率 ~70%)
│   ↓ 失败重试 (最多 3 次)，仍失败切换方案 B
│
└─ 方案 B: 前端弹出验证码图片让学生手动输入（透传回后端）
    ↓
登录成功 → 导出 Cookie 给 httpx.AsyncClient 复用
    ↓
integrations/platform.py 调用 API 1 拉取课程列表 → 写入 courses 表
    ↓
学生在前端选择课程/课次 → POST /api/v1/courses/{id}/parse
    ↓
task_service.create_task(status='queued') + BackgroundTasks.add_task(parse_worker.run)
    ↓
pipeline/steps/metadata.py → API 2 取 streamMap（教师/学生/课件三路 HLS）
    ↓
pipeline/steps/download.py → ffmpeg-python 下载教师流（MVP 优先，音轨最清晰）
    ↓
pipeline/steps/audio.py → 抽 16kHz 单声道 wav + 降噪
    ↓
pipeline/steps/asr.py → 讯飞 ASR 句级时间戳转写
    ↓
pipeline/steps/llm.py → 硅基流动大模型（重点/分层总结/两级导图）
    ↓
pipeline/steps/persist.py → 写入 transcripts/keypoints/summaries/mindmaps
    ↓
任务 succeeded → core/cleanup.py 按 CLEANUP_AUDIO_AFTER_TASK 清理中间音频
    ↓
前端轮询 GET /api/v1/tasks/{id} → 展示字幕/重点/总结/导图，点击跳转 Video.js
```

### 10.4 注意事项

1. **水印问题**: 播放器启用了水印 (`waterMark: "用户ID/姓名/日期"`)，但水印是播放器渲染的，下载原始 .ts 文件**不含水印**

2. **观看时长监控**: 播放器每 300 秒发送心跳到 `tqaListenRecord.shtml`，直接下载不触发此机制

3. **Cookie 时效**: CAS Cookie 有时效性 (推测 2-8 小时)，需在 Cookie 过期前完成下载

4. **视频文件大小**: 单节课录像约 3.9 GB (三路流总和)，需确保存储空间充足

5. **网络要求**: 视频服务器 `lmt5.bjtu.edu.cn:8880` 可能限制校内访问，校外需 VPN

6. **并发限制**: 建议限制并发下载数 (2-3 个)，避免 IP 被封

7. **法律法规**: 抓取和下载课程视频仅供个人学习使用，不得公开传播

---

## 11. 与本项目（交大课录智析）集成映射

> 本节把上述平台探索结果落地到本项目已搭建的技术栈与模块。本项目技术栈：FastAPI + BackgroundTasks + SQLite + SQLAlchemy + httpx + ffmpeg-python + 讯飞 ASR + 硅基流动 LLM；前端 React + Video.js + markmap。无 Redis、无 RabbitMQ、无 GPU。

### 11.1 平台 API → 本项目模块映射

| 平台 API | 本项目模块 | 落地说明 |
|---------|-----------|---------|
| CAS 登录 | `app/integrations/platform.py`（新增 `cas_login`）+ Playwright（可选依赖）| 登录成功后导出 Cookie 给 `httpx.AsyncClient` 复用，后续 API 1/2 与视频下载共用会话 |
| API 1 课程录像列表 | `app/integrations/platform.py::list_replay_courses` | 拉取后写入 `courses` 表，`platform_course_id = cId` 用于重复导入识别（FR-01），`video_format='hls'` |
| API 2 视频流地址 | `app/integrations/platform.py::fetch_stream_map` + `app/pipeline/steps/metadata.py` | 取 `streamMap`，存 `teaStreamHlsUrl` 到 `courses.video_url` |
| API 3 知识点列表 | `app/integrations/platform.py`（新增）| 平台已有章节标记 `zsd`，可作为 `keypoints` 的补充/校验来源（与 LLM 抽取的重点做时间点对齐校验，偏差 ≤ 2 秒）|
| API 6 字幕文件 (VTT) | `app/integrations/platform.py`（新增）| 平台已有 VTT 字幕时可直接用，作为讯飞 ASR 结果的补充/校验；无则走 ASR 生成 |
| 视频下载 | `app/pipeline/steps/download.py` + `ffmpeg-python` | 见 11.2 三路流策略 |
| 心跳 API 7 | 不对接 | 直接下载不触发观看时长监控，无需心跳 |

### 11.2 三路视频流处理策略

平台每节课录制教师/学生/课件三路同步 HLS 流，音频内嵌在各自 `.ts` 分段中。

| 流 | 字段 | MVP 策略 |
|----|------|----------|
| 教师流 | `teaStreamHlsUrl` | **优先下载并送 ASR**（教师讲课音频最清晰，含板书口述）|
| 学生流 | `stuStreamHlsUrl` | MVP 不下载（学生/教室全景，音轨价值低）|
| 课件流 | `vgaStreamHlsUrl` | MVP 不下载（PPT 画面，无教学音频）；P1 可考虑截图做重点详解配图 |

> 如需三路，分别对三个 HLS URL 调用 `download.py`；本项目 `TASK_MAX_CONCURRENT` 限制并发，避免 IP 被封（见 10.4 注意事项 6）。

### 11.3 数据模型字段映射（对应 docs/03-data-model.md）

| 平台字段 | 本项目 `courses` 表字段 |
|---------|------------------------|
| `cId` (131266) | `platform_course_id`（唯一索引，重复导入识别）|
| `courseName` | `title` |
| `teacherName` | `teacher_name` |
| `courseBetween` / `teachTimeStr` | `session_label` |
| `classEndTime - classBeginTime` | `duration_sec` |
| `teaStreamHlsUrl` | `video_url` |
| HLS 协议 | `video_format = 'hls'` |
| 平台拉取 | `source = 'platform'`；人工导入则 `source = 'manual'` |

平台 API 3 的 `zsd` 知识点可写入 `keypoints` 表，`category` 按内容归类，`timestamp_sec = zsd_wait_time`，`source_model = 'platform-zsd'`，`ai_generated = False`（平台原生标记，非 AI 生成）。

### 11.4 环境变量补充（追加到 .env.example）

```
# ---------- 北交大课程平台 CAS 对接 ----------
PLATFORM_CAS_LOGIN_URL=https://mis.bjtu.edu.cn
# CAS 用户名/密码不在此配置，由用户打开网页后在前端登录页手动输入
# userId 和 cId 在登录后自动获取，无需手动配置：
#   - userId: cas_login() 从登录后页面自动提取
#   - cId:    list_user_courses() 从课程平台首页自动解析
# CAS 验证码处理方式：ocr / manual
PLATFORM_CAPTCHA_MODE=manual
# CAS Cookie 有效期（秒），过期前完成下载
PLATFORM_COOKIE_TTL=28800
```

> `PLATFORM_BASE_URL` 已在 `.env.example` 中定义，此处补充 CAS 相关项。CAS 凭证禁止入库（已由 `.gitignore` 排除 `.env`）。

### 11.5 依赖补充

本项目 `backend/pyproject.toml` 已含 `httpx`、`ffmpeg-python`、`tenacity`。CAS 登录需追加可选依赖：

```bash
cd backend
uv add playwright          # 加入 pyproject.toml + uv.lock
uv run playwright install chromium   # 安装无头浏览器内核
```

Playwright 仅用于 CAS 登录这一步，不引入 Selenium，避免重复依赖。

### 11.6 风险与降级（对接 docs/05-risk-handling.md）

| 平台侧风险 | 本项目处理 |
|-----------|-----------|
| CAS 验证码识别失败 | OCR 重试 3 次后回退前端手动输入；登录失败不阻塞已缓存课程 |
| CAS Cookie 过期（2-8h）| `PLATFORM_COOKIE_TTL` 监控，过期前重新登录；下载超时由 `TASK_TOTAL_TIMEOUT` 兜底 |
| 校外无法访问 `lmt5.bjtu.edu.cn:8880` | 文档标注需校内/VPN；下载失败标记 `DOWNLOAD_FAIL` 可重试 |
| 三路流总和 ~3.9GB/节 | MVP 仅下载教师流（~1.3GB）；`CACHE_RETENTION_DAYS` 自动清理 |
| IP 并发限制 | `TASK_MAX_CONCURRENT=2` 限流 |
| 水印 | 下载原始 `.ts` 不含水印（水印由播放器渲染），无需处理 |

### 11.7 合规

- 仅抓取已授权课程（`course_authorizations` 校验，NFR-07/12）。
- 课程视频仅供学生个人复习，不公开传播（对应需求文档 NFR-08 数据最小化）。
- CAS 凭证由学生本人提供，系统不存储明文密码（仅保留会话 Cookie）。

---

## 附录: 探索过程中发现的关键 URL 清单

| 用途 | URL |
|------|-----|
| CAS 登录 | `https://cas.bjtu.edu.cn/auth/login/` |
| MIS 门户 | `https://mis.bjtu.edu.cn/home/` |
| 课程平台 | `http://123.121.147.7:88/ve/back/coursePlatform/coursePlatform.shtml` |
| 课程列表 API | `http://123.121.147.7:88/ve/back/rp/common/teachCalendar.shtml?method=toDisplyTeachCourses` |
| 视频流 API | `http://123.121.147.7:88/ve/back/rp/common/teachCalendar.shtml?method=toDisplyCourseSchedDetail` |
| 知识点 API | `http://123.121.147.7:88/ve/webservices/qxkt.shtml?method=queryVeRpInfoZsd` |
| 字幕 API | `http://123.121.147.7:88/ve/webservices/qxkt.shtml?method=getSubtitleFile` |
| 心跳 API | `http://123.121.147.7:88/ve/back/tqa/tqaListenRecord.shtml?method=insertListenRecord` |
| HLS 视频服务器 | `https://lmt5.bjtu.edu.cn:8880/vod11/_definst_/...` |
| RTMP 视频服务器 | `rtmp://123.121.147.15:1935/vod11/mp4:/...` |
| 播放器 JS | `http://123.121.147.7:88/ve/ui/jydH5Player/jyd20241210.min.js` |
