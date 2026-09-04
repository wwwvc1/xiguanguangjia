from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional

class ReminderBase(BaseModel):
    type: str
    time: str
    enabled: bool = True

class ReminderCreate(ReminderBase):
    weekdays: Optional[list[int]] = None  # 0=周一, 6=周日;空=每天

class ReminderUpdate(BaseModel):
    type: str | None = None
    time: str | None = None
    enabled: bool | None = None
    weekdays: Optional[list[int]] = None

class ReminderResponse(ReminderBase):
    id: int
    user_id: int
    weekdays: Optional[list[int]] = None
    created_at: datetime
    class Config:
        from_attributes = True
