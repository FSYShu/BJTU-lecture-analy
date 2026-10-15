"""A3：平台字幕（VTT）与知识点（zsd）接入。

对应 docs/10-platform-feasibility-analysis.md §11.1 与 docs/09-mvp-implementation-plan.md A3：

- ``parse_vtt``：平台 API 6 的 WebVTT → 句级转写（``ai_generated=False``、``source_model='platform-vtt'``）；
- ``vtt_coverage``：字幕覆盖时长占比，过低时回退 ASR 生成；
- ``map_zsd``：平台 API 3 的知识点 → 重点时间点（``timestamp_sec = zsd_wait_time``、
  ``source_model='platform-zsd'``、``ai_generated=False``，``category`` 按内容归类）；
- ``align_keypoints``：平台知识点与 LLM 重点按 ``TIMESTAMP_TOLERANCE_SEC`` 去重后并存（平台优先）。
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger

from app.config import settings
from app.db.models.keypoint import KEYPOINT_CATEGORIES

PLATFORM_VTT_SOURCE = "platform-vtt"
PLATFORM_ZSD_SOURCE = "platform-zsd"

_CUE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
    r"\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d+);")

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("formula", ("公式", "定理", "推导", "方程", "定理证明", "表达式")),
    ("example", ("例题", "例", "练习", "习题", "案例", "题目")),
    ("exam_point", ("考点", "考试", "重点", "必考", "作业", "易错")),
)


# --------------------------------------------------------------------------- #
# WebVTT
# --------------------------------------------------------------------------- #
def parse_vtt(vtt_text: str) -> list[dict]:
    """WebVTT → ``[{text, start_sec, end_sec, ai_generated=False, source_model='platform-vtt'}]``。"""
    cues: list[dict] = []
    current: dict | None = None

    for raw_line in (vtt_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT") or line.upper().startswith(("NOTE", "STYLE", "REGION")):
            current = None
            continue

        match = _CUE_RE.search(line)
        if match:
            current = {
                "start": _to_seconds(match.group("start")),
                "end": _to_seconds(match.group("end")),
                "texts": [],
            }
            cues.append(current)
            continue

        if current is None or line.isdigit():
            continue
        cleaned = _clean_cue_text(line)
        if cleaned:
            current["texts"].append(cleaned)

    sentences: list[dict] = []
    for cue in cues:
        text = " ".join(cue["texts"]).strip()
        if not text:
            continue
        start = max(0.0, cue["start"])
        end = cue["end"] if cue["end"] > start else start + 0.5
        sentences.append({
            "text": text,
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
            "ai_generated": False,
            "source_model": PLATFORM_VTT_SOURCE,
        })

    sentences.sort(key=lambda item: item["start_sec"])
    return _make_monotonic(sentences)


def vtt_coverage(sentences: list[dict], duration_sec: float | None) -> float:
    """字幕覆盖时长占课程时长的比例（0–1）；时长未知时按 1.0 处理。"""
    if not sentences:
        return 0.0
    try:
        duration = float(duration_sec or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return 1.0

    covered = 0.0
    cursor = 0.0
    for item in sorted(sentences, key=lambda s: s["start_sec"]):
        start = max(cursor, float(item["start_sec"]))
        end = min(duration, float(item["end_sec"]))
        if end > start:
            covered += end - start
            cursor = end
    return max(0.0, min(1.0, covered / duration))


def _make_monotonic(sentences: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in sentences:
        if out and item["start_sec"] < out[-1]["end_sec"]:
            item = {**item, "start_sec": out[-1]["end_sec"]}
            if item["end_sec"] <= item["start_sec"]:
                item["end_sec"] = round(item["start_sec"] + 0.5, 2)
        out.append(item)
    return out


def _clean_cue_text(line: str) -> str:
    text = _TAG_RE.sub("", line)
    text = _ENTITY_RE.sub(" ", text)
    return text.strip()


def _to_seconds(value: str) -> float:
    """``HH:MM:SS.mmm`` / ``MM:SS.mmm`` → 秒。"""
    normalized = value.strip().replace(",", ".")
    parts = normalized.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


# --------------------------------------------------------------------------- #
# 平台知识点（zsd）
# --------------------------------------------------------------------------- #
def map_zsd(zsd_items: list[dict], duration_sec: float | None = None) -> list[dict]:
    """平台 zsd → 重点时间点（``ai_generated=False``、``source_model='platform-zsd'``）。"""
    out: list[dict] = []
    duration = float(duration_sec or 0.0)

    for item in zsd_items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("zsd_name") or item.get("name") or "").strip()
        timestamp = _to_float(item.get("zsd_wait_time"))
        if timestamp is None:
            sfm = item.get("sfm")
            timestamp = _to_seconds(sfm) if isinstance(sfm, str) and sfm else None
        if not title or timestamp is None or timestamp < 0:
            continue
        if duration and timestamp > duration:
            logger.warning("[platform] 知识点越界，已丢弃：{} @ {}s（时长 {}s）", title, timestamp, duration)
            continue
        out.append({
            "title": title[:255],
            "category": _infer_category(title),
            "summary": None,
            "timestamp_sec": round(float(timestamp), 2),
            "ai_generated": False,
            "source_model": PLATFORM_ZSD_SOURCE,
        })

    out.sort(key=lambda item: item["timestamp_sec"])
    logger.info("[platform] 平台知识点 {} 条（有效 {} 条）", len(zsd_items or []), len(out))
    return out


def _infer_category(title: str) -> str:
    """按内容把平台知识点归到 keypoints.category 枚举（docs/10:977「按内容归类」）。"""
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in title for keyword in keywords):
            return category
    return "concept" if "concept" in KEYPOINT_CATEGORIES else "concept"


# --------------------------------------------------------------------------- #
# 对齐与合并
# --------------------------------------------------------------------------- #
def align_keypoints(
    ai_items: list[dict],
    platform_items: list[dict],
    tolerance_sec: float | None = None,
) -> list[dict]:
    """平台知识点与 LLM 重点按时间点去重合并（平台优先），并按时间排序。"""
    if not platform_items:
        merged = list(ai_items or [])
    else:
        tolerance = settings.timestamp_tolerance_sec if tolerance_sec is None else tolerance_sec
        kept: list[dict] = []
        aligned = 0
        for item in ai_items or []:
            timestamp = float(item.get("timestamp_sec", 0.0) or 0.0)
            if any(abs(timestamp - float(p["timestamp_sec"])) <= tolerance for p in platform_items):
                aligned += 1
                continue
            kept.append(item)
        if aligned:
            logger.info("[platform] {} 条 LLM 重点与平台知识点时间点对齐（±{}s），以平台为准",
                        aligned, tolerance)
        merged = list(platform_items) + kept

    merged.sort(key=lambda item: float(item.get("timestamp_sec", 0.0) or 0.0))
    for index, item in enumerate(merged):
        item["seq_index"] = index
        item.setdefault("ai_generated", True)
    return merged


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
