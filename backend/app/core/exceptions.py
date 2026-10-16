"""业务异常定义与全局异常处理器。

对应 docs/05-risk-handling.md：失败隔离、权限拦截、API 异常降级。
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    """业务异常基类。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthError(AppError):
    def __init__(self, message: str = "未授权") -> None:
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "无权访问该课程") -> None:
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


class TaskFailedError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=422)


class ExternalAPIError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=502)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("[api] 未处理异常: {}", exc)
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
        )