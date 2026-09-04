from pydantic import BaseModel
from datetime import datetime

class UserResponse(BaseModel):
    id: int
    nickname: str | None = None
    avatar: str | None = None
    created_at: datetime
    class Config:
        from_attributes = True
