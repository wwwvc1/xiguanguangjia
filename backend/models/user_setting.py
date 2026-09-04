from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserSettingResponse(BaseModel):
    user_id: int
    target_calories: int
    home_layout: Optional[list] = None
    updated_at: datetime

class UserSettingUpdate(BaseModel):
    target_calories: Optional[int] = None
    home_layout: Optional[list] = None
