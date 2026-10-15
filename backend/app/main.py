"""FastAPI 应用入口。挂载路由、CORS、异常处理、日志初始化。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("启动 {} (env={})", settings.app_name, settings.app_env)
    yield
    logger.info("关闭 {}", settings.app_name)


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

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")