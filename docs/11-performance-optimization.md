# 性能优化方案：全链路耗时与网络消耗分析

> 对应 `docs/04-data-flow.md` 六步数据流，针对当前 pipeline 全链路的耗时瓶颈与网络开销给出量化分析与优化方案。

## 一、完整链路全景

```
前端 POST /courses/{id}/parse
  → threading.Thread → parse_worker.run → orchestrator.run_pipeline
    → Step 1 metadata.fetch_metadata     (Playwright CAS/SSO + 平台 API 1/2/3/6)
    → Step 2+3 download.download_audio_from_url  (ffmpeg 拉流 → 16kHz WAV)
    → Step 4 _resolve_transcripts         (平台 VTT 优先 / 否则 ASR 分片并行)
    → Step 5 llm.run_llm                  (重点 + 总结 + 导图，串行)
    → Step 6 persist.save_results         (SQLite 批量写入)
前端 useTask.ts 每 2s 轮询 GET /tasks/{id}
```

### 关键配置项（`backend/app/config.py`）

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `task_total_timeout` | 3600s | 单任务整体超时 |
| `task_max_concurrent` | 2 | 任务最大并发数 |
| `siliconflow_asr_timeout` | 300s | ASR 超时 |
| `siliconflow_asr_max_retry` | 3 | ASR 重试次数 |
| `siliconflow_asr_chunk_seconds` | 480s | 单分片最长时长 |
| `siliconflow_asr_chunk_max_mb` | 20MB | 单分片最大体积 |
| `siliconflow_asr_workers` | 4 | ASR 并行转写分片数 |
| `siliconflow_timeout` | 120s | LLM 超时 |
| `siliconflow_max_retry` | 3 | LLM 重试次数 |
| `siliconflow_max_input_chars` | 12000 | LLM 单次投喂上限 |
| `platform_request_timeout` | 60s | 平台 HTTP 超时 |
| `vtt_min_coverage` | 0.5 | VTT 复用覆盖率阈值 |

## 二、各阶段耗时分析（以 90 分钟课堂为例）

| 阶段 | 操作 | 耗时估算 | 瓶颈 | 代码位置 |
|------|------|---------|------|---------|
| **Step 1 元数据** | Playwright 启动 Chromium + CAS/SSO 登录 + API 1/2/3/6 串行 | **20-35s** | Chromium 冷启动 + CAS 登录交互 | `metadata.py:53` → `platform.py:1004` |
| **Step 2+3 音频提取** | ffmpeg 从 HLS URL 提取音频 → 16kHz mono WAV | **3-10 min** | 网络下载视频流 + ffmpeg 转码 | `download.py:61` |
| **Step 4 ASR** | 90min 音频切 ~12 片(每片 ≤20MB/480s)，4 并发上传 | **2-4 min** | 外部 ASR API 处理速度 | `siliconflow_asr.py:138` |
| **Step 4 VTT 复用** | 平台字幕覆盖 ≥50% 时直接用 | **~0s** | — | `orchestrator.py:162` |
| **Step 5 LLM** | 重点 + 总结 + 导图 **串行**调用，分段 map-reduce | **1.5-4 min** | 串行 LLM 调用 | `llm.py:80-96` |
| **Step 6 持久化** | SQLite 批量写入 ~500-800 行转写 | **1-3s** | — | `persist.py:25` |
| **总耗时（走 ASR）** | | **7-19 min** | | |
| **总耗时（VTT 复用）** | | **5-15 min** | | |

## 三、网络消耗分析

### 3.1 外部 API 调用清单（单任务）

