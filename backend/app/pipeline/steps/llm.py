"""Step 5：调用大模型语义解析。

仅基于本节转写生成，每条结果记录 source_model + generated_at。
对应 docs/05-risk-handling.md 防幻觉。
"""
from app.config import settings
from app.db.models import Course
from app.integrations import siliconflow_llm
from app.pipeline.retry import with_retry


@with_retry(
    max_attempts=settings.siliconflow_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="llm",
)
def run_llm(transcripts: list[dict], course: Course, task_id: int) -> tuple[list[dict], dict, dict]:
    text = "\n".join(t["text"] for t in transcripts)
    keypoints = siliconflow_llm.extract_keypoints(text, course.title)
    summary = siliconflow_llm.generate_summary(text, course.title)
    mindmap = siliconflow_llm.generate_mindmap(text, course.title)
    return keypoints, summary, mindmap