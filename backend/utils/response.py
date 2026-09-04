from pydantic import BaseModel

class ApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict | list | None = None

def success(data=None, message="success"):
    return ApiResponse(code=200, message=message, data=data)

def error(message="error", code=400):
    return ApiResponse(code=code, message=message)