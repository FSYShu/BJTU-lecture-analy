"""建表脚本入口（被 scripts/init_db.py 复用）。"""
from app.db.base import Base
from app.db.models import *  # noqa: F401,F403  确保所有模型被注册
from app.db.session import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)