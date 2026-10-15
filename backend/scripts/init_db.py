"""初始化 SQLite 数据库表。

用法: uv run python scripts/init_db.py
"""
from pathlib import Path

from app.config import settings
from app.db.init_db import init_db
from app.db.session import engine


def main() -> None:
    Path(settings.storage_root, "db").mkdir(parents=True, exist_ok=True)
    init_db()
    print(f"数据库已初始化: {engine.url}")


if __name__ == "__main__":
    main()