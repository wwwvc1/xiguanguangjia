from pydantic import BaseModel
from typing import Optional, List, Dict

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict]] = None  # 多轮对话历史, [{role, content}]
    model_id: Optional[int] = None  # 指定模型 id(系统/用户自定义), 不传则用用户激活或系统默认

class ChatResponse(BaseModel):
    reply: str
    sources: list[str] | None = None
