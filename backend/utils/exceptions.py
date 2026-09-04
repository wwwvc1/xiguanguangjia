from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import traceback

async def validation_exception_handler(request: Request, exc: ValidationError):
    """Pydantic 校验失败"""
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "参数校验失败", "data": exc.errors()}
    )

async def global_exception_handler(request: Request, exc: Exception):
    """未预期的异常：打印 traceback 到日志(开发期),不暴露内部细节给前端"""
    print(f"[GlobalException] {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": None}
    )