| 组件 | 调用次数 | 请求大小 | 响应大小 | 总流量 | 代码位置 |
|------|---------|---------|---------|--------|---------|
| Playwright CAS/SSO | 1 次 | ~1KB | ~5KB cookies | ~6KB | `platform.py:1004` |
| 平台 API 1 课程列表 | 1 次 | ~0.5KB | ~10-50KB | ~50KB | `platform.py:1006` |
| 平台 API 2 视频流 | N 次(课次数) | ~0.5KB | ~2KB | ~2N KB | `platform.py:1014` **串行** |
| 平台 API 3 知识点 | 1 次 | ~0.5KB | ~5-20KB | ~20KB | `platform.py:1032` |
| 平台 API 6 VTT 字幕 | 1 次 | ~0.5KB | ~50-500KB | ~500KB | `platform.py:1044` |
| **ffmpeg 拉流** | 1 次 | — | **~300-700MB** | **~700MB** | `download.py:76` |
| **ASR 上传** | M 次(分片数) | **≤20MB/次** | ~50-200KB | **~170MB↑ + ~2MB↓** | `siliconflow_asr.py:157` |
| **LLM 请求** | K 次(分段×3子任务) | ≤12KB/次 | ~5-50KB | ~100KB | `siliconflow_llm.py:69` |
| **前端轮询** | **300-600 次** | ~0.5KB | ~1KB | ~1MB | `useTask.ts:16` |

### 3.2 网络消耗热点

```
ffmpeg 拉流     ████████████████████████████  ~700MB  (最大)
ASR 上传        ████████████████████          ~170MB
VTT 字幕下载    █                             ~500KB
前端轮询        █                             ~1MB (高频低量)
LLM 请求        ▏                             ~100KB
平台 API        ▏                             ~100KB
```

## 四、关键问题定位

### 问题 1：httpx 客户端不复用（连接池浪费）

每次调用都 `with httpx.Client(...)` / `async with _client(...)` 新建客户端，无 keep-alive 复用。

- ASR：每分片新建客户端 `siliconflow_asr.py:157`
- LLM：每次调用新建客户端 `siliconflow_llm.py:69`
- 平台 API：每次调用新建 `platform.py:30-35`

**影响**：每次 TCP 握手 + TLS 协商开销 ~50-200ms，ASR 12 片 + LLM 8 次 + 平台 5 次 ≈ 25 次冗余连接建立。

### 问题 2：LLM 三子任务串行（`orchestrator.py:80-96`）

重点、总结、导图三个子任务**串行**调用，各自 10-30s，总耗时叠加：

```python
keypoints = _extract_keypoints(text, ...)   # 10-30s
summary = _generate_summary(text, ...)       # 10-30s
mindmap = _generate_mindmap(text, ...)       # 10-30s
# 串行总耗 30-90s，并行只需 10-30s
```

### 问题 3：LLM 分段 map 串行（`siliconflow_llm.py:211,311,399`）

多段转写逐段 `for chunk in chunks` 调用，无并发：

```python
for index, chunk in enumerate(chunks, start=1):
    payload = _chat_json(_keypoint_prompt(chunk, ...))  # 串行
```

### 问题 4：平台 API 串行（`platform.py:1013-1015`）

`fetch_course_meta` 对每个 replay 串行调 `get_stream_map`：

```python
for r in replays:
    stream_map = await get_stream_map(cookie_dict, r["id"], user_id)  # 串行
```

### 问题 5：Playwright 重复启动 Chromium

CAS 登录、`sync_courses_from_ve`、`get_stream_map_via_browser` 各自启动一次 Chromium（~300-500MB 内存，~3-5s 冷启动）。

### 问题 6：前端固定 2s 轮询（`useTask.ts:16`）

无论任务进度如何，固定 2s 间隔。10-20 分钟任务产生 **300-600 次** HTTP 请求，大部分返回相同状态。

### 问题 7：ASR 分片全量落盘再上传（`siliconflow_asr.py:148-150`）

`_create_all_chunks` 先把所有分片写到临时目录，再并行上传。90 分钟音频产生 ~12 个文件 ~170MB 磁盘 IO。

### 问题 8：无 HTTP 响应缓存

平台课程列表、知识点、VTT 字幕等重复请求无缓存，重试任务会重新拉取。

## 五、优化方案

### 优化 1：LLM 三子任务并行化 ⭐ 最高收益

**现状**：`llm.py:80-96` 串行调用三个子任务，总耗 30-90s

**方案**：用 `concurrent.futures.ThreadPoolExecutor` 并行调用

