from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AchievementResponse(BaseModel):
    id: int
    user_id: int
    type: str
    name: str
    description: Optional[str] = None
    unlocked_at: datetime
