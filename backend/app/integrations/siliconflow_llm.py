"""硅基流动大模型客户端。重点抽取 / 分层总结 / 两级思维导图（A2）。

对应 docs/09-mvp-implementation-plan.md A2、docs/05-risk-handling.md 防幻觉与内容质量。

要点：
- 仅基于传入转写文本生成，系统提示明确禁止引入外部知识（防幻觉）；
- 输入必须是**带时间戳**的转写行（``[起始秒] 文本``），否则模型只能编造时间点；
- 长转写（> ``SILICONFLOW_MAX_INPUT_CHARS``）按时间窗口分段，map→reduce 合并；
- JSON 解析容错：去 ```json 围栏、截取首尾花括号，解析失败时把错误回灌重试一次；
- 结果规范化：``category`` 白名单、时间点取数值、思维导图强制两级、空结果如实返回空。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from loguru import logger

from app.config import settings
from app.db.models.keypoint import KEYPOINT_CATEGORIES

_CHAT_PATH = "/chat/completions"
_TEMPERATURE = 0.3

# 同名/邻近重点合并阈值（秒），避免分段模式在重叠区重复产出
_DEDUPE_WINDOW_SEC = 30.0
# 同名重点相隔超过该阈值时视为不同知识点（同一讲次里可能重复出现同名要点）
_SAME_TITLE_WINDOW_SEC = 180.0

_SYSTEM_PROMPT = (
    "你是课程内容分析助手。仅根据用户提供的课程转写文本生成结果，"
    "不得引入转写中未出现的外部知识。所有时间点必须来自转写提供的时间戳。"
    "始终只输出 JSON，不要输出解释文字或 Markdown 代码块。"
)

_CATEGORY_VALUES = " / ".join(KEYPOINT_CATEGORIES)


# --------------------------------------------------------------------------- #
# HTTP 调用
# --------------------------------------------------------------------------- #
def _chat(user_prompt: str) -> str:
    """单次 Chat Completions 调用，返回模型输出的原始文本。

    429/5xx/超时由调用方的 ``with_retry`` 处理（见 pipeline/steps/llm.py）。
    """
    if not settings.siliconflow_api_key:
        raise RuntimeError("硅基流动 API Key 未配置（SILICONFLOW_API_KEY）")

    url = settings.siliconflow_base_url.rstrip("/") + _CHAT_PATH
    headers = {"Authorization": f"Bearer {settings.siliconflow_api_key}"}
    payload: dict[str, Any] = {
        "model": settings.siliconflow_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": _TEMPERATURE,
        "response_format": {"type": "json_object"},
    }

    started = time.monotonic()
    with httpx.Client(timeout=settings.siliconflow_timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code in (400, 422):
            logger.warning("[llm] 接口不接受 response_format=json_object（HTTP {}），退回纯文本模式",
                           resp.status_code)
            payload.pop("response_format", None)
            resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = _extract_content(data)
    usage = data.get("usage") or {}
    logger.info(
        "[llm] model={} 输入 {} 字 / prompt_tokens={} completion_tokens={} 耗时 {:.1f}s",
        settings.siliconflow_model,
        len(user_prompt),
        usage.get("prompt_tokens", "-"),
        usage.get("completion_tokens", "-"),
        time.monotonic() - started,
    )
    return content


def _extract_content(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"LLM 返回缺少 choices：{str(data)[:200]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # 少数实现返回分段内容
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise RuntimeError(f"LLM 返回内容为空：{str(data)[:200]}")
    return content


def _chat_json(user_prompt: str) -> dict:
    """调用模型并解析 JSON；解析失败时把错误回灌重试一次（A2-4）。"""
    content = _chat(user_prompt)
    try:
        return _loads(content)
    except ValueError as exc:
        logger.warning("[llm] JSON 解析失败，回灌错误重试一次：{}", exc)
        repair_prompt = (
            f"{user_prompt}\n\n"
            f"上一次输出无法解析为 JSON（错误：{exc}）。请只输出合法 JSON 对象，不要任何解释文字。"
        )
        return _loads(_chat(repair_prompt))


def _loads(content: str) -> dict:
    """去 ```json 围栏 → 截取首尾花括号 → json.loads。"""
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"输出中找不到 JSON 对象：{text[:120]}")

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 语法错误：{exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON 顶层不是对象")
    return parsed


# --------------------------------------------------------------------------- #
# 分段
# --------------------------------------------------------------------------- #
def _split_chunks(transcript_text: str) -> list[str]:
    """按行（每行一句带时间戳的转写）切分成不超过上限的若干块。"""
    limit = max(1000, settings.siliconflow_max_input_chars)
    if len(transcript_text) <= limit:
        return [transcript_text]

    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for line in transcript_text.splitlines():
        if buffer and size + len(line) + 1 > limit:
            chunks.append("\n".join(buffer))
            buffer, size = [], 0
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        chunks.append("\n".join(buffer))

    logger.info("[llm] 转写 {} 字超出上限 {}，切分为 {} 块",
                len(transcript_text), limit, len(chunks))
    return chunks


# --------------------------------------------------------------------------- #
# 重点时间点（FR-04）
# --------------------------------------------------------------------------- #
def extract_keypoints(transcript_text: str, course_title: str) -> list[dict]:
    """转写 → 重点时间点 ``[{title, category, summary, timestamp_sec}]``。"""
    chunks = _split_chunks(transcript_text)
    collected: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        payload = _chat_json(_keypoint_prompt(chunk, course_title, index, len(chunks)))
        collected.extend(_normalize_keypoints(payload.get("keypoints")))
    return _dedupe_keypoints(collected)


def _keypoint_prompt(text: str, course_title: str, index: int, total: int) -> str:
    part = f"（第 {index}/{total} 段）" if total > 1 else ""
    return (
        f"课程《{course_title}》的课堂转写{part}如下，每行格式为 [起始秒] 文本。\n"
        f"请抽取重点时间点（核心概念、公式推导、例题讲解、考点提示）。\n"
        f"只输出 JSON 对象，结构为：\n"
        f'{{"keypoints": [{{"title": "知识点名称（≤20字）", "category": "concept", '
        f'"summary": "一句话摘要（≤50字）", "timestamp_sec": 123.4}}]}}\n'
        f"要求：\n"
        f"1. category 只能是 {_CATEGORY_VALUES}（概念/公式/例题/考点）之一；\n"
        f"2. timestamp_sec 必须取自转写行首方括号中的秒数，不得编造；\n"
        f"3. 没有值得标注的内容时返回空数组。\n"
        f"转写：\n{text}"
    )


def _normalize_keypoints(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _clean_str(item.get("title") or item.get("name"))
        timestamp = _to_float(item.get("timestamp_sec", item.get("timestamp", item.get("time"))))
        if not title or timestamp is None or timestamp < 0:
            continue
        out.append({
            "title": title[:255],
            "category": _normalize_category(item.get("category")),
            "summary": _clean_str(item.get("summary") or item.get("desc"))[:500],
            "timestamp_sec": round(timestamp, 2),
        })
    return out


def _normalize_category(value: Any) -> str:
    """category 白名单校验；非法值归为 concept（docs/03:121）。"""
    text = str(value or "").strip().lower()
    aliases = {
        "概念": "concept", "定义": "concept", "concept": "concept",
        "公式": "formula", "定理": "formula", "formula": "formula",
        "例题": "example", "例子": "example", "example": "example",
        "考点": "exam_point", "重点": "exam_point", "exam_point": "exam_point", "exam": "exam_point",
    }
    mapped = aliases.get(text)
    if mapped:
        return mapped
    return text if text in KEYPOINT_CATEGORIES else "concept"


def _dedupe_keypoints(items: list[dict]) -> list[dict]:
    """按标题归一化 + 时间邻近去重，并按时间排序（AC-03-03）。"""
    ordered = sorted(items, key=lambda k: k["timestamp_sec"])
    out: list[dict] = []
    seen: list[tuple[str, float]] = []
    for item in ordered:
        key = _normalize_title(item["title"])
        timestamp = item["timestamp_sec"]
        if any(existing == key and abs(timestamp - kept_ts) <= _SAME_TITLE_WINDOW_SEC
               for existing, kept_ts in seen):
            continue
        if any(abs(timestamp - kept["timestamp_sec"]) <= _DEDUPE_WINDOW_SEC
               and _similar_title(item["title"], kept["title"]) for kept in out):
            continue
        seen.append((key, timestamp))
        out.append(item)
    return out


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", title or "").lower()


def _similar_title(left: str, right: str) -> bool:
    a = re.sub(r"[\s，。、：:；;（）()【】\[\]]+", "", left)
    b = re.sub(r"[\s，。、：:；;（）()【】\[\]]+", "", right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


# --------------------------------------------------------------------------- #
# 分层总结（FR-05）
# --------------------------------------------------------------------------- #
def generate_summary(transcript_text: str, course_title: str) -> dict:
    """转写 → 分层总结 ``{overview, chapter_points, key_details, review_hints}``。"""
    chunks = _split_chunks(transcript_text)
    if len(chunks) == 1:
        payload = _chat_json(_summary_prompt(chunks[0], course_title))
        return _normalize_summary(payload)

    # 分段模式：先逐段提炼，再用一次 reduce 调用生成完整分层总结
    notes: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        payload = _chat_json(_chunk_notes_prompt(chunk, course_title, index, len(chunks)))
        notes.extend(_clean_str(n) for n in payload.get("notes", []) if _clean_str(n))
    reduced = _chat_json(_summary_reduce_prompt(notes, course_title))
    return _normalize_summary(reduced)


def _summary_prompt(text: str, course_title: str) -> str:
    return (
        f"课程《{course_title}》的课堂转写如下，每行格式为 [起始秒] 文本。\n"
        f"请生成分层课程总结，只输出 JSON 对象：\n"
        f'{{"overview": "课程概览（100-200字，说明本节讲了什么）",\n'
        f' "chapter_points": [{{"chapter": "章节/模块名", "points": ["要点1", "要点2"]}}],\n'
        f' "key_details": [{{"title": "知识点", "detail": "详解"}}],\n'
        f' "review_hints": ["复习提示1", "复习提示2"]}}\n'
        f"要求：严格按课程讲解顺序组织章节；内容只能来自转写；没有内容的字段返回空数组。\n"
        f"转写：\n{text}"
    )


def _chunk_notes_prompt(text: str, course_title: str, index: int, total: int) -> str:
    return (
        f"课程《{course_title}》的课堂转写片段（第 {index}/{total} 段）如下，每行格式为 [起始秒] 文本。\n"
        f'请提炼该片段的要点，只输出 JSON 对象：{{"notes": ["要点1", "要点2"]}}\n'
        f"要点需包含讲到的概念、公式、例题与结论，按讲解顺序排列。\n"
        f"转写：\n{text}"
    )


def _summary_reduce_prompt(notes: list[str], course_title: str) -> str:
    joined = "\n".join(f"- {note}" for note in notes)
    return (
        f"以下是课程《{course_title}》按时间顺序分段的要点笔记：\n{joined}\n\n"
        f"请据此生成分层课程总结，只输出 JSON 对象：\n"
        f'{{"overview": "课程概览（100-200字）",\n'
        f' "chapter_points": [{{"chapter": "章节/模块名", "points": ["要点1"]}}],\n'
        f' "key_details": [{{"title": "知识点", "detail": "详解"}}],\n'
        f' "review_hints": ["复习提示"]}}\n'
        f"要求：只使用上面笔记中出现的信息，不得引入外部知识；无内容的字段返回空数组。"
    )


def _normalize_summary(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"overview": None, "chapter_points": [], "key_details": [], "review_hints": []}

    chapter_points: list[dict] = []
    for item in _as_list(raw.get("chapter_points")):
        if isinstance(item, dict):
            chapter = _clean_str(item.get("chapter") or item.get("title") or item.get("module"))
            points = [_clean_str(p) for p in _as_list(item.get("points")) if _clean_str(p)]
            if chapter or points:
                chapter_points.append({"chapter": chapter or "未命名章节", "points": points})
        elif _clean_str(item):
            chapter_points.append({"chapter": _clean_str(item), "points": []})

    key_details: list[dict] = []
    for item in _as_list(raw.get("key_details")):
        if isinstance(item, dict):
            title = _clean_str(item.get("title") or item.get("name"))
            detail = _clean_str(item.get("detail") or item.get("summary") or item.get("content"))
            if title or detail:
                key_details.append({"title": title or "知识点", "detail": detail})
        elif _clean_str(item):
            key_details.append({"title": _clean_str(item), "detail": ""})

    review_hints = [_clean_str(h) for h in _as_list(raw.get("review_hints")) if _clean_str(h)]

    return {
        "overview": _clean_str(raw.get("overview") or raw.get("summary")) or None,
        "chapter_points": chapter_points,
        "key_details": key_details,
        "review_hints": review_hints,
    }


# --------------------------------------------------------------------------- #
# 两级思维导图（FR-06）
# --------------------------------------------------------------------------- #
def generate_mindmap(transcript_text: str, course_title: str) -> dict:
    """转写 → 两级思维导图 ``{root_topic, nodes}``。"""
    chunks = _split_chunks(transcript_text)
    if len(chunks) == 1:
        payload = _chat_json(_mindmap_prompt(chunks[0], course_title))
        return _normalize_mindmap(payload, course_title)

    # 分段模式：先抽该片段的重点（带时间戳），再用 reduce 调用组织成两级导图
    collected: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        payload = _chat_json(_keypoint_prompt(chunk, course_title, index, len(chunks)))
        collected.extend(_normalize_keypoints(payload.get("keypoints")))
    merged = _dedupe_keypoints(collected)[:60]
    if not merged:
        return {"root_topic": course_title, "nodes": []}
    reduced = _chat_json(_mindmap_reduce_prompt(merged, course_title))
    return _normalize_mindmap(reduced, course_title)


def _mindmap_prompt(text: str, course_title: str) -> str:
    return (
        f"课程《{course_title}》的课堂转写如下，每行格式为 [起始秒] 文本。\n"
        f"请生成两级思维导图（课程主题 → 知识模块 → 知识点），只输出 JSON 对象：\n"
        f'{{"root_topic": "{course_title}",\n'
        f' "nodes": [{{"module": "知识模块名", "knowledge_points": '
        f'[{{"name": "知识点", "timestamp_sec": 123.4}}]}}]}}\n'
        f"要求：\n"
        f"1. 严格两级，不要出现第三层；\n"
        f"2. timestamp_sec 必须取自转写行首方括号中的秒数，没有对应时间的知识点填 null；\n"
        f"3. 模块数量控制在 3-8 个。\n"
        f"转写：\n{text}"
    )


def _mindmap_reduce_prompt(keypoints: list[dict], course_title: str) -> str:
    lines = "\n".join(f"- [{k['timestamp_sec']}] {k['title']}" for k in keypoints)
    return (
        f"以下是课程《{course_title}》的重点时间点（格式 [秒] 名称）：\n{lines}\n\n"
        f"请把它们组织成两级思维导图（课程主题 → 知识模块 → 知识点），只输出 JSON 对象：\n"
        f'{{"root_topic": "{course_title}",\n'
        f' "nodes": [{{"module": "知识模块名", "knowledge_points": '
        f'[{{"name": "知识点", "timestamp_sec": 123.4}}]}}]}}\n'
        f"要求：严格两级；knowledge_points 只能来自上面的列表；timestamp_sec 必须与列表一致，不得编造。"
    )


def _normalize_mindmap(raw: Any, course_title: str) -> dict:
    if not isinstance(raw, dict):
        return {"root_topic": course_title, "nodes": []}

    root_topic = _clean_str(raw.get("root_topic") or raw.get("root") or raw.get("topic")) or course_title
    nodes: list[dict] = []
    for node in _as_list(raw.get("nodes") or raw.get("modules")):
        if not isinstance(node, dict):
            continue
        module = _clean_str(node.get("module") or node.get("name") or node.get("chapter"))
        if not module:
            continue
        points: list[dict] = []
        for point in _as_list(node.get("knowledge_points") or node.get("points") or node.get("children")):
            if isinstance(point, dict):
                name = _clean_str(point.get("name") or point.get("title") or point.get("knowledge_point"))
                timestamp = _to_float(point.get("timestamp_sec", point.get("timestamp", point.get("time"))))
            else:
                name, timestamp = _clean_str(point), None
            if not name:
                continue
            # 强制两级：忽略知识点下面可能出现的第三层
            points.append({
                "name": name[:255],
                "timestamp_sec": round(timestamp, 2) if timestamp is not None and timestamp >= 0 else None,
            })
        if points:
            nodes.append({"module": module[:255], "knowledge_points": points})

    return {"root_topic": root_topic[:255], "nodes": nodes[:20]}


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().rstrip("s秒")
        try:
            return float(text)
        except ValueError:
            # 支持 "01:23" / "01:23.4" 形式
            parts = text.split(":")
            if len(parts) in (2, 3):
                try:
                    numbers = [float(p) for p in parts]
                except ValueError:
                    return None
                seconds = 0.0
                for number in numbers:
                    seconds = seconds * 60 + number
                return seconds
    return None
