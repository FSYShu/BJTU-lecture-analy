"""核心功能模块黑盒测试套件。

以 HTTP 接口为边界做黑盒测试，覆盖：
- 认证模块（auth）
- 课程模块（courses）
- 解析任务模块（tasks）
- 解析结果查询模块（lectures / 课程级结果）
- 授权管理模块（admin）
- 平台对接模块（platform，外部 SSO/VE 依赖在边界打桩）

每个用例 docstring 标注用例编号（TC-XXX-nn），与测试报告一一对应。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as jose_jwt
from sqlalchemy.orm import Session

from app.api.v1 import courses as courses_api
from app.api.v1 import platform as platform_api
from app.api.v1 import tasks as tasks_api
from app.config import settings
from app.core.exceptions import ExternalAPIError
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


def _teacher(db: Session, username: str = "teacher1") -> User:
    return create_user(db, username, "pw123456", role="teacher", display_name="教师")


def _student(db: Session, username: str = "student1") -> User:
    return create_user(db, username, "pw123456", role="student", display_name="学生")


def _make_course(db: Session, **over) -> Course:
    data = {
        "title": "操作系统",
        "video_url": "http://example.com/v.mp4",
        "source": "manual",
        "teacher_name": "王老师",
    }
    data.update(over)
    course = Course(**data)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _platform_course(db: Session, **over) -> Course:
    data = {
        "title": "数据结构",
        "video_url": "",
        "source": "platform",
        "platform_course_id": "2026001",
        "course_num": "M1001",
        "fz_id": "20260101",
        "platform_c_id": 8801,
    }
    data.update(over)
    course = Course(**data)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _make_lecture(db: Session, course_id: int, replay_id: str = "9001", **over) -> Lecture:
    data = {"course_id": course_id, "platform_replay_id": replay_id}
    data.update(over)
    lecture = Lecture(**data)
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return lecture


def _make_task(db: Session, course_id: int, status: str = "queued", **over) -> ParseTask:
    data = {"course_id": course_id, "status": status}
    data.update(over)
    task = ParseTask(**data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _grant(db: Session, course_id: int, user_id: int, granted_by: int, valid_until=None):
    return authorization_service.grant(db, course_id, user_id, granted_by, valid_until)


def _stub_worker(monkeypatch) -> None:
    monkeypatch.setattr(courses_api, "parse_worker_run", lambda task_id: None)
    monkeypatch.setattr(tasks_api, "parse_worker_run", lambda task_id: None)
    monkeypatch.setattr(platform_api, "parse_worker_run", lambda task_id: None)


def _enable_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "siliconflow_api_key", "sk-test")
    monkeypatch.setattr(settings, "platform_base_url", "http://platform.test")


class TestHealth:
    def test_health(self, client):
        """TC-H-01 健康检查返回 ok。"""
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_login_success(self, client, db):
        """TC-A-01 有效用户名+密码登录成功，返回 token 与用户信息。"""
        _teacher(db)
        resp = client.post(f"{BASE}/auth/login", json={"username": "teacher1", "password": "pw123456"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["role"] == "teacher"

    def test_login_wrong_password(self, client, db):
        """TC-A-02 密码错误返回 401。"""
        _teacher(db)
        resp = client.post(f"{BASE}/auth/login", json={"username": "teacher1", "password": "bad"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"

    def test_login_unknown_user(self, client):
        """TC-A-03 用户不存在返回 401，且提示与密码错误一致（防枚举）。"""
        resp = client.post(f"{BASE}/auth/login", json={"username": "ghost", "password": "x"})
        assert resp.status_code == 401
        assert "用户名或密码错误" in resp.json()["message"]

    def test_login_missing_password(self, client):
        """TC-A-04 缺少 password 字段返回 422。"""
        resp = client.post(f"{BASE}/auth/login", json={"username": "teacher1"})
        assert resp.status_code == 422

    def test_login_missing_username(self, client):
        """TC-A-05 缺少 username 字段返回 422。"""
        resp = client.post(f"{BASE}/auth/login", json={"password": "x"})
        assert resp.status_code == 422

    def test_login_empty_credentials(self, client):
        """TC-A-06 空字符串用户名/密码（边界：长度 0）返回 401。"""
        resp = client.post(f"{BASE}/auth/login", json={"username": "", "password": ""})
        assert resp.status_code == 401

    def test_login_empty_body(self, client):
        """TC-A-07 空请求体返回 422。"""
        resp = client.post(f"{BASE}/auth/login", json={})
        assert resp.status_code == 422

    def test_me_valid_token(self, client, db):
        """TC-A-08 有效 token 访问 /me 返回当前用户。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/auth/me", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "teacher1"

    def test_me_no_token(self, client):
        """TC-A-09 无 Authorization 头返回 401。"""
        resp = client.get(f"{BASE}/auth/me")
        assert resp.status_code == 401

    def test_me_non_bearer_scheme(self, client):
        """TC-A-10 非 Bearer 前缀的 Authorization 返回 401。"""
        resp = client.get(f"{BASE}/auth/me", headers={"Authorization": "Token abc"})
        assert resp.status_code == 401

    def test_me_tampered_token(self, client, db):
        """TC-A-11 篡改签名后的 token 返回 401。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/auth/me", headers=_headers(token[:-2] + "xx"))
        assert resp.status_code == 401

    def test_me_expired_token(self, client, db):
        """TC-A-12 过期 token（exp = now-1s，边界）返回 401。"""
        user = _teacher(db)
        token = jose_jwt.encode(
            {
                "sub": str(user.id),
                "role": user.role,
                "iat": datetime.now(timezone.utc) - timedelta(hours=9),
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        resp = client.get(f"{BASE}/auth/me", headers=_headers(token))
        assert resp.status_code == 401

    def test_me_disabled_user(self, client, db):
        """TC-A-13 已禁用用户持有效 token 仍返回 401。"""
        user = _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        user.is_active = False
        db.commit()
        resp = client.get(f"{BASE}/auth/me", headers=_headers(token))
        assert resp.status_code == 401

    def test_me_token_of_deleted_user(self, client, db):
        """TC-A-14 token sub 指向不存在用户返回 401。"""
        _teacher(db)
        token = jose_jwt.encode(
            {"sub": "99999", "role": "teacher", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        resp = client.get(f"{BASE}/auth/me", headers=_headers(token))
        assert resp.status_code == 401

    def test_me_empty_bearer_token(self, client):
        """TC-A-15 'Bearer ' 后为空 token（边界）返回 401。"""
        resp = client.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401


class TestCourses:
    def test_list_courses_teacher_sees_all(self, client, db):
        """TC-C-01 教师角色可列出全部课程。"""
        _teacher(db)
        _make_course(db)
        _make_course(db, title="高等数学")
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_courses_student_without_grant(self, client, db):
        """TC-C-02 学生无授权时课程列表为空。"""
        _student(db)
        _make_course(db)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_courses_student_with_grant(self, client, db):
        """TC-C-03 学生有有效授权时可看到对应课程。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        _grant(db, course.id, student.id, teacher.id)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        assert [c["id"] for c in resp.json()] == [course.id]

    def test_list_courses_student_revoked_grant(self, client, db):
        """TC-C-04 授权被撤销后学生不再看到课程。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        auth = _grant(db, course.id, student.id, teacher.id)
        authorization_service.revoke(db, auth.id)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.json() == []

    def test_list_courses_student_expired_grant(self, client, db):
        """TC-C-05 授权已过期（valid_until < now）学生不应再看到课程。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        _grant(db, course.id, student.id, teacher.id, valid_until=datetime.now(timezone.utc) - timedelta(seconds=1))
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_courses_unauthenticated(self, client):
        """TC-C-06 未登录访问课程列表返回 401。"""
        resp = client.get(f"{BASE}/courses")
        assert resp.status_code == 401

    def test_get_course_by_valid_key(self, client, db):
        """TC-C-07 合法 course_key（课程号-课序号后两位）查询成功。"""
        _teacher(db)
        course = _platform_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/courses/M1001-01", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == course.id

    def test_get_course_key_not_found(self, client, db):
        """TC-C-08 不存在的 course_key 返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/courses/M9999-99", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_course_key_without_dash(self, client, db):
        """TC-C-09 course_key 无连字符（格式边界）返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/courses/M1001", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_course_manual_has_no_key(self, client, db):
        """TC-C-10 手工导入课程无 course_num/fz_id，按 key 查询返回 404。"""
        _teacher(db)
        _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/courses/M1001-01", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_course_student_unauthorized(self, client, db):
        """TC-C-11 未授权学生查询课程详情返回 404（不泄露存在性）。"""
        _teacher(db)
        _student(db)
        _platform_course(db)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/M1001-01", headers=_headers(token))
        assert resp.status_code == 404

    def test_import_course_success(self, client, db):
        """TC-C-12 教师手工导入课程成功，source=manual。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(
            f"{BASE}/courses/import",
            json={"title": "计算机网络", "video_url": "http://example.com/cn.mp4", "duration_sec": 3600},
            headers=_headers(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source"] == "manual"
        assert body["duration_sec"] == 3600

    def test_import_course_missing_title(self, client, db):
        """TC-C-13 缺少必填 title 返回 422。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/import", json={"video_url": "http://x/v.mp4"}, headers=_headers(token))
        assert resp.status_code == 422

    def test_import_course_missing_video_url(self, client, db):
        """TC-C-14 缺少必填 video_url 返回 422。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/import", json={"title": "x"}, headers=_headers(token))
        assert resp.status_code == 422

    def test_import_course_empty_title(self, client, db):
        """TC-C-15 空字符串 title（边界：长度 0）应返回 422。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(
            f"{BASE}/courses/import", json={"title": "", "video_url": "http://x/v.mp4"}, headers=_headers(token)
        )
        assert resp.status_code == 422

    def test_import_course_negative_duration(self, client, db):
        """TC-C-16 duration_sec 为负数（边界：-1）应返回 422。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(
            f"{BASE}/courses/import",
            json={"title": "x", "video_url": "http://x/v.mp4", "duration_sec": -1},
            headers=_headers(token),
        )
        assert resp.status_code == 422

    def test_import_course_unauthenticated(self, client):
        """TC-C-17 未登录导入课程返回 401。"""
        resp = client.post(f"{BASE}/courses/import", json={"title": "x", "video_url": "http://x/v.mp4"})
        assert resp.status_code == 401

    def test_parse_missing_api_key(self, client, db, monkeypatch):
        """TC-C-18 未配置 SILICONFLOW_API_KEY 时发起解析返回 400。"""
        monkeypatch.setattr(settings, "siliconflow_api_key", "")
        monkeypatch.setattr(settings, "platform_base_url", "http://platform.test")
        _stub_worker(monkeypatch)
        _teacher(db)
        _platform_course(db, video_url="http://x/v.mp4")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/M1001-01/parse", headers=_headers(token))
        assert resp.status_code == 400
        assert resp.json()["code"] == "AI_CREDENTIALS_MISSING"

    def test_parse_missing_video_url(self, client, db, monkeypatch):
        """TC-C-19 课程 video_url 为空串时发起解析返回 400 VIDEO_URL_MISSING。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        course = _platform_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/M1001-01/parse", headers=_headers(token))
        assert resp.status_code == 400
        assert resp.json()["code"] == "VIDEO_URL_MISSING"

    def test_parse_success(self, client, db, monkeypatch):
        """TC-C-20 前置条件满足时发起解析成功，任务为 queued。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        _platform_course(db, video_url="http://x/v.mp4")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/M1001-01/parse", headers=_headers(token))
        assert resp.status_code == 201
        assert resp.json()["status"] == "queued"

    def test_parse_course_not_found(self, client, db, monkeypatch):
        """TC-C-21 对不存在课程发起解析返回 404。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/M9999-99/parse", headers=_headers(token))
        assert resp.status_code == 404

    def test_parse_student_unauthorized_course(self, client, db, monkeypatch):
        """TC-C-22 未授权学生对课程发起解析应被拒绝（403/404）。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        _student(db)
        _platform_course(db, video_url="http://x/v.mp4")
        token = _login(client, "student1", "pw123456")
        resp = client.post(f"{BASE}/courses/M1001-01/parse", headers=_headers(token))
        assert resp.status_code in (403, 404)


class TestTasks:
    def test_get_task_success(self, client, db):
        """TC-T-01 查询存在的任务返回 200 与任务详情。"""
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="asr_running", progress=45)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/{task.id}", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "asr_running"
        assert resp.json()["progress"] == 45

    def test_get_task_not_found(self, client, db):
        """TC-T-02 任务不存在返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/99999", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_task_id_zero(self, client, db):
        """TC-T-03 task_id=0（边界）返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/0", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_task_id_non_numeric(self, client, db):
        """TC-T-04 task_id 非数字返回 422。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/abc", headers=_headers(token))
        assert resp.status_code == 422

    def test_latest_task_by_course(self, client, db):
        """TC-T-05 按 course_id 查询返回最新一条任务。"""
        _teacher(db)
        course = _make_course(db)
        _make_task(db, course.id, status="failed")
        t2 = _make_task(db, course.id, status="succeeded")
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/latest", params={"course_id": course.id}, headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == t2.id

    def test_latest_task_none(self, client, db):
        """TC-T-06 课程无任务时查询最新任务返回 404。"""
        _teacher(db)
        course = _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/latest", params={"course_id": course.id}, headers=_headers(token))
        assert resp.status_code == 404

    def test_latest_task_no_params(self, client, db):
        """TC-T-07 不传 lecture_id/course_id（边界）返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/latest", headers=_headers(token))
        assert resp.status_code == 404

    def test_retry_failed_task(self, client, db, monkeypatch):
        """TC-T-08 重试失败任务成功：retry_count+1、指向父任务、继承缓存路径。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="failed", video_cache_path="/v.mp4", audio_cache_path="/a.wav")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/retry", headers=_headers(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "queued"
        assert body["retry_count"] == 1
        new_task = db.get(ParseTask, body["id"])
        assert new_task.parent_task_id == task.id
        assert new_task.video_cache_path == "/v.mp4"
        assert new_task.audio_cache_path == "/a.wav"

    def test_retry_succeeded_task(self, client, db, monkeypatch):
        """TC-T-09 重试已成功任务返回 422 TASK_NOT_RETRYABLE。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="succeeded")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/retry", headers=_headers(token))
        assert resp.status_code == 422
        assert resp.json()["code"] == "TASK_NOT_RETRYABLE"

    def test_retry_queued_task(self, client, db, monkeypatch):
        """TC-T-10 重试排队中任务返回 422。"""
        _enable_ai(monkeypatch)
        _stub_worker(monkeypatch)
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="queued")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/retry", headers=_headers(token))
        assert resp.status_code == 422

    def test_retry_not_found(self, client, db):
        """TC-T-11 重试不存在任务返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/99999/retry", headers=_headers(token))
        assert resp.status_code == 404

    def test_cancel_queued_task(self, client, db):
        """TC-T-12 取消排队中任务：状态变 failed 且 error_code=CANCELLED。"""
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="queued")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/cancel", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "CANCELLED"

    def test_cancel_succeeded_task(self, client, db):
        """TC-T-13 取消已成功任务：状态保持不变（幂等）。"""
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="succeeded")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/cancel", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"

    def test_cancel_failed_task_keeps_error(self, client, db):
        """TC-T-14 取消已失败任务：保留原 error_code（幂等）。"""
        _teacher(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="failed", error_code="ASR_FAIL")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/cancel", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["error_code"] == "ASR_FAIL"

    def test_cancel_not_found(self, client, db):
        """TC-T-15 取消不存在任务返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/tasks/99999/cancel", headers=_headers(token))
        assert resp.status_code == 404

    def test_get_task_student_cross_course(self, client, db):
        """TC-T-16 学生读取未授权课程的任务应被拒绝（403/404）。"""
        _teacher(db)
        _student(db)
        course = _make_course(db)
        task = _make_task(db, course.id)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/tasks/{task.id}", headers=_headers(token))
        assert resp.status_code in (403, 404)

    def test_cancel_student_cross_course(self, client, db):
        """TC-T-17 学生取消未授权课程的任务应被拒绝（403/404）。"""
        _teacher(db)
        _student(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="queued")
        token = _login(client, "student1", "pw123456")
        resp = client.post(f"{BASE}/tasks/{task.id}/cancel", headers=_headers(token))
        assert resp.status_code in (403, 404)
        db.refresh(task)
        assert task.status == "queued"

    def test_stream_task_not_found(self, client, db):
        """TC-T-18 SSE 订阅不存在任务返回 404（而非 200+error 帧）。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/tasks/99999/stream", headers=_headers(token))
        assert resp.status_code == 404


