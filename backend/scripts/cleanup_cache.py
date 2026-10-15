"""手动触发缓存清理。

用法: uv run python scripts/cleanup_cache.py
"""
from app.core.cleanup import run_scheduled_cleanup


def main() -> None:
    result = run_scheduled_cleanup()
    print(f"清理完成: {result}")


if __name__ == "__main__":
    main()