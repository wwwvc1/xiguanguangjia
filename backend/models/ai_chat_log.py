"""AI 聊天日志 Pydantic 模型"""
from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime


class AIChatLogResponse(BaseModel):
    id: int
    user_id: int
    session_id: str
    role: str
    content: str
    tool_calls: Optional[Any] = None
    model: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIChatSessionItem(BaseModel):
    session_id: str
    first_user_message: str
    message_count: int
    last_active: datetime
    model: Optional[str] = None


class AIChatSessionListResponse(BaseModel):
    total: int
    items: list[AIChatSessionItem]