```python
# llm.py run_llm() 改为并行
import concurrent.futures

def run_llm(transcripts, course, task_id):
    text = format_transcript(transcripts)
    if not text:
        raise StepError("LLM_ERROR", "转写为空", step="llm")

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_kp = executor.submit(_safe_call, _extract_keypoints, text, course.title)
        fut_sm = executor.submit(_safe_call, _generate_summary, text, course.title)
        fut_mm = executor.submit(_safe_call, _generate_mindmap, text, course.title)
        keypoints, kp_err = fut_kp.result()
        summary, sm_err = fut_sm.result()
        mindmap, mm_err = fut_mm.result()

    failures = [e for e in (kp_err, sm_err, mm_err) if e]
    if len(failures) == 3:
        raise StepError("LLM_ERROR", "全部失败", step="llm")
    # ...
```

**收益**：耗时从 30-90s → **10-30s**，节省 ~50%

**风险**：需注意 API 429 限流（3 并发一般安全）

### 优化 2：LLM 分段 map 并行化

**现状**：`siliconflow_llm.py:211` 逐段串行调 LLM

**方案**：分段 map 阶段用线程池并行（控制并发 2-3）

```python
# extract_keypoints 分段并行
def extract_keypoints(transcript_text, course_title):
    chunks = _split_chunks(transcript_text)
    if len(chunks) == 1:
        payload = _chat_json(_keypoint_prompt(chunks[0], course_title, 1, 1))
        return _dedupe_keypoints(_normalize_keypoints(payload.get("keypoints")))

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(chunks))) as ex:
        futures = [ex.submit(_chat_json, _keypoint_prompt(c, course_title, i, len(chunks)))
                   for i, c in enumerate(chunks, 1)]
        collected = []
        for f in futures:
            collected.extend(_normalize_keypoints(f.result().get("keypoints")))
    return _dedupe_keypoints(collected)
```

**收益**：2 段时从 2 次串行 → 1 批并行，节省 ~40%

### 优化 3：httpx 客户端复用（连接池）

**现状**：每次调用新建客户端

**方案**：模块级共享客户端

```python
# siliconflow_llm.py
_llm_client: httpx.Client | None = None

def _get_client() -> httpx.Client:
    global _llm_client
    if _llm_client is None or _llm_client.is_closed:
        timeout = httpx.Timeout(settings.siliconflow_timeout, connect=10.0, write=30.0, pool=10.0)
        _llm_client = httpx.Client(timeout=timeout)
    return _llm_client
```

**收益**：消除 ~25 次 TCP/TLS 握手，节省 ~2-5s

### 优化 4：前端轮询自适应 + SSE 替代

**现状**：固定 2s 轮询，300-600 次请求

**方案 A（低成本）**：自适应轮询间隔

```typescript
// useTask.ts — 根据进度动态调整间隔
const poll = async () => {
  const t = await getTask(taskId);
  setTask(t);
  if (t.status === 'succeeded' || t.status === 'failed') return clearInterval(timer);
  // 进度变化快时间隔短，停滞时间隔拉长
  const interval = t.progress < 90 ? 2000 : 5000;
  timer = setInterval(poll, interval);
};
```

**方案 B（最优）**：SSE 推送替代轮询

```python
# backend/app/api/v1/tasks.py
@router.get("/{task_id}/stream")
async def stream_task(task_id: int):
    async def event_generator():
        while True:
            task = db.get(ParseTask, task_id)
            yield {"data": json.dumps(task_to_dict(task))}
            if task.status in ("succeeded", "failed"):
                break
            await asyncio.sleep(2)
    return EventSourceResponse(event_generator())
```

**收益**：消除 300-600 次轮询请求 → 1 次 SSE 连接

### 优化 5：平台 API 并行化

**现状**：`platform.py:1013` 对每个 replay 串行调 `get_stream_map`

**方案**：`asyncio.gather` 并行

```python
# platform.py fetch_course_meta
replays = await list_replay_courses(cookie_dict, target["cId"])
tasks = [get_stream_map(cookie_dict, r["id"], user_id) for r in replays]
stream_maps = await asyncio.gather(*tasks, return_exceptions=True)
result = [{"replay": r, "stream_map": sm}
          for r, sm in zip(replays, stream_maps) if not isinstance(sm, Exception)]
```

