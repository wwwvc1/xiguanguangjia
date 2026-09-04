from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class TransactionBase(BaseModel):
    category: str
    description: str | None = None
    amount: float
    type: Literal["income", "expense"]
    time: datetime

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    category: str | None = None
    description: str | None = None
    amount: float | None = None
    type: Literal["income", "expense"] | None = None
    time: datetime | None = None

class TransactionResponse(TransactionBase):
    id: int
    user_id: int
    created_at: datetime
    class Config:
        from_attributes = True
