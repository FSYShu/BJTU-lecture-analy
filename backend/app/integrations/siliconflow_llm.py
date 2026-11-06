"""硅基流动大模型客户端。重点抽取 / 分层总结 / 两级思维导图（A2）。

对应 docs/09-mvp-implementation-plan.md A2、docs/05-risk-handling.md 防幻觉与内容质量。

要点：
- 仅基于传入转写文本生成，系统提示明确禁止引入外部知识（防幻觉）；
- 输入必须是**带时间戳**的转写行（``[起始秒] 文本``），否则模型只能编造时间点；
- 长转写（> ``SILICONFLOW_MAX_INPUT_CHARS``）按时间窗口分段，map→reduce 合并；
  各分段互不依赖，map 阶段**并行**调用（``SILICONFLOW_LLM_WORKERS``），
  结果按块序号有序合并，避免并发打乱章节/要点顺序；
- HTTP 客户端进程内复用（``app/integrations/http_pool.py``），
  在飞请求数由 ``SILICONFLOW_LLM_MAX_CONCURRENCY`` 统一封顶，防止并发打满限流；
- JSON 解析容错：去 ```json 围栏、截取首尾花括号，解析失败时把错误回灌重试一次；
- 结果规范化：``category`` 白名单、时间点取数值、思维导图强制两级、空结果如实返回空。
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

import httpx
from loguru import logger

from app.config import settings
from app.core.concurrency import map_ordered
from app.db.models.keypoint import KEYPOINT_CATEGORIES
from app.integrations import http_pool

_CHAT_PATH = "/chat/completions"
_TEMPERATURE = 0.3

# 全局并发闸门：三子任务并行 × 分段并行会把在飞请求数乘到 9 以上，
# 用信号量统一压到 SILICONFLOW_LLM_MAX_CONCURRENCY，避免瞬间打满对端限流（429 会重试，反而更慢）。
_REQUEST_SLOTS = threading.BoundedSemaphore(max(1, settings.siliconflow_llm_max_concurrency))

# 同名/邻近重点合并阈值（秒），避免分段模式在重叠区重复产出
_DEDUPE_WINDOW_SEC = 30.0
# 同名重点相隔超过该阈值时视为不同知识点（同一讲次里可能重复出现同名要点）
_SAME_TITLE_WINDOW_SEC = 180.0
# 长转写分段时相邻块的时间重叠窗口（秒），见 docs/09 A2-2
_CHUNK_OVERLAP_SEC = 60.0

_SYSTEM_PROMPT = (
    "你是「交大课录智析」的课程内容分析引擎，服务对象是考前需要快速复习的大学生。\n"
    "用户会给出某节课堂回放的转写片段，每行格式为「[起始秒] 该句文本」，"
    "方括号内的数字是该句在整节视频中的起始时间（秒，绝对时间轴）。\n"
    "硬性规则：\n"
    "1. 只能使用转写中出现的信息，禁止引入教材、常识或其他课程的外部知识；"
    "转写没提到的内容一律不写。\n"
    "2. 任何时间点都必须直接取自转写行首方括号中的数字，禁止推测、换算或编造。\n"
    "3. 只输出一个合法 JSON 对象：不要 Markdown 代码块、不要注释、不要解释或前后缀文字。\n"
    "4. 用中文表达，术语沿用转写中的说法；不要用「老师讲解了…」这类空话凑字数。\n"
    "5. 片段中没有对应内容时，按用户要求返回空数组或空字符串，不得用占位内容填充。\n"
    "6. 面向复习：结论优先、可直接扫读；同一知识点只出现一次，重复时保留时间最早的一次。"
)

_CATEGORY_VALUES = " / ".join(KEYPOINT_CATEGORIES)


# --------------------------------------------------------------------------- #
# HTTP 调用
# --------------------------------------------------------------------------- #
def _chat(user_prompt: str) -> str:
    """单次 Chat Completions 调用，返回模型输出的原始文本。

    客户端复用见 ``app/integrations/http_pool.py``（省掉每次调用的 TCP/TLS 握手）；
    同时在飞请求数受 ``SILICONFLOW_LLM_MAX_CONCURRENCY`` 约束。
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
    timeout = _timeout()
    client = http_pool.get_client()

    started = time.monotonic()
    with _REQUEST_SLOTS:
        resp = client.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code in (400, 422):
            logger.warning("[llm] 接口不接受 response_format=json_object（HTTP {}），退回纯文本模式",
                           resp.status_code)
            payload.pop("response_format", None)
            resp = client.post(url, headers=headers, json=payload, timeout=timeout)
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