**收益**：N 个课次从 N×2s → 2s

### 优化 6：ASR 流式分片上传

**现状**：`siliconflow_asr.py:148` 先切所有分片落盘，再上传

**方案**：边切边上传，用生产者-消费者模式

```python
# 边切边传：切一片就提交到线程池
import queue

def _transcribe_wave(path, progress_callback):
    chunk_queue: queue.Queue = queue.Queue(maxsize=workers + 2)

    def _producer():
        with wave.open(str(path), "rb") as w:
            # ... 切片逻辑，每切一片放 chunk_queue
        chunk_queue.put(None)  # 结束信号

    def _consumer(idx, chunk_path, start_sec, end_sec):
        with _get_client() as client:
            payload = _request_transcription(client, chunk_path)
            return idx, _sentences_from_payload(payload, offset=start_sec, chunk_end=end_sec)

    # 生产者线程 + 消费者线程池
```

**收益**：减少磁盘 IO 等待，分片在切完前就开始上传

### 优化 7：平台元数据缓存

**现状**：每次任务重新拉取平台课程列表、知识点、VTT

**方案**：按 `platform_course_id` + `replay_id` 做短期内存缓存

```python
# platform.py
from functools import lru_cache
from datetime import timedelta

_meta_cache: dict[str, tuple[float, dict]] = {}
_META_TTL = 300  # 5 分钟

async def fetch_course_meta(platform_course_id: str | None) -> dict:
    now = time.time()
    cached = _meta_cache.get(platform_course_id)
    if cached and now - cached[0] < _META_TTL:
        return cached[1]
    # ... 原逻辑
    _meta_cache[platform_course_id] = (now, result)
    return result
```

**收益**：重试任务或同课程多次解析时跳过平台拉取，节省 20-35s

## 六、流量/带宽优化方案

以下方案专门针对**网络流量（带宽消耗）**进行优化，与第五章的耗时优化互补。

### 流量优化 1：ASR 上传音频压缩 ⭐⭐⭐ 最高流量收益

**现状**：`siliconflow_asr.py:90` 上传 **未压缩 PCM WAV**（16kHz mono 16bit = 32KB/s），90 分钟音频总上传量 ~172MB，是全链路最大的上行流量。

**方案**：ffmpeg 提取音频时直接输出压缩格式（Opus/FLAC/MP3），大幅减小上传体积。

```python
# download.py download_audio_from_url() — 改为输出 Opus
cmd = [
    "ffmpeg",
    # ... 输入参数不变
    "-vn",
    "-acodec", "libopus",       # Opus 编码（替代 pcm_s16le）
    "-ar", "16000",
    "-ac", "1",
    "-b:a", "24k",              # 24kbps 足够语音识别
    "-progress", "pipe:2",
    str(out_path).replace(".wav", ".opus"),
]
```

| 格式 | 码率 | 90min 体积 | 压缩比 |
|------|------|-----------|--------|
| PCM WAV（当前） | 256kbps | **~172MB** | 1× |
| FLAC | ~80kbps | ~54MB | 3.2× |
| MP3 16kHz | 32kbps | ~22MB | 7.8× |
| **Opus 16kHz** | **24kbps** | **~16MB** | **10.8×** |

**收益**：ASR 上传流量从 ~170MB → **~16MB**，减少 **~90%**
**前提**：需确认硅基流动 ASR API 接受非 WAV 格式（多数 OpenAI 兼容接口支持 mp3/opus/flac）
**回退**：若 API 不支持，保持 WAV 但在 HTTP 层启用请求压缩（multipart 无法压缩，故优先验证格式支持）

### 流量优化 2：API 响应 GZip 压缩 ⭐⭐⭐

**现状**：FastAPI 未启用响应压缩，转写/重点/总结等 JSON 响应全量明文传输。

- `lectures.py:23` `list_transcripts` — 500-800 句转写，JSON ~100-300KB
- `lectures.py:33` `list_keypoints` — 20-40 条重点，JSON ~20-50KB
- `lectures.py:43` `get_summary` — 分层总结，JSON ~10-30KB
- `lectures.py:56` `get_mindmap` — 思维导图，JSON ~10-30KB

