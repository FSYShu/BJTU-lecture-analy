"""A2：硅基流动 LLM 客户端与解析步骤测试（mock 模型调用）。"""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.integrations import siliconflow_llm
from app.pipeline.errors import StepError
from app.pipeline.steps import llm as llm_step


class _Course:
    """run_llm 只用到 course.title。"""

    title = "信号与系统"


# --------------------------------------------------------------------------- #
# JSON 容错与规范化
# --------------------------------------------------------------------------- #
def test_loads_handles_fences_and_prose():
    assert siliconflow_llm._loads('```json\n{"a": 1}\n```') == {"a": 1}
    assert siliconflow_llm._loads('好的，结果如下：{"a": 2} 以上。') == {"a": 2}


def test_loads_raises_on_invalid_json():
    with pytest.raises(ValueError):
        siliconflow_llm._loads("这里没有 JSON")


def test_chat_json_repairs_once(monkeypatch):
    """第一次输出不是 JSON，回灌错误后第二次成功（A2-4）。"""
    outputs = iter(["不是 JSON", json.dumps({"keypoints": []})])
    prompts: list[str] = []

    def fake_chat(prompt: str) -> str:
        prompts.append(prompt)
        return next(outputs)

    monkeypatch.setattr(siliconflow_llm, "_chat", fake_chat)
    assert siliconflow_llm._chat_json("原始提示") == {"keypoints": []}
    assert len(prompts) == 2
    assert "无法解析为 JSON" in prompts[1]


def test_normalize_category_aliases():
    assert siliconflow_llm._normalize_category("公式") == "formula"
    assert siliconflow_llm._normalize_category("EXAM_POINT") == "exam_point"
    assert siliconflow_llm._normalize_category("考点") == "exam_point"
    assert siliconflow_llm._normalize_category("乱七八糟") == "concept"
    assert siliconflow_llm._normalize_category(None) == "concept"


def test_normalize_keypoints_drops_invalid():
    items = siliconflow_llm._normalize_keypoints([
        {"title": "傅里叶变换", "category": "公式", "summary": "定义", "timestamp_sec": "12.5"},
        {"title": "", "timestamp_sec": 3},
        {"title": "无时间点"},
        "不是对象",
    ])
    assert items == [{
        "title": "傅里叶变换",
        "category": "formula",
        "summary": "定义",
        "timestamp_sec": 12.5,
    }]


def test_normalize_mindmap_enforces_two_levels():
    result = siliconflow_llm._normalize_mindmap({
        "root_topic": "信号与系统",
        "nodes": [
            {"module": "傅里叶分析", "knowledge_points": [
                {"name": "定义", "timestamp_sec": "10:00", "children": [{"name": "第三层"}]},
                "级数",
            ]},
            {"knowledge_points": [{"name": "缺少模块名"}]},
        ],
    }, "默认主题")
    assert result["root_topic"] == "信号与系统"
    assert len(result["nodes"]) == 1
    points = result["nodes"][0]["knowledge_points"]
    assert points[0] == {"name": "定义", "timestamp_sec": 600.0}
    assert points[1]["timestamp_sec"] is None


def test_normalize_summary_accepts_strings_and_dicts():
    summary = siliconflow_llm._normalize_summary({
        "overview": "本节讲傅里叶变换",
        "chapter_points": [{"chapter": "第一章", "points": ["要点"]}, "第二章"],
        "key_details": [{"title": "定义", "detail": "详解"}],
        "review_hints": ["复习提示", ""],
    })
    assert summary["overview"] == "本节讲傅里叶变换"
    assert summary["chapter_points"][0] == {"chapter": "第一章", "points": ["要点"]}
    assert summary["chapter_points"][1] == {"chapter": "第二章", "points": []}
    assert summary["review_hints"] == ["复习提示"]


def test_normalize_summary_with_none_returns_empty_structure():
    summary = siliconflow_llm._normalize_summary(None)
    assert summary == {"overview": None, "chapter_points": [], "key_details": [], "review_hints": []}


