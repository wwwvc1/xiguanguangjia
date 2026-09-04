from pydantic import BaseModel
from datetime import datetime,date
from typing import Literal

class MealItemBase(BaseModel):
    name: str
    portion: str | None = None
    calories: int

class MealItemCreate(MealItemBase):
    pass

class MealItemResponse(MealItemBase):
    id: int
    meal_id: int
    class Config:
        from_attributes = True

class MealBase(BaseModel):
    meal_type: Literal["breakfast", "lunch", "dinner"]
    date: date
    total_calories: int = 0

class MealCreate(MealBase):
    items: list[MealItemCreate]

class MealResponse(MealBase):
    id: int
    user_id: int
    created_at: datetime
    items: list[MealItemResponse] = []