**方案**：启用 `GZipMiddleware`

```python
# backend/app/main.py
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1024)  # >1KB 的响应才压缩
```

**收益**：JSON 文本压缩率 60-80%，转写响应 300KB → ~60KB，全链路前端下载流量减少 ~70%

### 流量优化 3：转写结果分页加载 ⭐⭐

**现状**：`lectures.py:17-24` `list_transcripts` 一次返回所有转写句（500-800 句），前端首屏只需部分。

**方案**：支持 `limit` / `offset` 分页，前端按需加载

```python
# api/v1/lectures.py
@router.get("/{lecture_id}/transcripts", response_model=list[TranscriptOut])
def list_transcripts(
    lecture_id: int,
    offset: int = 0,
    limit: int = 100,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> list[Transcript]:
    stmt = (
        select(Transcript)
        .where(Transcript.lecture_id == lecture_id)
        .order_by(Transcript.start_sec)
        .offset(offset)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())
```

**收益**：首屏加载从 ~300KB → ~40KB（100 句），减少 ~87%；后续滚动按需加载

### 流量优化 4：前端结果聚合端点 ⭐⭐

**现状**：前端展示解析结果时分别请求 4 个端点（transcripts / keypoints / summary / mindmap），4 次 HTTP 往返。

**方案**：新增聚合端点，一次返回概览数据（不含全量转写）

```python
# api/v1/lectures.py
@router.get("/{lecture_id}/overview")
def get_overview(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> dict:
    """一次返回重点 + 总结 + 导图 + 转写摘要（首句 + 末句 + 总句数）。"""
    return {
        "keypoints": ...,    # 全量（体积小）
        "summary": ...,
        "mindmap": ...,
        "transcript_meta": {   # 不含全量转写，前端按需分页拉取
            "total": count,
            "first": first_sentence,
            "last": last_sentence,
        },
    }
```

**收益**：4 次请求 → 1 次，减少 3 次往返 + 重复 header 开销

### 流量优化 5：LLM 请求 payload 精简 ⭐

**现状**：`siliconflow_llm.py:19-31` 转写格式为 `[123.4] 文本`，时间戳占每个 token 约 8-10 字符。分段重叠区 60s 导致重复传输。

**方案**：

1. 时间戳格式紧凑化：`[123.4]` → `[123]`（精度到秒足够，减少 ~30% 时间戳字符）
2. 减少分段重叠：`_CHUNK_OVERLAP_SEC` 从 60s → 30s，减少重叠区重复传输

```python
# siliconflow_llm.py
_CHUNK_OVERLAP_SEC = 30.0  # 从 60.0 降至 30.0

# format_transcript 时间戳精度
lines.append(f"[{start:.0f}] {text}")  # 从 :.1f 改为 :.0f
```

**收益**：LLM 请求 payload 减少 ~15-20%，重叠区重复传输减半

### 流量优化 6：ffmpeg 只拉音频 HLS 分片 ⭐

**现状**：`download.py:76` ffmpeg 从完整 HLS 流拉取，虽 `-vn` 丢弃视频，但仍需下载视频分片才能提取音频（取决于 HLS 结构）。

**方案**：若平台提供独立音频 HLS 流（`teaStreamAudioHlsUrl`），优先使用，避免下载视频分片。

```python
# metadata.py _apply_meta() — 优先音频独立流
video_url = (
    stream_map.get("teaStreamAudioHlsUrl")  # 新增：独立音频流优先
    or stream_map.get("teaStreamHlsUrl")
    or stream_map.get("teaStreamUrl")
    or stream_map.get("stuStreamHlsUrl")
)
```

**收益**：若平台有独立音频流，下载量从 ~700MB → ~50-100MB（仅音频），减少 ~85%
**前提**：需确认平台 streamMap 是否包含独立音频流字段

### 流量优化 7：平台 VTT 字幕落盘缓存 ⭐

**现状**：`metadata.py:164` 每次任务都重新拉取平台 VTT 字幕（~50-500KB），即使同课程已拉取过。

