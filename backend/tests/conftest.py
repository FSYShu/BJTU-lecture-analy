"""pytest 公共夹具。

FastAPI 相关依赖在 ``client`` 夹具内部延迟导入：流水线单测
（``tests/test_pipeline``）因此只需要 pydantic / sqlalchemy / httpx 等轻量依赖。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import *  # noqa: F401,F403


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session():
    """内存 SQLite 会话，供流水线各步骤的单测直接读写 ORM。"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()