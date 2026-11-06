"""聚合端点（docs/11 流量优化 F4）单测。

直接调用路由函数而不是走 TestClient：这里要验的是聚合逻辑（哪些字段、
缺结果时怎么返回），鉴权与 HTTP 语义由 deps 与 FastAPI 本身保证。
"""
from app.api.v1.lectures import get_overview
from app.db.models import Course, Keypoint, Lecture, ParseTask, Summary, Transcript


def _seed(db, *, with_llm: bool = True):
    course = Course(
        title="算法设计与分析", video_url="https://example.com/a.m3u8", source="platform"
    )
    db.add(course)
    db.flush()

    lecture = Lecture(course_id=course.id, platform_replay_id="rp-1")
    db.add(lecture)
    db.flush()

    task = ParseTask(course_id=course.id, lecture_id=lecture.id, status="succeeded", progress=100)
    db.add(task)
    db.flush()

    for seq, (start, text) in enumerate([(0.0, "开场"), (61.5, "主定理"), (3600.0, "总结")]):
        db.add(Transcript(
            task_id=task.id, course_id=course.id, lecture_id=lecture.id,
            seq_index=seq, text=text, start_sec=start, end_sec=start + 5.0,
        ))

    if with_llm:
        db.add(Keypoint(
            task_id=task.id, course_id=course.id, lecture_id=lecture.id, seq_index=0,
            title="主定理", category="concept", timestamp_sec=61.5,
        ))
        db.add(Summary(
            task_id=task.id, course_id=course.id, lecture_id=lecture.id, overview="本章概览",
        ))

    db.commit()
    return course, lecture, task


def test_overview_aggregates_all_results(db):
    _, lecture, _ = _seed(db)

    overview = get_overview(lecture.id, _lecture=lecture, db=db)

    assert overview.lecture_id == lecture.id
    assert [k.title for k in overview.keypoints] == ["主定理"]
    assert overview.summary is not None and overview.summary.overview == "本章概览"
    assert overview.mindmap is None
    assert overview.transcript_meta.total == 3
    assert overview.transcript_meta.first.text == "开场"
    assert overview.transcript_meta.last.text == "总结"


def test_overview_keeps_latest_task(db):
    _, lecture, _ = _seed(db)

    overview = get_overview(lecture.id, _lecture=lecture, db=db)

    assert overview.task is not None
    assert overview.task.status == "succeeded"


def test_overview_returns_nulls_for_half_finished_parse(db):
    """解析只跑完转写时，首屏仍要能拿到转写，而不是整页 404。"""
    _, lecture, _ = _seed(db, with_llm=False)

    overview = get_overview(lecture.id, _lecture=lecture, db=db)

    assert overview.keypoints == []
    assert overview.summary is None
    assert overview.mindmap is None
    assert overview.transcript_meta.total == 3


def test_overview_of_empty_lecture(db):
    course = Course(title="空课次", video_url="https://example.com/b.m3u8", source="manual")
    db.add(course)
    db.flush()
    lecture = Lecture(course_id=course.id, platform_replay_id="rp-empty")
    db.add(lecture)
    db.commit()

    overview = get_overview(lecture.id, _lecture=lecture, db=db)

    assert overview.keypoints == []
    assert overview.transcript_meta.total == 0
    assert overview.transcript_meta.first is None
    assert overview.task is None
