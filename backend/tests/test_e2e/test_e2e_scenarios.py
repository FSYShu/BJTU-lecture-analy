"""端到端验收脚本：E2E-01/02/03。

使用 TestClient 模拟完整用户旅程，覆盖：
- E2E-01：学生完整回看链路（登录→课程列表→解析→字幕/重点/总结/导图→跳转→刷新）
- E2E-02：失败与恢复链路（失效地址→失败原因→重试→恢复成功）
- E2E-03：越权拦截链路（student_b 登录→课程A接口→全部 403）

运行方式：
    cd backend && uv run python -m pytest tests/test_e2e/test_e2e_scenarios.py -v
"""
import json

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.v1 import courses as courses_api
from app.api.v1 import platform as platform_api
from app.api.v1 import tasks as tasks_api
from app.config import settings
from app.db.models import (
    Course,
    Keypoint,
    Lecture,
    Mindmap,
    ParseTask,
    Summary,
    Transcript,
    User,
)
from app.integrations import platform as platform_integration
from app.services import authorization_service
from app.services.auth_service import create_user

BASE = "/api/v1"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, username: str, password: str) -> str:
    resp = client.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _patch_session_local(monkeypatch, engine):
    TestingSL = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    import app.db.session as session_mod
    monkeypatch.setattr(session_mod, "SessionLocal", TestingSL)


