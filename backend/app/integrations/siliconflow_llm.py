"""硅基流动大模型客户端。重点抽取 / 分层总结 / 两级思维导图。

仅基于传入转写文本生成，Prompt 明确禁止引入外部知识（防幻觉）。
"""
from app.config import settings

_SYSTEM_PROMPT = (
    "你是课程内容分析助手。仅根据用户提供的课程转写文本生成结果，"
    "不得引入转写中未出现的外部知识。所有时间点必须来自转写提供的时间戳。"
)


def _chat(user_prompt: str) -> str:
    if not settings.siliconflow_api_key:
        raise RuntimeError("硅基流动 API Key 未配置")
    # TODO: httpx 调用 settings.siliconflow_base_url + "/chat/completions"
    #       model=settings.siliconflow_model, messages=[system, user]
    raise NotImplementedError("硅基流动 LLM 调用实现待补充")


def extract_keypoints(transcript_text: str, course_title: str) -> list[dict]:
    prompt = f"课程《{course_title}》转写文本如下，请抽取重点时间点（概念/公式/例题/考点），每点含 title/category/summary/timestamp_sec：\n{transcript_text}"
    _chat(prompt)
    return []


def generate_summary(transcript_text: str, course_title: str) -> dict:
    prompt = f"课程《{course_title}》转写文本如下，请生成分层总结（overview/chapter_points/key_details/review_hints）：\n{transcript_text}"
    _chat(prompt)
    return {}


def generate_mindmap(transcript_text: str, course_title: str) -> dict:
    prompt = f"课程《{course_title}》转写文本如下，请生成两级思维导图（root_topic + nodes[{module, knowledge_points:[{name, timestamp_sec}]}]）：\n{transcript_text}"
    _chat(prompt)
    return {}