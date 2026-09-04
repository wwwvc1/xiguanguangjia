from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional

class TodoBase(BaseModel):
    text: str

class TodoCreate(TodoBase):
    due_date: Optional[str] = None  # 格式 YYYY-MM-DD

class TodoCreateBatch(TodoBase):
    start_date: str  # 格式 YYYY-MM-DD
    end_date: str    # 格式 YYYY-MM-DD

class TodoUpdate(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None
    due_date: Optional[str] = None

class TodoResponse(TodoBase):
    id: int
    done: bool
    due_date: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True
