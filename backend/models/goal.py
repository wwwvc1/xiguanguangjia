from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional

class GoalBase(BaseModel):
    name: str
class GoalCreate(GoalBase):
    progress: int = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    linked_metric: Optional[str] = None  # 关联的 metric,自动算进度
class GoalUpdate(BaseModel):
    name: str | None = None
    progress: int | None = None
    done: bool | None = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    linked_metric: Optional[str] = None
class GoalResponse(GoalBase):
    id: int
    progress: int
    done: bool
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    linked_metric: Optional[str] = None
    created_at: datetime
    update_time: datetime
    class Config:
        from_attributes = True
