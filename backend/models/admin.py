"""管理后台相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- 管理员登录 ---
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    is_admin: bool = True


class AdminMeResponse(BaseModel):
    user_id: int
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    is_admin: bool
    role: str = "viewer"  # 'super_admin' | 'viewer'(基于 is_admin,Phase 4 细化)
    last_login_at: Optional[datetime] = None


# --- 用户管理 ---
class UserListItem(BaseModel):
    id: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    openid: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    ai_calls_remaining: int = 100
    data_counts: dict = Field(default_factory=dict)


class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserListItem]


class UserDetailResponse(BaseModel):
    id: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    openid: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    ai_calls_remaining: int = 100
    data_counts: dict


class UserActiveUpdate(BaseModel):
    is_active: bool


class UserResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


class UserQuotaUpdate(BaseModel):
    set: Optional[int] = None
    delta: Optional[int] = None


# --- Dashboard ---
class DashboardUsers(BaseModel):
    total: int
    active_7d: int
    new_7d: int
    active_rate: float


class DashboardData(BaseModel):
    todos: int
    goals: int
    transactions: int
    meals: int
    reminders: int
    achievements: int
    reports: int


class DashboardAI(BaseModel):
    calls_7d: int
    calls_today: int
    unique_users_7d: int


class DashboardLLM(BaseModel):
    models_total: int
    system_default_id: Optional[int] = None
    system_default_name: Optional[str] = None


class DashboardKnowledge(BaseModel):
    documents: int
    chunks: int


class DashboardStats(BaseModel):
    users: DashboardUsers
    data: DashboardData
    ai: DashboardAI
    llm: DashboardLLM
    knowledge: DashboardKnowledge
    logs_7d: int


# --- 知识库 ---
class KnowledgeDocumentResponse(BaseModel):
    id: int
    filename: str
    chunk_count: int
    file_size: int
    status: str
    error_msg: Optional[str] = None
    uploaded_by: int
    uploader_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentListResponse(BaseModel):
    total: int
    items: list[KnowledgeDocumentResponse]
