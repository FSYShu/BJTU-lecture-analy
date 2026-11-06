"""任务状态 SSE 推送（docs/11 优化 4）单测。

直接驱动异步生成器，用假 ``sleep`` 推进任务状态，验证：
- 只在快照变化时发 data 帧；
- 到达 succeeded/failed 立即结束；
- 任务不存在时给出 error 事件而不是空转。
"""
import json

from sqlalchemy.orm import sessionmaker

from app.db.models import Course, ParseTask
from app.services.task_stream import task_events


def _make_task(db) -> ParseTask:
    course = Course(title="SSE 测试课", video_url="https://example.com/c.m3u8", source="manual")
    db.add(course)
    db.flush()
    task = ParseTask(course_id=course.id, status="queued", progress=0, current_step="queued")
    db.add(task)
    db.commit()
    return task


def _data_frames(frames: list[str]) -> list[dict]:
    return [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: ")
    ]


def _session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


async def test_stream_stops_at_terminal_status(engine, db):
    task = _make_task(db)
    factory = _session_factory(engine)

    async def sleep_and_finish(_interval: float) -> None:
        """第一次等待后把任务推进到 succeeded，模拟 worker 跑完。"""
        session = factory()
        try:
            session.get(ParseTask, task.id).status = "succeeded"
            session.commit()
        finally:
            session.close()

    frames = [f async for f in task_events(task.id, factory, sleep=sleep_and_finish)]

    payloads = _data_frames(frames)
    assert [p["status"] for p in payloads] == ["queued", "succeeded"]


async def test_stream_does_not_repeat_unchanged_status(engine, db):
    task = _make_task(db)
    factory = _session_factory(engine)
    calls = {"n": 0}

    async def sleep_until_finished(_interval: float) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            return  # 前两次状态不变，应只发心跳
        session = factory()
        try:
            session.get(ParseTask, task.id).status = "failed"
            session.commit()
        finally:
            session.close()

    frames = [
        f async for f in task_events(
            task.id, factory, sleep=sleep_until_finished, interval=1.0, heartbeat_seconds=1.0
        )
    ]

    payloads = _data_frames(frames)
    assert [p["status"] for p in payloads] == ["queued", "failed"]
    assert ": keep-alive\n\n" in frames


async def test_stream_reports_missing_task(engine):
    factory = _session_factory(engine)

    async def noop_sleep(_interval: float) -> None:
        return None

    frames = [f async for f in task_events(9999, factory, sleep=noop_sleep)]

    assert len(frames) == 1
    assert frames[0].startswith("event: error")


async def test_stream_closes_when_max_duration_exceeded(engine, db):
    task = _make_task(db)
    factory = _session_factory(engine)

    async def noop_sleep(_interval: float) -> None:
        return None

    frames = [
        f async for f in task_events(task.id, factory, sleep=noop_sleep, max_seconds=-1)
    ]

    assert ": keep-alive" not in "".join(frames)
    assert "event: error" in frames[-1]