def _timeout() -> httpx.Timeout:
    """单次请求超时：读到完整响应用配置值，连接/写/等待连接池分别设更紧的上限。"""
    return httpx.Timeout(settings.siliconflow_timeout, connect=10.0, write=30.0, pool=10.0)


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
    """按行（每行一句带时间戳的转写）切分成不超过上限的若干块。

    相邻块保留 ``_CHUNK_OVERLAP_SEC`` 秒的**重叠区**（docs/09 A2-2：重叠 30–60 秒，
    避免跨块知识被切断）；重叠导致重复产出的重点由 ``_dedupe_keypoints`` 合并。
    """
    limit = max(1000, settings.siliconflow_max_input_chars)
    if len(transcript_text) <= limit:
        return [transcript_text]

    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for line in transcript_text.splitlines():
        if buffer and size + len(line) + 1 > limit:
            chunks.append("\n".join(buffer))
            buffer = _overlap_tail(buffer, limit)
            size = sum(len(item) + 1 for item in buffer)
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        chunks.append("\n".join(buffer))

    logger.info("[llm] 转写 {} 字超出上限 {}，切分为 {} 块（块间重叠 ≤{:.0f}s）",
                len(transcript_text), limit, len(chunks), _CHUNK_OVERLAP_SEC)
    return chunks


def _overlap_tail(lines: list[str], limit: int) -> list[str]:
    """取上一块末尾时间跨度 ≤ 重叠窗口的行，作为下一块的开头。"""
    if not lines:
        return []

    last_ts = _line_timestamp(lines[-1])
    if last_ts is None:
        tail = lines[-2:] if len(lines) > 2 else list(lines)
    else:
        tail = []
        for line in reversed(lines):
            timestamp = _line_timestamp(line)
            if timestamp is None or last_ts - timestamp > _CHUNK_OVERLAP_SEC:
                break
            tail.append(line)
        tail.reverse()

    # 重叠区不超过上限的 1/3，避免切分停滞
    while tail and sum(len(item) + 1 for item in tail) > limit // 3:
        tail.pop(0)
    return tail


def _line_timestamp(line: str) -> float | None:
    """解析转写行行首的 ``[起始秒]``。"""
    match = re.match(r"\s*\[(\d+(?:\.\d+)?)\]", line)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# 重点时间点（FR-04）
# --------------------------------------------------------------------------- #
def extract_keypoints(transcript_text: str, course_title: str) -> list[dict]:
    """转写 → 重点时间点 ``[{title, category, summary, timestamp_sec}]``。

    长转写分段后**并行**抽取（分段之间无依赖），再按块序号顺序合并去重，
    结果与串行版本完全一致，只是耗时从「分段数 × 单段耗时」降到约「单段耗时」。
    """
    chunks = _split_chunks(transcript_text)
    total = len(chunks)

    def _extract(index: int, chunk: str) -> list[dict]:
        payload = _chat_json(_keypoint_prompt(chunk, course_title, index + 1, total))
        items = _normalize_keypoints(payload.get("keypoints"))
        if total > 1:
            logger.info("[llm] 重点分段 {}/{} 完成：{} 条", index + 1, total, len(items))
        return items

    collected: list[dict] = []
    for items in map_ordered(
        _extract, chunks, settings.siliconflow_llm_workers, thread_name_prefix="llm-keypoints",
    ):
        collected.extend(items)
    return _dedupe_keypoints(collected)


