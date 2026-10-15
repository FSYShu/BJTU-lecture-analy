"""认证服务。P0-09。"""
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import User


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(db: Session, username: str, password: str, role: str, display_name: str | None = None) -> User:
    user = User(username=username, hashed_password=hash_password(password), role=role, display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user