**方案**：VTT 拉取后落盘到 `storage/` 目录，按 `replay_id` 缓存，7 天过期（复用 `cache_retention_days`）

```python
# metadata.py _prefetch_platform_assets()
vtt_cache_path = Path(settings.storage_root) / "vtt_cache" / f"{replay_id}.vtt"
if vtt_cache_path.is_file() and not _is_expired(vtt_cache_path):
    ctx.vtt_sentences = platform_assets.parse_vtt(vtt_cache_path.read_text("utf-8"))
    return

vtt_text = asyncio.run(platform.get_subtitle_vtt(cookies, replay_id))
vtt_cache_path.parent.mkdir(parents=True, exist_ok=True)
vtt_cache_path.write_text(vtt_text, "utf-8")
ctx.vtt_sentences = platform_assets.parse_vtt(vtt_text)
```

**收益**：同课程重试/重解析时跳过 VTT 下载，节省 ~500KB/次

## 七、优化收益汇总

### 耗时优化

| 优化项 | 改动量 | 耗时节省 | 优先级 |
|--------|--------|---------|--------|
| **1. LLM 三子任务并行** | 小 | **20-60s** | ⭐⭐⭐ |
| **2. LLM 分段 map 并行** | 中 | 10-30s | ⭐⭐ |
| **3. httpx 客户端复用** | 小 | 2-5s | ⭐⭐ |
| **4. 前端 SSE 替代轮询** | 中 | — | ⭐⭐⭐ |
| **5. 平台 API 并行** | 小 | N×2s | ⭐ |
| **6. ASR 流式分片** | 大 | 10-20s | ⭐ |
| **7. 平台元数据缓存** | 小 | 20-35s (重试时) | ⭐⭐ |

### 流量优化

| 优化项 | 改动量 | 流量节省 | 优先级 |
|--------|--------|---------|--------|
| **F1. ASR 音频压缩上传** | 中 | **~154MB/任务（90%）** | ⭐⭐⭐ |
| **F2. API 响应 GZip** | 极小 | **~70% 响应体积** | ⭐⭐⭐ |
| **F3. 转写分页加载** | 小 | 首屏 ~260KB → ~40KB | ⭐⭐ |
| **F4. 结果聚合端点** | 小 | 3 次请求往返 | ⭐⭐ |
| **F5. LLM payload 精简** | 极小 | ~15-20% 请求体积 | ⭐ |
| **F6. 只拉音频 HLS** | 中 | ~600MB（85%）（若可用） | ⭐ |
| **F7. VTT 落盘缓存** | 小 | ~500KB/次（重试时） | ⭐ |

### 综合效果

**耗时**：
- 首次解析：7-19 min → **5-13 min**（节省 ~25%）
- 重试/同课程复用：额外节省 20-35s

**流量（单任务）**：
- 上行：~172MB → **~16MB**（F1，减少 90%）
- 下行（ffmpeg 拉流）：~700MB → **~50-100MB**（F6，若平台支持独立音频流）
- 前端 API 响应：压缩 ~70%（F2 + F3）
- 前端轮询：~600 次请求 → 1 次 SSE 连接（优化 4）

## 八、推荐实施顺序

### 第一梯队（改动小、收益大）
1. **F2** API 响应 GZip — 一行代码，全局收益
2. **优化 1** LLM 三子任务并行 — 耗时收益最大
3. **F1** ASR 音频压缩上传 — 流量收益最大
4. **优化 4** SSE 替代轮询 — 消除高频无效请求

### 第二梯队（中等改动、显著收益）
5. **优化 3** httpx 客户端复用 — 通用基础设施
6. **F3** 转写分页加载 — 前端首屏体验
7. **F4** 结果聚合端点 — 减少请求往返
8. **优化 7 / F7** 平台元数据 + VTT 缓存 — 重试场景

### 第三梯队（按需实施）
9. **优化 2** LLM 分段 map 并行
10. **优化 5** 平台 API 并行
11. **F5** LLM payload 精简
12. **F6** 只拉音频 HLS（需平台支持）
13. **优化 6** ASR 流式分片