def _keypoint_prompt(text: str, course_title: str, index: int, total: int) -> str:
    if total > 1:
        header = (
            f"课程《{course_title}》的课堂转写（分段）。本次只给你整节课的第 {index}/{total} 段，"
            f"行首秒数已经是整节课的绝对时间，直接使用即可，不要按段内相对时间换算。"
        )
    else:
        header = f"课程《{course_title}》的课堂转写。每行格式为 [起始秒] 文本。"
    return (
        f"{header}\n"
        "请抽取学生复习时值得跳转回看的重点时间点。\n"
        "抽取标准（命中任意一类即可）：\n"
        "1. 概念/定理的定义与核心结论；\n"
        "2. 公式的推导关键步、适用条件与使用前提；\n"
        "3. 例题的题干、解题思路与答案；\n"
        "4. 明确的考点提示、易错点、「考试会考」这类提醒。\n"
        "不要抽取：点名考勤、课堂管理、闲聊、重复的口头语、与课程无关的内容。\n"
        "只输出 JSON，字段名固定：\n"
        '{"keypoints": [{"title": "知识点名称", "category": "concept", '
        '"summary": "一句话说明", "timestamp_sec": 123.4}]}\n'
        "字段规则：\n"
        "- title：名词性短语，≤20 个汉字，例如「傅里叶级数的收敛条件」，不要写成句子；\n"
        f"- category：只能是 {_CATEGORY_VALUES} 之一（依次对应 概念 / 公式 / 例题 / 考点）；\n"
        "- summary：≤50 个汉字，说清「这里讲了什么、为什么值得回看」；\n"
        "- timestamp_sec：该知识点首次讲到那一行的行首秒数，直接复制数字（可带小数），"
        "不要取整、不要改写；\n"
        "- 按 timestamp_sec 升序，最多 12 条；本段没有值得标注的内容时返回 "
        '{"keypoints": []}\n'
        "示例（只示意格式与粒度，不要照抄内容）：\n"
        "输入：\n"
        "[0.0] 今天讲傅里叶级数的收敛性。\n"
        "[45.2] 狄利克雷条件有三条，第一条是一个周期内连续或只有有限个第一类间断点。\n"
        "输出：\n"
        '{"keypoints": [{"title": "狄利克雷条件", "category": "concept", '
        '"summary": "傅里叶级数收敛的三条前提，允许有限个第一类间断点", '
        '"timestamp_sec": 45.2}]}\n'
        f"待分析转写：\n{text}"
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
    """转写 → 分层总结 ``{overview, chapter_points, key_details, review_hints}``。

    长转写：分段**并行**提炼要点（map）→ 单次调用汇总成完整总结（reduce）。
    要点按块序号顺序拼接，reduce 看到的仍是讲解顺序，与串行版本一致。
    """
    chunks = _split_chunks(transcript_text)
    if len(chunks) == 1:
        payload = _chat_json(_summary_prompt(chunks[0], course_title))
        return _normalize_summary(payload)

    total = len(chunks)

    def _map(index: int, chunk: str) -> list[str]:
        payload = _chat_json(_chunk_notes_prompt(chunk, course_title, index + 1, total))
        notes = [_clean_str(n) for n in payload.get("notes", []) if _clean_str(n)]
        logger.info("[llm] 总结分段 {}/{} 完成：{} 条要点", index + 1, total, len(notes))
        return notes

    notes: list[str] = []
    for part in map_ordered(
        _map, chunks, settings.siliconflow_llm_workers, thread_name_prefix="llm-summary",
    ):
        notes.extend(part)

    if not notes:
        # 所有分段都没提炼出内容：直接返回空结构，不调用 reduce，避免模型无依据编造总结
        logger.warning("[llm] 所有分段均未提炼出要点，返回空总结")
        return _normalize_summary(None)

    reduced = _chat_json(_summary_reduce_prompt(notes, course_title))
    return _normalize_summary(reduced)


def _summary_prompt(text: str, course_title: str) -> str:
    return (
        f"课程《{course_title}》的课堂转写（每行格式为 [起始秒] 文本）。\n"
        "请生成分层课程总结，让学生先看清这节课的骨架，再决定回看哪里。\n"
        "只输出 JSON，字段名固定：\n"
        '{"overview": "课程概览",\n'
        ' "chapter_points": [{"chapter": "章节/模块名", "points": ["要点"]}],\n'
        ' "key_details": [{"title": "知识点", "detail": "详解"}],\n'
        ' "review_hints": ["复习提示"]}\n'
        "字段规则：\n"
        "- overview：100–200 字，写清主线（先讲什么、再讲什么、最终落到什么结论），"
        "不要罗列知识点；\n"
        "- chapter_points：3–6 个模块，必须与讲解顺序一致；chapter 是模块名（≤15 字），"
        "points 是 2–5 条要点（每条 ≤40 字），写结论/公式/方法，不写「老师讲解了…」；\n"
        "- key_details：3–8 个必须掌握的知识点，detail 写 40–120 字，"
        "包含适用条件、易错点或推导关键步；\n"
        "- review_hints：2–5 条可执行的复习动作，可引用转写中的时间戳"
        "（例如「回看 12:30 的推导，自己重推一遍」）；\n"
        "- 内容只能来自转写；无内容的字段返回空数组，overview 无法概括时返回空字符串。\n"
        f"转写：\n{text}"
    )


def _chunk_notes_prompt(text: str, course_title: str, index: int, total: int) -> str:
    return (
        f"课程《{course_title}》的整节课转写被切成 {total} 段，这是第 {index}/{total} 段"
        f"（行首秒数为整节课的绝对时间）。\n"
        "请提炼本段要点，供后续汇总成整节课的分层总结使用。只输出 JSON："
        '{"notes": ["要点"]}\n'
        "规则：\n"
        "- 按讲解顺序 3–8 条，每条 ≤60 字，写成「主题：结论/方法/公式」的独立短句，"
        "脱离上下文也能读懂；\n"
        "- 关键处带上行首秒数（例如「12:30 处推导了…」），便于后续引用时间点；\n"
        "- 只写本段真实出现的内容；本段没有实质内容时返回 "
        '{"notes": []}\n'
        f"转写：\n{text}"
    )


def _summary_reduce_prompt(notes: list[str], course_title: str) -> str:
    joined = "\n".join(f"- {note}" for note in notes)
    return (
        f"以下是课程《{course_title}》按时间顺序排列的分段要点笔记：\n{joined}\n\n"
        "请据此生成整节课的分层课程总结，只输出 JSON，字段名固定：\n"
        '{"overview": "课程概览",\n'
        ' "chapter_points": [{"chapter": "章节/模块名", "points": ["要点"]}],\n'
        ' "key_details": [{"title": "知识点", "detail": "详解"}],\n'
        ' "review_hints": ["复习提示"]}\n'
        "要求：\n"
        "- overview：100–200 字，说明主线与最终结论；\n"
        "- 把同一主题的笔记合并进同一个 chapter（3–6 个模块），不要按片段编号罗列；\n"
        "- key_details 3–8 个（detail 40–120 字），review_hints 2–5 条可执行建议；\n"
        "- 只能使用上面笔记中的信息，不得引入外部知识；无内容的字段返回空数组。"
    )


_SUMMARY_FIELD_NAMES = frozenset({"overview", "chapter_points", "key_details", "review_hints", "summary", "notes"})


def _normalize_summary(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"overview": None, "chapter_points": [], "key_details": [], "review_hints": []}

    chapter_points: list[dict] = []
    for item in _as_list(raw.get("chapter_points")):
        if isinstance(item, dict):
            chapter = _clean_str(item.get("chapter") or item.get("title") or item.get("module"))
            if chapter in _SUMMARY_FIELD_NAMES:
                continue
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
    """转写 → 两级思维导图 ``{root_topic, nodes}``。

    长转写：分段**并行**抽取带时间戳的重点（map）→ 去重取前 60 条 →
    单次调用组织成两级导图（reduce）。分段结果按块序号合并，
    导图方向与讲解顺序保持一致。
    """
    chunks = _split_chunks(transcript_text)
    if len(chunks) == 1:
        payload = _chat_json(_mindmap_prompt(chunks[0], course_title))
        return _normalize_mindmap(payload, course_title)

    total = len(chunks)

    def _map(index: int, chunk: str) -> list[dict]:
        payload = _chat_json(_keypoint_prompt(chunk, course_title, index + 1, total))
        items = _normalize_keypoints(payload.get("keypoints"))
        logger.info("[llm] 导图分段 {}/{} 完成：{} 条关键点", index + 1, total, len(items))
        return items

    collected: list[dict] = []
    for items in map_ordered(
        _map, chunks, settings.siliconflow_llm_workers, thread_name_prefix="llm-mindmap",
    ):
        collected.extend(items)

    merged = _dedupe_keypoints(collected)[:60]
    if not merged:
        return {"root_topic": course_title, "nodes": []}
    reduced = _chat_json(_mindmap_reduce_prompt(merged, course_title))
    return _normalize_mindmap(reduced, course_title)


def _mindmap_prompt(text: str, course_title: str) -> str:
    return (
        f"课程《{course_title}》的课堂转写（每行格式为 [起始秒] 文本）。\n"
        "请生成两级思维导图：课程主题 → 知识模块 → 知识点。只输出 JSON：\n"
        '{"root_topic": "课程主题",\n'
        ' "nodes": [{"module": "知识模块名", "knowledge_points": '
        '[{"name": "知识点", "timestamp_sec": 123.4}]}]}\n'
        "规则：\n"
        "- 严格两级：knowledge_points 内不得再嵌套任何层级；模块 3–8 个，每个模块 2–6 个知识点；\n"
        "- module 是按内容聚类出的模块名（≤12 字），不要写「第一部分」「其他」这类空模块；\n"
        "- name 是知识点名称（≤20 字）；同一知识点只出现一次；\n"
        "- timestamp_sec 取该知识点首次讲到的行首秒数，没有对应位置时填 null；\n"
        "- 只使用转写中出现的内容，不要补充外部知识。\n"
        f"转写：\n{text}"
    )


def _mindmap_reduce_prompt(keypoints: list[dict], course_title: str) -> str:
    lines = "\n".join(f"- [{k['timestamp_sec']}] {k['title']}" for k in keypoints)
    return (
        f"以下是课程《{course_title}》的重点时间点（格式「[秒] 名称」）：\n{lines}\n\n"
        "请把它们组织成两级思维导图：课程主题 → 知识模块 → 知识点。只输出 JSON：\n"
        '{"root_topic": "课程主题",\n'
        ' "nodes": [{"module": "知识模块名", "knowledge_points": '
        '[{"name": "知识点", "timestamp_sec": 123.4}]}]}\n'
        "规则：\n"
        "- 严格两级，模块 3–8 个，每个模块 2–6 个知识点；\n"
        "- knowledge_points 的名称与时间戳只能来自上面的列表，不得新增条目、不得改写时间戳；\n"
        "- 同一知识点只归入一个模块；时间戳必须与列表完全一致。"
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
