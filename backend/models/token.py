from pydantic import BaseModel
class WeChatLoginRequest(BaseModel):
    code: str
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int | None = None
    nickname: str | None = None
