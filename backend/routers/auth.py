import requests
from fastapi import APIRouter, HTTPException, Depends, Security
from pydantic import BaseModel
from database import get_connection
from utils.auth import create_access_token
from utils.deps import security, get_current_user
from models.token import WeChatLoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
USE_MOCK = True

@router.post("/login", response_model=TokenResponse)
def wechat_login(req: WeChatLoginRequest):
    """微信登录：code -> openid -> 用户 -> JWT"""
    # Step 1: 获取 openid
    if USE_MOCK:
        openid = f"mock_openid_{req.code}"
    else:
        wx_appid = "你的小程序appid"
        wx_secret = "你的小程序密钥"
        wx_url = (
            f"https://api.weixin.qq.com/sns/jscode2session"
            f"?appid={wx_appid}&secret={wx_secret}&js_code={req.code}&grant_type=authorization_code"
        )
        resp = requests.get(wx_url).json()
        if "openid" not in resp:
            raise HTTPException(status_code=400, detail="微信登录失败")
        openid = resp["openid"]

    # Step 2: 查找或创建用户
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, nickname, avatar FROM users WHERE openid = %s",
                (openid,)
            )
            user = cursor.fetchone()

            if not user:
                cursor.execute(
                    "INSERT INTO users (openid) VALUES (%s)",
                    (openid,)
                )
                user_id = cursor.lastrowid
                conn.commit()
                user = {"id": user_id, "nickname": None, "avatar": None}
    finally:
        conn.close()

    # Step 3: 生成 JWT（mock 和 production 共用）
    token = create_access_token(data={"user_id": user["id"]})

    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        nickname=user["nickname"],
        avatar=user["avatar"]
    )

@router.get("/me")
def get_current_user_info(current_user: int = Depends(get_current_user)):
    """获取当前登录用户的信息（测试用）"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, openid, nickname, avatar, created_at FROM users WHERE id = %s",
                (current_user,)
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")
            return user
    finally:
        conn.close()