def _enable_ai(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_api_key", "sk-test")
    monkeypatch.setattr(settings, "platform_base_url", "http://platform.test")


def _stub_worker_success(monkeypatch):
    """模拟 worker 成功完成：落库转写+重点+总结+导图，任务标记 succeeded。"""
    def fake_worker(task_id):
        from app.db.session import SessionLocal
        from app.services import task_service
        s = SessionLocal()
        try:
            task = s.get(ParseTask, task_id)
            if not task:
                return
            course_id = task.course_id
            lecture_id = task.lecture_id
            if lecture_id is None:
                lec = s.query(Lecture).filter(Lecture.course_id == course_id).first()
                lecture_id = lec.id if lec else None
                task.lecture_id = lecture_id
                s.flush()

            s.add_all([
                Transcript(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=0,
                           text="今天讲操作系统进程管理", start_sec=0.0, end_sec=5.0, ai_generated=True),
                Transcript(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=1,
                           text="进程是程序的一次执行", start_sec=5.0, end_sec=10.0, ai_generated=True),
            ])
            s.add(Keypoint(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=0,
                           title="进程与线程", category="concept", timestamp_sec=120.0, ai_generated=True))
            s.add(Summary(task_id=task_id, course_id=course_id, lecture_id=lecture_id,
                          overview="本讲介绍进程管理", ai_generated=True))
            s.add(Mindmap(task_id=task_id, course_id=course_id, lecture_id=lecture_id,
                          root_topic="进程管理", nodes='[{"module":"进程","knowledge_points":[{"name":"进程概念"}]}]',
                          ai_generated=True))
            s.commit()
            task_service.update_status(s, task_id, "succeeded", 100, "done")
            from datetime import datetime, timezone
            task.finished_at = datetime.now(timezone.utc)
            s.commit()
        finally:
            s.close()

    monkeypatch.setattr(courses_api, "parse_worker_run", fake_worker)
    monkeypatch.setattr(tasks_api, "parse_worker_run", fake_worker)
    monkeypatch.setattr(platform_api, "parse_worker_run", fake_worker)


def _stub_worker_fail(monkeypatch, error_code="IO_ERROR", error_msg="音频提取失败"):
    """模拟 worker 失败：任务标记 failed。"""
    def fake_worker(task_id):
        from app.db.session import SessionLocal
        from app.services import task_service
        s = SessionLocal()
        try:
            task_service.mark_failed(s, task_id, error_code, error_msg)
        finally:
            s.close()

    monkeypatch.setattr(courses_api, "parse_worker_run", fake_worker)
    monkeypatch.setattr(tasks_api, "parse_worker_run", fake_worker)
    monkeypatch.setattr(platform_api, "parse_worker_run", fake_worker)


# ============================================================================ #
# E2E-01：学生完整回看链路
# ============================================================================ #

class TestE2E01StudentFullJourney:
    """E2E-01 学生完整回看链路：登录→课程列表→解析→字幕/重点/总结/导图→刷新。"""

    def test_student_full_journey(self, client, db, monkeypatch, engine):
        _enable_ai(monkeypatch)
        _patch_session_local(monkeypatch, engine)
        _stub_worker_success(monkeypatch)

        teacher = create_user(db, "teacher1", "pw123456", role="teacher", display_name="教师")
        teacher.platform_cookies = json.dumps([{"name": "SESSION", "value": "abc"}])
        db.commit()
        student = create_user(db, "student1", "pw123456", role="student", display_name="学生")
        student.platform_cookies = json.dumps([{"name": "SESSION", "value": "abc"}])
        db.commit()

        course = Course(title="操作系统", video_url="http://x/v.m3u8", source="platform",
                        course_num="OS101", fz_id="20260101", platform_c_id=8801,
                        teacher_name="王老师", platform_course_id="2026001")
        db.add(course)
        db.commit()
        db.refresh(course)

        lecture = Lecture(course_id=course.id, platform_replay_id="9001",
                          teach_time_str="2026-03-01", video_url="http://x/v.m3u8")
        db.add(lecture)
        db.commit()
        db.refresh(lecture)

        authorization_service.grant(db, course.id, student.id, teacher.id, valid_until=None)

        async def fake_fetch_replays(cookies, c_id):
            return [{"id": 9001, "teachTimeStr": "2026-03-01", "classRoom": "A101",
                     "courseBetween": "第1周", "videoId": "v1", "uuid": "u1"}]
        monkeypatch.setattr(platform_integration, "fetch_replays", fake_fetch_replays)

        token = _login(client, "student1", "pw123456")

        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        courses_list = resp.json()
        assert any(c["id"] == course.id for c in courses_list)

        resp = client.get(f"{BASE}/courses/OS101-01", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["title"] == "操作系统"

        resp = client.get(f"{BASE}/platform/courses/OS101-01/replays", headers=_headers(token))
        assert resp.status_code == 200

        resp = client.post(f"{BASE}/platform/courses/OS101-01/replays/9001/parse", headers=_headers(token))
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        resp = client.get(f"{BASE}/tasks/{task_id}", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"

        resp = client.get(f"{BASE}/lectures/{lecture.id}/overview", headers=_headers(token))
        assert resp.status_code == 200
        overview = resp.json()
        assert overview["transcript_meta"]["total"] >= 2
        assert len(overview["keypoints"]) >= 1
        assert overview["summary"] is not None
        assert overview["mindmap"] is not None

        resp = client.get(f"{BASE}/lectures/{lecture.id}/transcripts", headers=_headers(token))
        assert resp.status_code == 200
        transcripts = resp.json()
        assert len(transcripts) >= 2
        assert transcripts[0]["text"] == "今天讲操作系统进程管理"

        resp = client.get(f"{BASE}/lectures/{lecture.id}/keypoints", headers=_headers(token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        resp = client.get(f"{BASE}/lectures/{lecture.id}/summary", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["overview"] == "本讲介绍进程管理"

        resp = client.get(f"{BASE}/lectures/{lecture.id}/mindmap", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["root_topic"] == "进程管理"

        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        assert any(c["id"] == course.id for c in resp.json())


# ============================================================================ #
# E2E-02：失败与恢复链路
# ============================================================================ #

class TestE2E02FailureAndRecovery:
    """E2E-02 失败与恢复链路：失效地址→失败原因→重试→恢复成功。"""

    def test_failure_then_retry_recovery(self, client, db, monkeypatch, engine):
        _enable_ai(monkeypatch)
        _patch_session_local(monkeypatch, engine)

        teacher = create_user(db, "teacher1", "pw123456", role="teacher", display_name="教师")

        course = Course(title="数据结构", video_url="http://broken/v.m3u8", source="manual",
                        teacher_name="李老师")
        db.add(course)
        db.commit()
        db.refresh(course)

        token = _login(client, "teacher1", "pw123456")

        _stub_worker_fail(monkeypatch, "IO_ERROR", "音频提取失败：ffmpeg 返回码 1")

        resp = client.post(f"{BASE}/courses/{course.id}/parse", headers=_headers(token))
        assert resp.status_code == 201
        original_task_id = resp.json()["id"]

        resp = client.get(f"{BASE}/tasks/{original_task_id}", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "IO_ERROR"
        assert "音频提取失败" in body["error_message"]

        _stub_worker_success(monkeypatch)

        resp = client.post(f"{BASE}/tasks/{original_task_id}/retry", headers=_headers(token))
        assert resp.status_code == 201
        new_task = resp.json()
        assert new_task["status"] == "queued"
        assert new_task["retry_count"] == 1
        assert new_task["parent_task_id"] == original_task_id

        resp = client.get(f"{BASE}/tasks/{new_task['id']}", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"

        resp = client.get(f"{BASE}/tasks/{original_task_id}", headers=_headers(token))
        assert resp.json()["status"] == "failed"


# ============================================================================ #
# E2E-03：越权拦截链路
# ============================================================================ #

class TestE2E03UnauthorizedAccess:
    """E2E-03 越权拦截链路：student_b 登录→课程A接口→全部 403/404。"""

    def test_unauthorized_access_blocked(self, client, db, monkeypatch, engine):
        _enable_ai(monkeypatch)
        _patch_session_local(monkeypatch, engine)
        _stub_worker_success(monkeypatch)

        teacher = create_user(db, "teacher1", "pw123456", role="teacher", display_name="教师")
        student_a = create_user(db, "student_a", "pw123456", role="student", display_name="学生A")
        student_b = create_user(db, "student_b", "pw123456", role="student", display_name="学生B")

        course_a = Course(title="课程A", video_url="http://x/a.m3u8", source="manual",
                          course_num="CA101", fz_id="20260101", teacher_name="王老师")
        db.add(course_a)
        db.commit()
        db.refresh(course_a)

        lecture_a = Lecture(course_id=course_a.id, platform_replay_id="9001",
                            teach_time_str="2026-03-01", video_url="http://x/a.m3u8")
        db.add(lecture_a)
        db.commit()
        db.refresh(lecture_a)

        authorization_service.grant(db, course_a.id, student_a.id, teacher.id, valid_until=None)

        token_b = _login(client, "student_b", "pw123456")

        resp = client.get(f"{BASE}/courses", headers=_headers(token_b))
        assert resp.status_code == 200
        assert not any(c["id"] == course_a.id for c in resp.json())

        resp = client.get(f"{BASE}/courses/CA101-01", headers=_headers(token_b))
        assert resp.status_code in (403, 404)

        resp = client.post(f"{BASE}/courses/{course_a.id}/parse", headers=_headers(token_b))
        assert resp.status_code in (403, 404)

        resp = client.get(f"{BASE}/lectures/{lecture_a.id}/overview", headers=_headers(token_b))
        assert resp.status_code in (403, 404)

        resp = client.get(f"{BASE}/lectures/{lecture_a.id}/transcripts", headers=_headers(token_b))
        assert resp.status_code in (403, 404)

        resp = client.get(f"{BASE}/lectures/{lecture_a.id}/keypoints", headers=_headers(token_b))
        assert resp.status_code in (403, 404)

        token_a = _login(client, "student_a", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token_a))
        assert resp.status_code == 200
        assert any(c["id"] == course_a.id for c in resp.json())

        resp = client.get(f"{BASE}/courses/CA101-01", headers=_headers(token_a))
        assert resp.status_code == 200