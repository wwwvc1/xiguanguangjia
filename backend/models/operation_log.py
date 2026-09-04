"""操作日志 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class OperationLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    details: Optional[Any] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class OperationLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[OperationLogResponse]


class OperationLogStatsItem(BaseModel):
    action: str
    count: int
