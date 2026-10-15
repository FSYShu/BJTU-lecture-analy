"""A4-1：持久化校验测试（时间戳边界、来源标识、枚举、溯源、部分结果）。"""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.db.models import Course, Keypoint, Mindmap, ParseTask, Summary, Transcript
from app.pipeline.errors import StepError
from app.pipeline.steps import persist


def _fixtures(db, duration: int = 600) -> tuple[Course, ParseTask]:
    course = Course(title="信号与系统", video_url="http://example.com/a.m3u8", duration_sec=duration, source="manual")
    db.add(course)
    db.commit()
    db.refresh(course)

    task = ParseTask(course_id=course.id, status="llm_running")
    db.add(task)
    db.commit()
    db.refresh(task)
    return course, task


def test_save_results_writes_all_tables(db_session):
    course, task = _fixtures(db_session)
    transcripts = [
        {"text": "平台字幕一", "start_sec": 0.0, "end_sec": 2.0,
         "ai_generated": False, "source_model": "platform-vtt"},
        {"text": "ASR 字幕二", "start_sec": 2.0, "end_sec": 4.0},
    ]
    keypoints = [
        {"title": "傅里叶变换", "category": "公式", "summary": "定义",
         "timestamp_sec": 3.0, "source_transcript_seqs": [1]},
        {"title": "越界重点", "category": "concept", "summary": "", "timestamp_sec": 9999.0},
    ]
    summary = {
        "overview": "概览",
        "chapter_points": [{"chapter": "第一章", "points": ["要点"]}],
        "key_details": [],
        "review_hints": ["复习"],
    }
    mindmap = {
        "root_topic": "信号与系统",
        "nodes": [{"module": "傅里叶", "knowledge_points": [{"name": "定义", "timestamp_sec": 3.0}]}],
    }

    persist.save_results(db_session, task.id, course.id, transcripts, keypoints, summary, mindmap)

    rows = db_session.query(Transcript).order_by(Transcript.seq_index).all()
    assert [row.seq_index for row in rows] == [0, 1]
    assert rows[0].source_model == "platform-vtt" and rows[0].ai_generated is False
    assert rows[1].source_model == settings.siliconflow_asr_model and rows[1].ai_generated is True

    saved_keypoints = db_session.query(Keypoint).all()
    assert len(saved_keypoints) == 1
    assert saved_keypoints[0].category == "concept"          # 非法枚举归为 concept
    assert saved_keypoints[0].timestamp_sec == 3.0
    assert saved_keypoints[0].source_model == settings.siliconflow_model
    assert json.loads(saved_keypoints[0].source_transcript_ids) == [rows[1].id]

    assert db_session.query(Summary).count() == 1
    assert db_session.query(Mindmap).count() == 1


def test_save_results_keeps_platform_keypoints_not_ai_generated(db_session):
    course, task = _fixtures(db_session)
    keypoints = [{
        "title": "平台打点", "category": "exam_point", "summary": None, "timestamp_sec": 30.0,
        "ai_generated": False, "source_model": "platform-zsd",
    }]
    persist.save_results(db_session, task.id, course.id, [], keypoints, {}, {})

    saved = db_session.query(Keypoint).one()
    assert saved.ai_generated is False
    assert saved.source_model == "platform-zsd"
    assert json.loads(saved.source_transcript_ids) == []


def test_save_results_skips_empty_summary_and_mindmap(db_session):
    course, task = _fixtures(db_session)
    transcripts = [{"text": "只有字幕", "start_sec": 0.0, "end_sec": 1.0}]

    persist.save_results(db_session, task.id, course.id, transcripts, [], {}, {})

    assert db_session.query(Transcript).count() == 1
    assert db_session.query(Summary).count() == 0
    assert db_session.query(Mindmap).count() == 0


def test_save_results_clamps_transcript_end_to_duration(db_session):
    course, task = _fixtures(db_session, duration=600)
    transcripts = [{"text": "越界字幕", "start_sec": 599.0, "end_sec": 900.0}]

    persist.save_results(db_session, task.id, course.id, transcripts, [], {}, {})

    row = db_session.query(Transcript).one()
    assert row.start_sec == 599.0
    assert row.end_sec == 600.0


def test_save_results_drops_transcript_starting_past_duration(db_session):
    course, task = _fixtures(db_session, duration=600)
    transcripts = [
        {"text": "正常", "start_sec": 0.0, "end_sec": 1.0},
        {"text": "完全越界", "start_sec": 700.0, "end_sec": 800.0},
    ]

    persist.save_results(db_session, task.id, course.id, transcripts, [], {}, {})

    rows = db_session.query(Transcript).all()
    assert [row.text for row in rows] == ["正常"]


def test_save_results_wraps_failure_as_persist_fail(db_session, monkeypatch):
    course, task = _fixtures(db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("数据库写入失败")

    monkeypatch.setattr(persist, "_save_transcripts", boom)

    with pytest.raises(StepError) as excinfo:
        persist.save_results(db_session, task.id, course.id, [], [], {}, {})

    assert excinfo.value.code == "PERSIST_FAIL"
    assert db_session.query(Transcript).count() == 0
