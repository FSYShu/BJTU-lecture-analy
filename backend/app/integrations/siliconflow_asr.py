"""硅基流动 ASR 客户端（XingChenASR）。音频 → 句级时间戳转写。

对应 docs/09-mvp-implementation-plan.md A1、docs/05-risk-handling.md API 异常降级。

设计要点：
- 与 LLM 共用 ``SILICONFLOW_API_KEY`` / ``SILICONFLOW_BASE_URL``，Bearer Token 鉴权；
- 长回放音频（60–120 分钟）远超单次上传限制，按 ``SILICONFLOW_ASR_CHUNK_SECONDS`` /
  ``SILICONFLOW_ASR_CHUNK_MAX_MB`` 切成 16kHz 单声道 WAV 分片，逐片转写后加上分片起始偏移，
  拼回全局时间轴；
- 返回结构兼容 ``verbose_json`` 的 segments / words，以及仅有 text 的降级形态；
- 输出前做时间戳校验：单调不减、``start_sec < end_sec``、空洞告警（AC-06-02、NFR-02）。

本模块是**同步**实现（与 download.py / audio.py 一致），由 ``pipeline/steps/asr.py`` 的
重试装饰器包裹，因此失败时抛出的异常必须是 ``TimeoutError`` / ``RuntimeError`` 之一。
"""
from __future__ import annotations

import shutil
import tempfile
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.config import settings

_TRANSCRIPTIONS_PATH = "/audio/transcriptions"

# 句末标点：用于把词级/整段文本聚合成句
_SENTENCE_END = "。！？!?；;…"
_SENTENCE_SPLIT_RE = r"(?<=[。！？!?；;…])"
_MAX_SENTENCE_CHARS = 80
_GAP_WARN_SEC = 10.0

# 各实现可能使用的字段名，统一兼容
_START_KEYS = ("start", "start_sec", "start_time", "begin", "bg", "from")
_END_KEYS = ("end", "end_sec", "end_time", "stop", "ed", "to")
_TEXT_KEYS = ("text", "sentence", "content", "word", "value")


def transcribe(audio_path: str) -> list[dict]:
    """语音转写：音频 → 句级时间戳 ``[{"text", "start_sec", "end_sec"}, ...]``。

    这是 pipeline Step 4 的唯一入口，签名必须保持同步。
    """
    path = Path(audio_path)
    if not path.is_file():
        raise RuntimeError(f"音频文件不存在：{audio_path}")
    _ensure_credentials()

    if _is_wave(path):
        sentences = _transcribe_wave(path)
    else:
        # 非 WAV（理论上不会走到，audio.py 统一产出 16kHz WAV）：整体上传，时间轴按体积估算
        logger.warning("[asr] 输入不是 WAV，按整体上传处理：{}", path.name)
        sentences = _transcribe_single(path, offset=0.0, chunk_end=_estimate_duration(path))

    sentences = _validate(sentences)
    logger.info("[asr] 转写完成：{} 句，覆盖 {:.1f}s–{:.1f}s",
                len(sentences),
                sentences[0]["start_sec"] if sentences else 0.0,
                sentences[-1]["end_sec"] if sentences else 0.0)
    return sentences


# --------------------------------------------------------------------------- #
# 凭证与请求
# --------------------------------------------------------------------------- #
def _ensure_credentials() -> None:
    if not settings.siliconflow_api_key:
        raise RuntimeError("硅基流动 API Key 未配置（SILICONFLOW_API_KEY）")
    if not settings.siliconflow_base_url:
        raise RuntimeError("硅基流动 Base URL 未配置（SILICONFLOW_BASE_URL）")


def _endpoint() -> str:
    return settings.siliconflow_base_url.rstrip("/") + _TRANSCRIPTIONS_PATH


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.siliconflow_api_key}"}


def _request_transcription(client: httpx.Client, path: Path) -> dict[str, Any]:
    """上传单个音频文件并返回 JSON。

    先按 ``verbose_json`` + 时间戳粒度请求；若接口/模型不支持（400/422），
    退回最小参数集重试一次。429/5xx 交给上层重试装饰器处理。
    """
    base = {"model": settings.siliconflow_asr_model}
    verbose = {
        **base,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
    }

    resp = _post(client, path, verbose)
    if resp.status_code in (400, 422):
        logger.warning("[asr] 接口不接受 verbose_json/时间戳粒度（HTTP {}），退回基础参数：{}",
                       resp.status_code, resp.text[:200])
        resp = _post(client, path, base)

    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:  # 非 JSON 响应
        raise RuntimeError(f"ASR 返回非 JSON：{resp.text[:200]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ASR 返回结构异常（顶层不是对象）")
    return payload


