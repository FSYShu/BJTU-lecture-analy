"""Step 5：调用大模型语义解析（A2）。

- 输入必须是**带时间戳**的转写行（``[起始秒] 文本``），否则模型只能编造时间点（A2-1）；
- 三个子任务各自重试（``SILICONFLOW_MAX_RETRY``），任一失败只降级该项，其余结果保留
  （docs/05:10：已生成的部分结果不回滚丢失）；
- 重点时间点用本地转写句 seq 溯源，不信任模型输出（docs/03:126、docs/05:49）。
"""
from __future__ import annotations

from loguru import logger

from app.config import settings
from app.db.models import Course
from app.integrations import siliconflow_llm
from app.pipeline.errors import StepError
from app.pipeline.retry import with_retry


def format_transcript(transcripts: list[dict]) -> str:
    """把转写拼成 ``[起始秒] 文本``；时间戳必须进 prompt，否则无法产出可跳转的时间点。"""
    lines: list[str] = []
    for item in transcripts or []:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(item.get("start_sec", 0.0))
        except (TypeError, ValueError):
            start = 0.0
        lines.append(f"[{start:.1f}] {text}")
    return "\n".join(lines)


@with_retry(
    max_attempts=settings.siliconflow_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="llm-keypoints",
)
def _extract_keypoints(text: str, course_title: str) -> list[dict]:
    return siliconflow_llm.extract_keypoints(text, course_title)


@with_retry(
    max_attempts=settings.siliconflow_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="llm-summary",
)
def _generate_summary(text: str, course_title: str) -> dict:
    return siliconflow_llm.generate_summary(text, course_title)


@with_retry(
    max_attempts=settings.siliconflow_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="llm-mindmap",
)
def _generate_mindmap(text: str, course_title: str) -> dict:
    return siliconflow_llm.generate_mindmap(text, course_title)


def run_llm(
    transcripts: list[dict],
    course: Course,
    task_id: int,
) -> tuple[list[dict], dict, dict, list[str]]:
    """生成 ``(重点, 分层总结, 两级导图, 失败项列表)``。

    全部子任务失败时抛 ``StepError(LLM_ERROR)``；部分失败时返回已成功的结果 + 失败说明，
    由编排层先落库、再把任务标记为 failed 供重试（docs/05:10、AC-02-06）。
    """
    text = format_transcript(transcripts)
    if not text:
        raise StepError("LLM_ERROR", "转写为空，无法生成解析结果", step="llm")

    keypoints: list[dict] = []
    summary: dict = {}
    mindmap: dict = {}
    failures: list[str] = []

    try:
        keypoints = _extract_keypoints(text, course.title) or []
    except Exception as exc:  # noqa: BLE001 - 单项降级，其余子任务继续
        failures.append(f"重点时间点：{exc}")
        logger.warning("[llm] 重点时间点生成失败：{}", exc)

    try:
        summary = _generate_summary(text, course.title) or {}
    except Exception as exc:  # noqa: BLE001
        failures.append(f"课程总结：{exc}")
        logger.warning("[llm] 课程总结生成失败：{}", exc)

    try:
        mindmap = _generate_mindmap(text, course.title) or {}
    except Exception as exc:  # noqa: BLE001
        failures.append(f"思维导图：{exc}")
        logger.warning("[llm] 思维导图生成失败：{}", exc)

    if len(failures) == 3:
        raise StepError("LLM_ERROR", "重点/总结/导图全部生成失败：" + "；".join(failures)[:400], step="llm")

    keypoints = link_source_transcripts(keypoints, transcripts)
    return keypoints, summary, mindmap, failures


def link_source_transcripts(
    keypoints: list[dict],
    transcripts: list[dict],
    tolerance_sec: float | None = None,
) -> list[dict]:
    """为重点时间点补上 ``source_transcript_seqs``（转写句序号），用于溯源。

    匹配规则：时间点落在转写句区间内，或与某句句首相差不超过
    ``TIMESTAMP_TOLERANCE_SEC``；都不命中时取时间上最近的一句。
    序号由 persist 换算成真实的 ``source_transcript_ids``。
    """
    tolerance = settings.timestamp_tolerance_sec if tolerance_sec is None else tolerance_sec
    if not transcripts:
        return keypoints

    starts = [float(item.get("start_sec", 0.0) or 0.0) for item in transcripts]
    ends = [float(item.get("end_sec", 0.0) or 0.0) for item in transcripts]

    for keypoint in keypoints or []:
        if keypoint.get("source_transcript_seqs"):
            continue
        timestamp = float(keypoint.get("timestamp_sec", 0.0) or 0.0)
        seqs = [
            index
            for index, (start, end) in enumerate(zip(starts, ends))
            if (start <= timestamp <= end) or abs(start - timestamp) <= tolerance
        ]
        if not seqs:
            nearest = min(range(len(starts)), key=lambda i: abs(starts[i] - timestamp))
            seqs = [nearest]
        keypoint["source_transcript_seqs"] = seqs[:5]
    return keypoints
