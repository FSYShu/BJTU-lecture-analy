"""FastAPI 应用入口。挂载路由、CORS、压缩、异常处理、日志初始化。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("[app] 启动 {} (env={})", settings.app_name, settings.app_env)

    from app.db.init_db import init_db
    from app.db.models import ParseTask
    from app.db.session import SessionLocal

    init_db()

    db = SessionLocal()
    active_statuses = ["queued", "downloading", "extracting_audio", "asr_running", "llm_running", "persisting"]
    stale = db.query(ParseTask).filter(ParseTask.status.in_(active_statuses)).all()
    for t in stale:
        t.status = "failed"
        t.error_code = "INTERRUPTED"
        t.error_message = "后端重启，任务被中断"
    if stale:
        db.commit()
    logger.info("[app] 清理 {} 个未完成的解析任务", len(stale))
    db.close()

    yield
    logger.info("[app] 关闭 {}", settings.app_name)


app = FastAPI(
    title="交大课录智析 API",
    description="北京交通大学课程回放AI解析平台",
    version="0.1.0",
    docs_url="/docs" if not settings.is_prod else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# >1KB 的 JSON 响应才压缩：转写 300KB → ~60KB，重点/总结/导图同样受益；
# 小于 1KB 的响应压缩收益抵不过 CPU 开销。Starlette 的 GZipMiddleware 本身已
# 排除 text/event-stream（DEFAULT_EXCLUDED_CONTENT_TYPES），后续新增 SSE 端点
# （docs/11 优化 4）不会被缓冲卡住。
app.add_middleware(GZipMiddleware, minimum_size=1024)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")