def _post(client: httpx.Client, path: Path, data: dict[str, Any]) -> httpx.Response:
    with path.open("rb") as fh:
        return client.post(
            _endpoint(),
            headers=_headers(),
            data=data,
            files={"file": (path.name, fh, "audio/wav")},
        )


# --------------------------------------------------------------------------- #
# 分片
# --------------------------------------------------------------------------- #
def _is_wave(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getframerate() > 0 and w.getnchannels() > 0
    except (wave.Error, EOFError, OSError):
        return False


@contextmanager
def _wav_chunks(audio_path: Path) -> Iterator[tuple[Path, float, float]]:
    """把 WAV 切成若干分片，yield ``(分片文件, 起始秒, 结束秒)``。"""
    max_seconds = max(30, settings.siliconflow_asr_chunk_seconds)
    max_bytes = max(1, settings.siliconflow_asr_chunk_max_mb) * 1024 * 1024
    tmpdir = Path(tempfile.mkdtemp(prefix="sf_asr_"))
    try:
        with wave.open(str(audio_path), "rb") as w:
            rate = w.getframerate()
            channels = w.getnchannels()
            width = w.getsampwidth()
            frame_bytes = max(1, channels * width)
            by_time = int(max_seconds * rate)
            by_size = int(max_bytes // frame_bytes)
            frames_per_chunk = max(1, min(by_time, by_size))
            logger.info("[asr] 分片参数：{}Hz {}ch {}bit，每片 {} 帧（≈{:.0f}s）",
                        rate, channels, width * 8, frames_per_chunk, frames_per_chunk / rate)

            index = 0
            while True:
                frames = w.readframes(frames_per_chunk)
                if not frames:
                    break
                start_sec = index * frames_per_chunk / rate
                end_sec = start_sec + len(frames) / frame_bytes / rate
                chunk_path = tmpdir / f"chunk_{index:04d}.wav"
                with wave.open(str(chunk_path), "wb") as out:
                    out.setnchannels(channels)
                    out.setsampwidth(width)
                    out.setframerate(rate)
                    out.writeframes(frames)
                try:
                    yield chunk_path, start_sec, end_sec
                finally:
                    chunk_path.unlink(missing_ok=True)
                index += 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _transcribe_wave(path: Path) -> list[dict]:
    """按分片逐段转写并拼接全局时间轴。"""
    sentences: list[dict] = []
    with httpx.Client(timeout=settings.siliconflow_asr_timeout) as client:
        for chunk_path, start_sec, end_sec in _wav_chunks(path):
            payload = _request_transcription(client, chunk_path)
            part = _sentences_from_payload(payload, offset=start_sec, chunk_end=end_sec)
            logger.info("[asr] 分片 {} 转写 {} 句（{:.0f}s–{:.0f}s）",
                        chunk_path.name, len(part), start_sec, end_sec)
            sentences.extend(part)
    return sentences


def _transcribe_single(path: Path, offset: float, chunk_end: float) -> list[dict]:
    with httpx.Client(timeout=settings.siliconflow_asr_timeout) as client:
        payload = _request_transcription(client, path)
    return _sentences_from_payload(payload, offset=offset, chunk_end=chunk_end)


def _estimate_duration(path: Path) -> float:
    """按 16kHz 单声道 16bit 估算音频时长（仅在非 WAV 兜底时使用）。"""
    return max(0.0, path.stat().st_size / (16000 * 2))


# --------------------------------------------------------------------------- #
# 响应解析
# --------------------------------------------------------------------------- #
def _sentences_from_payload(payload: dict[str, Any], offset: float, chunk_end: float) -> list[dict]:
    segments = payload.get("segments")
    if isinstance(segments, list) and segments:
        return _from_segments(segments, offset)

    words = payload.get("words")
    if isinstance(words, list) and words:
        return _from_words(words, offset)

    # 兼容部分实现的字段命名
    for key in ("sentences", "utterances", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return _from_segments(value, offset)

    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return _from_text(text, offset, chunk_end, estimated=True)

    raise RuntimeError(f"ASR 返回中既无时间戳片段也无文本：{str(payload)[:200]}")


def _from_segments(segments: list[Any], offset: float) -> list[dict]:
    out: list[dict] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = _pick_text(seg)
        start = _pick_number(seg, _START_KEYS)
        end = _pick_number(seg, _END_KEYS)
        if not text or start is None:
            continue
        if end is None or end <= start:
            end = start + 0.5
        out.extend(_split_long(text, start + offset, end + offset))
    return out


def _from_words(words: list[Any], offset: float) -> list[dict]:
    """词级时间戳 → 句级：按句末标点/长度切分。"""
    out: list[dict] = []
    buffer: list[str] = []
    start: float | None = None
    end: float | None = None

    def flush() -> None:
        nonlocal buffer, start, end
        if buffer and start is not None:
            text = "".join(buffer).strip()
            if text:
                out.extend(_split_long(text, start + offset, (end or start) + offset))
        buffer, start, end = [], None, None

    for word in words:
        if not isinstance(word, dict):
            continue
        text = _pick_text(word) or ""
        w_start = _pick_number(word, _START_KEYS)
        w_end = _pick_number(word, _END_KEYS)
        if w_start is None:
            continue
        if start is None:
            start = w_start
        buffer.append(text)
        end = w_end if w_end is not None else w_start
        joined = "".join(buffer).strip()
        if joined and joined[-1] in _SENTENCE_END:
            flush()
        elif len(joined) >= _MAX_SENTENCE_CHARS:
            flush()
    flush()
    return out


def _from_text(text: str, offset: float, chunk_end: float, *, estimated: bool) -> list[dict]:
    """仅有纯文本时：按标点断句，并按字数比例估算时间轴。

    这是**降级路径**：接口未返回任何时间戳时的兜底，精度低于真实时间戳，
    因此记 warning 并可通过 ``SILICONFLOW_ASR_ALLOW_ESTIMATED_TIMESTAMPS=false`` 关闭。
    """
    if not settings.siliconflow_asr_allow_estimated_timestamps:
        raise RuntimeError("ASR 接口未返回时间戳，且已禁用时间轴估算（SILICONFLOW_ASR_ALLOW_ESTIMATED_TIMESTAMPS=false）")

    sentences = _split_sentences(text)
    if not sentences:
        return []
    span = max(0.1, chunk_end - offset)
    total_chars = sum(len(s) for s in sentences) or 1
    logger.warning("[asr] 接口未返回时间戳，按字数估算时间轴（{} 句，跨度 {:.0f}s）",
                   len(sentences), span)

    out: list[dict] = []
    cursor = offset
    for sentence in sentences:
        duration = span * len(sentence) / total_chars
        out.append({
            "text": sentence,
            "start_sec": cursor,
            "end_sec": cursor + duration,
        })
        cursor += duration
    return out


def _split_sentences(text: str) -> list[str]:
    import re

    normalized = text.replace("\r", "\n")
    parts: list[str] = []
    for line in normalized.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts.extend(p.strip() for p in re.split(_SENTENCE_SPLIT_RE, line) if p.strip())

    # 过长的句子再按逗号切分，避免单条字幕过长
    result: list[str] = []
    for part in parts:
        if len(part) <= _MAX_SENTENCE_CHARS * 2:
            result.append(part)
            continue
        buffer = ""
        for piece in re.split(r"(?<=[，,、])", part):
            if len(buffer) + len(piece) > _MAX_SENTENCE_CHARS and buffer:
                result.append(buffer)
                buffer = piece
            else:
                buffer += piece
        if buffer:
            result.append(buffer)
    return result


def _split_long(text: str, start: float, end: float) -> list[dict]:
    """把过长片段按标点切成多条，时间按字数比例分配。"""
    if len(text) <= _MAX_SENTENCE_CHARS * 2:
        return [{"text": text, "start_sec": start, "end_sec": end}]

    pieces = _split_sentences(text)
    if len(pieces) <= 1:
        return [{"text": text, "start_sec": start, "end_sec": end}]

    total_chars = sum(len(p) for p in pieces) or 1
    span = max(0.1, end - start)
    out: list[dict] = []
    cursor = start
    for piece in pieces:
        duration = span * len(piece) / total_chars
        out.append({"text": piece, "start_sec": cursor, "end_sec": cursor + duration})
        cursor += duration
    return out


def _pick_text(item: dict) -> str:
    for key in _TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_number(item: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def _validate(sentences: list[dict]) -> list[dict]:
    """时间戳校验：单调不减、start < end、空洞告警（AC-06-02、NFR-02）。"""
    cleaned: list[dict] = []
    for item in sentences:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = float(item.get("start_sec", 0.0))
        end = float(item.get("end_sec", 0.0))
        if start < 0:
            start = 0.0
        if end <= start:
            end = start + 0.5
        if cleaned and start < cleaned[-1]["end_sec"]:
            logger.warning("[asr] 时间戳回退（{:.2f}s < {:.2f}s），已顺延", start, cleaned[-1]["end_sec"])
            start = cleaned[-1]["end_sec"]
            if end <= start:
                end = start + 0.5
        cleaned.append({
            "text": text,
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
        })

    for prev, cur in zip(cleaned, cleaned[1:]):
        gap = cur["start_sec"] - prev["end_sec"]
        if gap > _GAP_WARN_SEC:
            logger.warning("[asr] 字幕空洞 {:.1f}s（{:.1f}s → {:.1f}s）", gap, prev["end_sec"], cur["start_sec"])

    if not cleaned:
        logger.warning("[asr] 未解析出任何有效语句")
    return cleaned
