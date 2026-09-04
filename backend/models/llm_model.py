"""LLM 模型相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LLMModelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="展示名")
    base_url: str = Field(..., min_length=1, max_length=255, description="OpenAI 兼容 base_url")
    api_key: str = Field(..., min_length=1, max_length=512, description="API Key")
    model_name: str = Field(..., min_length=1, max_length=128, description="模型标识")


class LLMModelCreate(LLMModelBase):
    is_system_default: bool = False
    is_active: bool = True
    owner_user_id: Optional[int] = None  # None=系统模型


class LLMModelUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    is_active: Optional[bool] = None


class LLMModelResponse(LLMModelBase):
    id: int
    is_system_default: bool
    is_active: bool
    owner_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    api_key_masked: str = ""  # 脱敏后的 key

    class Config:
        from_attributes = True


class LLMModelTestRequest(BaseModel):
    prompt: str = Field(default="你好,请用一句话自我介绍。")


class LLMModelTestResponse(BaseModel):
    success: bool
    latency_ms: int
    reply: Optional[str] = None
    error: Optional[str] = None


class LLMModelListResponse(BaseModel):
    system_models: list[LLMModelResponse]
    user_models: list[LLMModelResponse]
    active_model_id: Optional[int] = None  # 用户当前激活的模型
