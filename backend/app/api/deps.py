"""依赖注入：当前用户、课程级权限校验。

对应 docs/05-risk-handling.md 权限鉴权拦截；NFR-07。
"""
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.db.models import CourseAuthorization, User
from app.db.session import get_db


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("缺少认证信息")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise AuthError("无效或过期的 Token") from exc
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise AuthError("用户不存在或已禁用")
    return user


def require_role(*roles: str):
    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError("角色权限不足")
        return user
    return _checker


def require_course_access(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if user.role in ("teacher", "admin"):
        return user
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = select(CourseAuthorization).where(
        CourseAuthorization.course_id == course_id,
        CourseAuthorization.user_id == user.id,
        CourseAuthorization.is_revoked == False,  # noqa: E712
        CourseAuthorization.valid_from <= now,
    )
    auth = db.execute(stmt).scalar_one_or_none()
    if auth is None:
        raise ForbiddenError("无权访问该课程")
    if auth.valid_until is not None and auth.valid_until < now:
        raise ForbiddenError("课程授权已过期")
    return user