# --------------------------------------------------------------------------- #
# 长文本分段
# --------------------------------------------------------------------------- #
def test_split_chunks_respects_limit(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_max_input_chars", 1000)
    text = "\n".join(f"[{i}.0] 这是第 {i} 行课程内容，用于触发分段逻辑。" for i in range(100))
    chunks = siliconflow_llm._split_chunks(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "\n".join(chunks) == text


def test_extract_keypoints_merges_duplicates_across_chunks(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_max_input_chars", 100)
    text = "\n".join(f"[{i * 10}.0] 第 {i} 句课程内容，用于触发分段。" for i in range(20))
    calls = {"count": 0}

    def fake_chat(prompt: str) -> str:
        calls["count"] += 1
        timestamp = 10.0 if calls["count"] == 1 else 500.0
        return json.dumps({"keypoints": [
            {"title": "傅里叶变换", "category": "概念", "summary": "定义", "timestamp_sec": timestamp},
            {"title": "傅里叶变换", "category": "概念", "summary": "重复项", "timestamp_sec": timestamp + 5},
        ]}, ensure_ascii=False)

    monkeypatch.setattr(siliconflow_llm, "_chat", fake_chat)
    out = siliconflow_llm.extract_keypoints(text, "信号与系统")
    assert calls["count"] > 1
    # 邻近同名去重；相隔超过同名窗口的保留为不同知识点
    assert [item["timestamp_sec"] for item in out] == [10.0, 500.0]


# --------------------------------------------------------------------------- #
# 解析步骤
# --------------------------------------------------------------------------- #
def test_format_transcript_includes_timestamps():
    text = llm_step.format_transcript([{"text": "你好。", "start_sec": 12.34, "end_sec": 14.0}])
    assert text == "[12.3] 你好。"


def test_link_source_transcripts_matches_window_or_nearest():
    transcripts = [
        {"text": "A", "start_sec": 0.0, "end_sec": 5.0},
        {"text": "B", "start_sec": 5.0, "end_sec": 10.0},
        {"text": "C", "start_sec": 100.0, "end_sec": 110.0},
    ]
    keypoints = [{"title": "x", "timestamp_sec": 5.5}, {"title": "y", "timestamp_sec": 300.0}]
    llm_step.link_source_transcripts(keypoints, transcripts, tolerance_sec=2)
    assert keypoints[0]["source_transcript_seqs"] == [1]
    assert keypoints[1]["source_transcript_seqs"] == [2]


def test_run_llm_partial_failure_keeps_successes(monkeypatch):
    monkeypatch.setattr(llm_step, "_extract_keypoints", lambda text, title: [
        {"title": "定义", "category": "concept", "summary": "", "timestamp_sec": 5.0},
    ])

    def boom(text, title):
        raise RuntimeError("summary failed")

    monkeypatch.setattr(llm_step, "_generate_summary", boom)
    monkeypatch.setattr(llm_step, "_generate_mindmap", lambda text, title: {
        "root_topic": "主题",
        "nodes": [{"module": "M", "knowledge_points": [{"name": "定义", "timestamp_sec": 5.0}]}],
    })

    transcripts = [{"text": "定义在开头。", "start_sec": 5.0, "end_sec": 9.0}]
    keypoints, summary, mindmap, failures = llm_step.run_llm(transcripts, _Course(), 1)

    assert summary == {}
    assert mindmap["root_topic"] == "主题"
    assert len(keypoints) == 1 and keypoints[0]["source_transcript_seqs"] == [0]
    assert len(failures) == 1 and "课程总结" in failures[0]


def test_run_llm_all_failed_raises_step_error(monkeypatch):
    def boom(text, title):
        raise RuntimeError("模型不可用")

    monkeypatch.setattr(llm_step, "_extract_keypoints", boom)
    monkeypatch.setattr(llm_step, "_generate_summary", boom)
    monkeypatch.setattr(llm_step, "_generate_mindmap", boom)

    transcripts = [{"text": "内容。", "start_sec": 0.0, "end_sec": 1.0}]
    with pytest.raises(StepError) as excinfo:
        llm_step.run_llm(transcripts, _Course(), 1)
    assert excinfo.value.code == "LLM_ERROR"


def test_run_llm_empty_transcript_raises(monkeypatch):
    with pytest.raises(StepError) as excinfo:
        llm_step.run_llm([], _Course(), 1)
    assert excinfo.value.code == "LLM_ERROR"
