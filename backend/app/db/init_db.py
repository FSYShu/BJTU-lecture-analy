"""建表脚本入口（被 scripts/init_db.py 复用）。

``create_all`` 只建缺失的表，不会给已存在的表补列；因此这里对 MVP 期间新增的列
做一次幂等的轻量迁移（SQLite ``ALTER TABLE ... ADD COLUMN``）。
"""
from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.models import *  # noqa: F401,F403  确保所有模型被注册
from app.db.session import engine

# 表名 -> {列名: DDL 类型}
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "courses": {
        "platform_replay_id": "VARCHAR(64)",
        "course_num": "VARCHAR(32)",
        "fz_id": "VARCHAR(32)",
        "platform_c_id": "INTEGER",
    },
    "users": {
        "platform_user_id": "INTEGER",
        "platform_cookies": "VARCHAR(4096)",
        "cookies_updated_at": "DATETIME",
        "ve_user_id": "INTEGER",
    },
    "parse_tasks": {
        "lecture_id": "INTEGER",
    },
    "transcripts": {
        "lecture_id": "INTEGER",
    },
    "keypoints": {
        "lecture_id": "INTEGER",
    },
    "summaries": {
        "lecture_id": "INTEGER",
    },
    "mindmaps": {
        "lecture_id": "INTEGER",
    },
}


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_missing_columns()


def _migrate_missing_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl_type in columns.items():
            if name in present:
                continue
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
