from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UserResponse(BaseModel):
    id: int
    nickname: str | None = None
    avatar: str | None = None
    created_at: datetime
    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    """PUT /api/user/profile 请求体 — 任意字段可单独更新"""
    nickname: Optional[str] = Field(default=None, max_length=64, description="昵称,1-64 字")
    avatar: Optional[str] = Field(default=None, description="头像 base64(可带 data:image/xxx;base64, 前缀)")
