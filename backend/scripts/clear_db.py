"""清除 SQLite 数据库。

用法:
    uv run python scripts/clear_db.py             # 删除数据库文件并重新初始化
    uv run python scripts/clear_db.py --data-only  # 只清空数据，保留表结构
"""
import argparse
from pathlib import Path

from sqlalchemy import inspect, text

from app.config import settings
from app.db.base import Base
from app.db.init_db import init_db
from app.db.models import *  # noqa: F401,F403
from app.db.session import engine


def clear_data_only() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if not tables:
        print("数据库中没有表，无需清除。")
        return
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table in tables:
            conn.execute(text(f"DELETE FROM {table}"))
            print(f"  已清空: {table}")
        conn.execute(text("PRAGMA foreign_keys = ON"))
    print(f"已清空 {len(tables)} 张表的数据（表结构保留）。")


def drop_and_rebuild() -> None:
    db_path = Path(settings.storage_root, "db", "app.db")
    wal_path = db_path.with_suffix(".db-wal")
    shm_path = db_path.with_suffix(".db-shm")

    engine.dispose()

    for p in [db_path, wal_path, shm_path]:
        if p.exists():
            p.unlink()
            print(f"  已删除: {p}")

    Path(settings.storage_root, "db").mkdir(parents=True, exist_ok=True)
    init_db()
    print(f"数据库已重建: {engine.url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="清除 SQLite 数据库")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="只清空数据，保留表结构（不删除文件）",
    )
    args = parser.parse_args()

    if args.data_only:
        print("模式: 清空数据（保留表结构）")
        clear_data_only()
    else:
        print("模式: 删除文件并重建数据库")
        drop_and_rebuild()


if __name__ == "__main__":
    main()