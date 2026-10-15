"""A3：平台字幕（VTT）与知识点（zsd）接入测试。"""
from __future__ import annotations

import pytest

from app.pipeline.steps import platform_assets

VTT = """WEBVTT

NOTE 平台导出的字幕

STYLE
::cue { color: white }

1
00:00:00.000 --> 00:00:03.500
<v 老师>大家好，今天讲傅里叶变换。

2
00:00:03.500 --> 00:00:08.000
先看定义。
"""


def test_parse_vtt_basic():
    sentences = platform_assets.parse_vtt(VTT)
    assert [item["text"] for item in sentences] == ["大家好，今天讲傅里叶变换。", "先看定义。"]
    first = sentences[0]
    assert first["start_sec"] == 0.0
    assert first["end_sec"] == 3.5
    assert first["ai_generated"] is False
    assert first["source_model"] == "platform-vtt"


def test_parse_vtt_empty_or_garbage():
    assert platform_assets.parse_vtt("") == []
    assert platform_assets.parse_vtt("<html><body>404</body></html>") == []


def test_parse_vtt_makes_timeline_monotonic():
    overlapping = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:05.000\n第一句。\n\n"
        "00:00:03.000 --> 00:00:04.000\n第二句。\n"
    )
    sentences = platform_assets.parse_vtt(overlapping)
    assert sentences[0]["end_sec"] >= sentences[0]["start_sec"]
    assert sentences[1]["start_sec"] >= sentences[0]["end_sec"]


def test_vtt_coverage():
    sentences = [
        {"text": "a", "start_sec": 0.0, "end_sec": 30.0},
        {"text": "b", "start_sec": 30.0, "end_sec": 60.0},
    ]
    assert platform_assets.vtt_coverage(sentences, 120) == pytest.approx(0.5)
    assert platform_assets.vtt_coverage([], 120) == 0.0
    assert platform_assets.vtt_coverage(sentences, 0) == 1.0


def test_map_zsd_infers_category_and_drops_out_of_range():
    items = [
        {"zsd_name": "课程介绍", "zsd_wait_time": 3},
        {"zsd_name": "傅里叶系数公式", "zsd_wait_time": 21, "sfm": "00:00:21"},
        {"zsd_name": "考试常考点", "zsd_wait_time": 29},
        {"zsd_name": "例题：方波展开", "zsd_wait_time": 37},
        {"zsd_name": "越界知识点", "zsd_wait_time": 9999},
        {"zsd_name": "只有 sfm 字段", "sfm": "00:01:05"},
        {"zsd_wait_time": 12},
    ]
    mapped = platform_assets.map_zsd(items, duration_sec=3600)

    assert [item["title"] for item in mapped] == [
        "课程介绍", "傅里叶系数公式", "考试常考点", "例题：方波展开", "只有 sfm 字段",
    ]
    by_title = {item["title"]: item for item in mapped}
    assert by_title["课程介绍"]["category"] == "concept"
    assert by_title["傅里叶系数公式"]["category"] == "formula"
    assert by_title["考试常考点"]["category"] == "exam_point"
    assert by_title["例题：方波展开"]["category"] == "example"
    assert by_title["只有 sfm 字段"]["timestamp_sec"] == 65.0
    assert by_title["课程介绍"]["ai_generated"] is False
    assert by_title["课程介绍"]["source_model"] == "platform-zsd"
    assert "越界知识点" not in by_title


def test_align_keypoints_prefers_platform_within_tolerance():
    platform = [{
        "title": "傅里叶系数公式", "category": "formula", "summary": None,
        "timestamp_sec": 21.0, "ai_generated": False, "source_model": "platform-zsd",
    }]
    ai = [
        {"title": "傅里叶系数", "category": "formula", "summary": "重复", "timestamp_sec": 21.5, "ai_generated": True},
        {"title": "Parseval 定理", "category": "exam_point", "summary": "补充", "timestamp_sec": 45.5, "ai_generated": True},
    ]

    merged = platform_assets.align_keypoints(ai, platform, tolerance_sec=2)
    assert [item["title"] for item in merged] == ["傅里叶系数公式", "Parseval 定理"]
    assert [item["seq_index"] for item in merged] == [0, 1]
    assert merged[0]["ai_generated"] is False


def test_align_keypoints_without_platform_keeps_sorted_ai():
    ai = [
        {"title": "后", "timestamp_sec": 90.0},
        {"title": "前", "timestamp_sec": 10.0},
    ]
    merged = platform_assets.align_keypoints(ai, [])
    assert [item["title"] for item in merged] == ["前", "后"]
    assert [item["seq_index"] for item in merged] == [0, 1]
    assert all(item["ai_generated"] is True for item in merged)