class TestResults:
    def _seed_results(self, db, course_id: int, lecture_id: int, task_id: int):
        db.add_all([
            Transcript(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=0,
                       text="今天我们讲操作系统", start_sec=0.0, end_sec=3.5),
            Transcript(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=1,
                       text="第一章进程管理", start_sec=3.5, end_sec=8.0),
            Keypoint(task_id=task_id, course_id=course_id, lecture_id=lecture_id, seq_index=0,
                     title="进程与线程", category="concept", timestamp_sec=120.0),
            Summary(task_id=task_id, course_id=course_id, lecture_id=lecture_id, overview="本讲概述"),
            Mindmap(task_id=task_id, course_id=course_id, lecture_id=lecture_id,
                    root_topic="操作系统", nodes="[]"),
        ])
        db.commit()

    def test_summary_not_generated(self, client, db):
        """TC-R-01 总结未生成时返回 404 与可读提示。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/summary", headers=_headers(token))
        assert resp.status_code == 404

    def test_mindmap_not_generated(self, client, db):
        """TC-R-02 思维导图未生成时返回 404。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/mindmap", headers=_headers(token))
        assert resp.status_code == 404

    def test_transcripts_empty(self, client, db):
        """TC-R-03 无字幕时返回 200 空数组（而非 404）。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/transcripts", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_keypoints_empty(self, client, db):
        """TC-R-04 无重点时返回 200 空数组。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/keypoints", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lecture_not_found(self, client, db):
        """TC-R-05 回放不存在返回 404 NOT_FOUND。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/99999/summary", headers=_headers(token))
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_lecture_student_forbidden(self, client, db):
        """TC-R-06 未授权学生访问回放结果返回 403。"""
        _teacher(db)
        _student(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/transcripts", headers=_headers(token))
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_course_transcripts_student_forbidden(self, client, db):
        """TC-R-07 未授权学生访问课程级字幕返回 403。"""
        _teacher(db)
        _student(db)
        course = _make_course(db)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/{course.id}/transcripts", headers=_headers(token))
        assert resp.status_code == 403

    def test_overview_empty(self, client, db):
        """TC-R-08 overview 无任何结果时返回 200，字段为 null/空（首屏不报错）。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/overview", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"] is None
        assert body["mindmap"] is None
        assert body["keypoints"] == []
        assert body["transcript_meta"]["total"] == 0

    def test_overview_with_data(self, client, db):
        """TC-R-09 overview 聚合返回字幕元信息/重点/总结/导图/最新任务。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        task = _make_task(db, course.id, status="succeeded", lecture_id=lecture.id)
        self._seed_results(db, course.id, lecture.id, task.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/overview", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["transcript_meta"]["total"] == 2
        assert len(body["keypoints"]) == 1
        assert body["summary"]["overview"] == "本讲概述"
        assert body["mindmap"]["root_topic"] == "操作系统"
        assert body["task"]["status"] == "succeeded"

    def test_summary_generated(self, client, db):
        """TC-R-10 总结已生成时返回 200 与内容。"""
        _teacher(db)
        course = _make_course(db)
        lecture = _make_lecture(db, course.id)
        task = _make_task(db, course.id, status="succeeded", lecture_id=lecture.id)
        self._seed_results(db, course.id, lecture.id, task.id)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/lectures/{lecture.id}/summary", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["overview"] == "本讲概述"


class TestAdmin:
    def test_student_cannot_list_authorizations(self, client, db):
        """TC-M-01 学生访问授权管理返回 403。"""
        _student(db)
        token = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/admin/authorizations", headers=_headers(token))
        assert resp.status_code == 403

    def test_unauthenticated_admin(self, client):
        """TC-M-02 未登录访问授权管理返回 401。"""
        resp = client.get(f"{BASE}/admin/authorizations")
        assert resp.status_code == 401

    def test_grant_success(self, client, db):
        """TC-M-03 教师授权学生课程返回 201。"""
        _teacher(db)
        student = _student(db)
        course = _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(
            f"{BASE}/admin/authorizations",
            json={"course_id": course.id, "user_id": student.id},
            headers=_headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["course_id"] == course.id

    def test_grant_then_student_access(self, client, db):
        """TC-M-04 授权后学生可访问课程字幕资源。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        task = _make_task(db, course.id, status="succeeded")
        db.add(Transcript(task_id=task.id, course_id=course.id, seq_index=0,
                          text="内容", start_sec=0.0, end_sec=1.0))
        db.commit()
        token = _login(client, "teacher1", "pw123456")
        client.post(
            f"{BASE}/admin/authorizations",
            json={"course_id": course.id, "user_id": student.id},
            headers=_headers(token),
        )
        stoken = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/{course.id}/transcripts", headers=_headers(stoken))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_revoke_then_student_lost_access(self, client, db):
        """TC-M-05 撤销授权后学生立即失去访问权限。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        grant_resp = client.post(
            f"{BASE}/admin/authorizations",
            json={"course_id": course.id, "user_id": student.id},
            headers=_headers(token),
        )
        auth_id = grant_resp.json()["id"]
        client.post(f"{BASE}/admin/authorizations/{auth_id}/revoke", headers=_headers(token))
        stoken = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/{course.id}/transcripts", headers=_headers(stoken))
        assert resp.status_code == 403

    def test_revoke_not_found(self, client, db):
        """TC-M-06 撤销不存在的授权返回 404 AUTH_NOT_FOUND。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/admin/authorizations/99999/revoke", headers=_headers(token))
        assert resp.status_code == 404
        assert resp.json()["code"] == "AUTH_NOT_FOUND"

    def test_failed_tasks_list(self, client, db):
        """TC-M-07 教师可查看失败任务列表。"""
        _teacher(db)
        course = _make_course(db)
        _make_task(db, course.id, status="failed", error_code="ASR_FAIL", error_message="识别失败")
        _make_task(db, course.id, status="succeeded")
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/admin/tasks/failed", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["error_code"] == "ASR_FAIL"

    def test_grant_future_valid_until(self, client, db):
        """TC-M-08 授权有效期在未来：学生可访问。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        client.post(
            f"{BASE}/admin/authorizations",
            json={
                "course_id": course.id,
                "user_id": student.id,
                "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
            headers=_headers(token),
        )
        stoken = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/{course.id}/transcripts", headers=_headers(stoken))
        assert resp.status_code == 200

    def test_grant_expired_valid_until(self, client, db):
        """TC-M-09 授权有效期已过：学生访问应返回 403 课程授权已过期。"""
        teacher = _teacher(db)
        student = _student(db)
        course = _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        client.post(
            f"{BASE}/admin/authorizations",
            json={
                "course_id": course.id,
                "user_id": student.id,
                "valid_until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            },
            headers=_headers(token),
        )
        stoken = _login(client, "student1", "pw123456")
        resp = client.get(f"{BASE}/courses/{course.id}/transcripts", headers=_headers(stoken))
        assert resp.status_code == 403


class TestPlatform:
    def test_sso_login_new_user(self, client, db, monkeypatch):
        """TC-P-01 SSO 登录新用户：自动建号（teacher）并签发 token。"""
        async def fake_sso(username, password):
            return ([{"name": "SESSION", "value": "abc"}], 23280001)

        monkeypatch.setattr(platform_integration, "sso_login", fake_sso)
        resp = client.post(f"{BASE}/platform/sso-login", json={"username": "23280001", "password": "x"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == 23280001
        assert body["user"]["role"] == "teacher"
        assert db.query(User).filter(User.username == "23280001").count() == 1

    def test_sso_login_existing_user_no_duplicate(self, client, db, monkeypatch):
        """TC-P-02 SSO 登录老用户：不重复建号，cookies 更新。"""
        async def fake_sso(username, password):
            return ([{"name": "SESSION", "value": "new"}], 23280001)

        monkeypatch.setattr(platform_integration, "sso_login", fake_sso)
        client.post(f"{BASE}/platform/sso-login", json={"username": "23280001", "password": "x"})
        client.post(f"{BASE}/platform/sso-login", json={"username": "23280001", "password": "x"})
        users = db.query(User).filter(User.username == "23280001").all()
        assert len(users) == 1
        assert json.loads(users[0].platform_cookies)[0]["value"] == "new"

    def test_sso_login_platform_failure(self, client, monkeypatch):
        """TC-P-03 SSO 认证失败（密码错误）返回 502 与错误码。"""
        async def fake_sso(username, password):
            raise ExternalAPIError("SSO_LOGIN_FAILED", "统一身份认证失败：用户名或密码错误")

        monkeypatch.setattr(platform_integration, "sso_login", fake_sso)
        resp = client.post(f"{BASE}/platform/sso-login", json={"username": "23280001", "password": "bad"})
        assert resp.status_code == 502
        assert resp.json()["code"] == "SSO_LOGIN_FAILED"

    def test_sso_login_missing_field(self, client):
        """TC-P-04 SSO 登录缺少字段返回 422。"""
        resp = client.post(f"{BASE}/platform/sso-login", json={"username": "23280001"})
        assert resp.status_code == 422

    def test_sync_courses_no_cookies(self, client, db):
        """TC-P-05 未持有平台 cookies 时同步课程返回 400。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/platform/sync-courses", headers=_headers(token))
        assert resp.status_code == 400
        assert resp.json()["code"] == "NO_PLATFORM_COOKIES"

    def test_sync_courses_success(self, client, db, monkeypatch):
        """TC-P-06 同步课程成功：平台课程去重落库并返回 synced/total。"""
        async def fake_sync(cookies):
            return (
                [
                    {"xkhId": "20260101", "courseName": "数据结构", "courseId": "M1001", "cId": 8801},
                    {"xkhId": "20260102", "courseName": "操作系统", "courseId": "M1002", "cId": 8802},
                ],
                cookies,
                7788,
            )

        monkeypatch.setattr(platform_integration, "sync_courses_from_ve", fake_sync)
        user = _teacher(db)
        user.platform_cookies = json.dumps([{"name": "SESSION", "value": "abc"}])
        db.commit()
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/platform/sync-courses", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json() == {"synced": 2, "total": 2}
        assert db.query(Course).count() == 2

    def test_sync_courses_unauthenticated(self, client):
        """TC-P-07 未登录同步课程返回 401。"""
        resp = client.post(f"{BASE}/platform/sync-courses")
        assert resp.status_code == 401

    def test_replays_missing_platform_cid(self, client, db):
        """TC-P-08 课程缺少平台 cId 时拉取回放列表返回 400。"""
        _teacher(db)
        _make_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/platform/courses/any-key/replays", headers=_headers(token))
        assert resp.status_code == 400
        assert resp.json()["code"] == "NO_COURSE_ID"

    def test_replays_no_cookies(self, client, db):
        """TC-P-09 未持有平台 cookies 时拉取回放列表返回 400。"""
        _teacher(db)
        _platform_course(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/platform/courses/M1001-01/replays", headers=_headers(token))
        assert resp.status_code == 400
        assert resp.json()["code"] == "NO_PLATFORM_COOKIES"

    def test_replays_success(self, client, db, monkeypatch):
        """TC-P-10 拉取回放列表成功：落库 Lecture 并标注 has_result/任务状态。"""
        async def fake_replays(cookies, c_id):
            return [
                {"id": 9001, "videoId": "v1", "classRoom": "逸夫101", "teachTimeStr": "周一1-2节"},
                {"id": 9002, "videoId": "v2", "classRoom": "逸夫102", "teachTimeStr": "周三3-4节"},
            ]

        monkeypatch.setattr(platform_integration, "fetch_replays", fake_replays)
        user = _teacher(db)
        user.platform_cookies = json.dumps([{"name": "SESSION", "value": "abc"}])
        course = _platform_course(db)
        lecture = _make_lecture(db, course.id, "9001")
        task = _make_task(db, course.id, status="succeeded", lecture_id=lecture.id)
        db.add(Transcript(task_id=task.id, course_id=course.id, lecture_id=lecture.id,
                          seq_index=0, text="内容", start_sec=0.0, end_sec=1.0))
        db.commit()
        token = _login(client, "teacher1", "pw123456")
        resp = client.get(f"{BASE}/platform/courses/M1001-01/replays", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        first = next(r for r in body if r["id"] == 9001)
        assert first["has_result"] is True
        assert first["latest_task_status"] == "succeeded"
        second = next(r for r in body if r["id"] == 9002)
        assert second["has_result"] is False

    def test_stream_uses_cache(self, client, db, monkeypatch):
        """TC-P-11 已缓存 video_url 时直接返回，不调用浏览器取流。"""
        called = []

        async def fake_stream(cookies, replay_id, ve_user_id, c_id):
            called.append(True)
            return ({"teaStreamHlsUrl": "http://x/new.m3u8"}, 1)

        monkeypatch.setattr(platform_integration, "get_stream_map_via_browser", fake_stream)
        _teacher(db)
        course = _platform_course(db)
        _make_lecture(db, course.id, "9001", video_url="http://x/cached.m3u8")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/platform/courses/M1001-01/replays/9001/stream", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["video_url"] == "http://x/cached.m3u8"
        assert called == []

    def test_stream_force_refresh(self, client, db, monkeypatch):
        """TC-P-12 force=True 时忽略缓存重新取流并落库。"""
        async def fake_stream(cookies, replay_id, ve_user_id, c_id):
            return ({"teaStreamHlsUrl": "http://x/new.m3u8"}, 9999)

        monkeypatch.setattr(platform_integration, "get_stream_map_via_browser", fake_stream)
        user = _teacher(db)
        user.platform_cookies = json.dumps([{"name": "SESSION", "value": "abc"}])
        db.commit()
        course = _platform_course(db)
        _make_lecture(db, course.id, "9001", video_url="http://x/cached.m3u8")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(
            f"{BASE}/platform/courses/M1001-01/replays/9001/stream",
            params={"force": True},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["video_url"] == "http://x/new.m3u8"

    def test_stream_course_not_found(self, client, db):
        """TC-P-13 对不存在课程取流返回 404。"""
        _teacher(db)
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/platform/courses/M9999-99/replays/9001/stream", headers=_headers(token))
        assert resp.status_code == 404

class TestBlackboxFailures:
    """异常路径黑盒测试：TC-B-03/04。"""

    def _patch_session_local(self, monkeypatch, engine):
        """让 SessionLocal 使用测试引擎，使 worker 能看到测试数据。"""
        from sqlalchemy.orm import sessionmaker
        TestingSL = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        import app.db.session as session_mod
        monkeypatch.setattr(session_mod, "SessionLocal", TestingSL)

    def test_audio_extraction_failure_marks_task_failed(self, client, db, monkeypatch, engine):
        """TC-B-03 音频提取异常时任务标记 failed，error_code 为 IO_ERROR。"""
        _enable_ai(monkeypatch)
        self._patch_session_local(monkeypatch, engine)

        def fake_worker(task_id):
            from app.db.session import SessionLocal
            from app.services import task_service
            s = SessionLocal()
            try:
                task_service.mark_failed(s, task_id, "IO_ERROR", "音频提取失败：ffmpeg 返回码 1")
            finally:
                s.close()

        monkeypatch.setattr(courses_api, "parse_worker_run", fake_worker)
        monkeypatch.setattr(tasks_api, "parse_worker_run", fake_worker)
        monkeypatch.setattr(platform_api, "parse_worker_run", fake_worker)

        _teacher(db)
        course = _make_course(db, video_url="http://broken/v.m3u8")
        token = _login(client, "teacher1", "pw123456")
        resp = client.post(f"{BASE}/courses/{course.id}/parse", headers=_headers(token))
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        resp = client.get(f"{BASE}/tasks/{task_id}", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "IO_ERROR"
        assert "音频提取失败" in body["error_message"]

    def test_asr_failure_then_retry_preserves_history(self, client, db, monkeypatch, engine):
        """TC-B-04 ASR 服务异常时任务标记 failed（ASR_ERROR），重试生成新任务且历史保留。"""
        _enable_ai(monkeypatch)
        self._patch_session_local(monkeypatch, engine)

        def fake_worker(task_id):
            from app.db.session import SessionLocal
            from app.services import task_service
            s = SessionLocal()
            try:
                task_service.mark_failed(s, task_id, "ASR_ERROR", "ASR 转写失败：连接超时")
            finally:
                s.close()

        monkeypatch.setattr(courses_api, "parse_worker_run", fake_worker)
        monkeypatch.setattr(tasks_api, "parse_worker_run", fake_worker)
        monkeypatch.setattr(platform_api, "parse_worker_run", fake_worker)

        _teacher(db)
        course = _make_course(db, video_url="http://example.com/v.mp4")
        token = _login(client, "teacher1", "pw123456")

        resp = client.post(f"{BASE}/courses/{course.id}/parse", headers=_headers(token))
        assert resp.status_code == 201
        original_task_id = resp.json()["id"]

        resp = client.get(f"{BASE}/tasks/{original_task_id}", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "ASR_ERROR"
        assert "ASR 转写失败" in body["error_message"]

        resp = client.post(f"{BASE}/tasks/{original_task_id}/retry", headers=_headers(token))
        assert resp.status_code == 201
        new_task = resp.json()
        assert new_task["status"] == "queued"
        assert new_task["retry_count"] == 1
        assert new_task["parent_task_id"] == original_task_id

        resp = client.get(f"{BASE}/tasks/{original_task_id}", headers=_headers(token))
        assert resp.json()["status"] == "failed"

        resp = client.get(f"{BASE}/tasks/{new_task['id']}", headers=_headers(token))
        assert resp.json()["status"] == "failed"
        assert resp.json()["error_code"] == "ASR_ERROR"