"""登录相关 API
- 微信登录:`POST /api/auth/login`(body: {code})
- 账号密码登录:`POST /api/auth/login-with-password`(body: {username, password})
- 注册:`POST /api/auth/register`(body: {username, password, nickname?})
- 当前用户信息:`GET /api/auth/me`

USE_MOCK 模式:
  - 微信 code 不去微信服务器换 openid,直接用 STABLE_MOCK_OPENID
  - 所有 mock 微信登录都进入同一个账号,避免 wx.login() code 变化导致每次都是新用户
"""
import re
import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from database import get_connection
from utils.auth import create_access_token, hash_password, verify_password
from utils.deps import security, get_current_user
from models.token import WeChatLoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ============= 模式开关 =============
# True: 微信登录走 mock(openid 固定),不需要 appid/secret
# False: 微信登录走真 jscode2session,需要在 .env 填 WX_APPID / WX_SECRET
USE_MOCK = True
STABLE_MOCK_OPENID = "mock_user_dev"   # mock 模式下,所有用户共用这个 openid

# 真微信模式下,从 .env 读(没配就报错)
import os
WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")


# ============= Pydantic models =============

class PasswordLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=32)


# ============= Helper =============

def _exchange_code_for_openid(code: str) -> str:
    """真微信模式:用 code 换 openid"""
    if not WX_APPID or not WX_SECRET:
        raise HTTPException(status_code=500, detail="真微信模式未配置 WX_APPID/WX_SECRET")
    url = (
        f"https://api.weixin.qq.com/sns/jscode2session"
        f"?appid={WX_APPID}&secret={WX_SECRET}&js_code={code}&grant_type=authorization_code"
    )
    try:
        resp = requests.get(url, timeout=5).json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"微信服务器无响应: {e}")
    if "openid" not in resp:
        raise HTTPException(status_code=400, detail=f"微信登录失败: {resp.get('errmsg', '未知错误')}")
    return resp["openid"]


def _find_or_create_by_openid(openid: str) -> dict:
    """根据 openid 查/建用户"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, nickname, avatar FROM users WHERE openid = %s",
                (openid,)
            )
            user = cursor.fetchone()
            if not user:
                cursor.execute("INSERT INTO users (openid) VALUES (%s)", (openid,))
                user_id = cursor.lastrowid
                conn.commit()
                user = {"id": user_id, "nickname": None, "avatar": None}
            return user
    finally:
        conn.close()


# ============= Endpoints =============

@router.post("/login", response_model=TokenResponse)
def wechat_login(req: WeChatLoginRequest):
    """微信登录:code -> openid -> 用户 -> JWT"""
    if USE_MOCK:
        openid = STABLE_MOCK_OPENID
    else:
        openid = _exchange_code_for_openid(req.code)

    user = _find_or_create_by_openid(openid)
    token = create_access_token(data={"user_id": user["id"]})
    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        nickname=user["nickname"],
        avatar=user["avatar"]
    )


@router.post("/login-with-password", response_model=TokenResponse)
def login_with_password(req: PasswordLoginRequest):
    """账号密码登录(开发/测试/后台用)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, nickname, avatar, password_hash, is_active
                   FROM users WHERE username = %s""",
                (req.username,)
            )
            row = cursor.fetchone()
            if not row or not row.get("password_hash"):
                raise HTTPException(status_code=401, detail="账号或密码错误")
            if not row.get("is_active", 1):
                raise HTTPException(status_code=403, detail="账号已停用")
            if not verify_password(req.password, row["password_hash"]):
                raise HTTPException(status_code=401, detail="账号或密码错误")

            # 更新最后登录时间
            cursor.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                (row["id"],)
            )
            conn.commit()

            token = create_access_token(data={"user_id": row["id"]})
            return TokenResponse(
                access_token=token,
                user_id=row["id"],
                nickname=row["nickname"],
                avatar=row["avatar"]
            )
    finally:
        conn.close()


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """注册新账号(账号密码方式)"""
    if not USERNAME_RE.match(req.username):
        raise HTTPException(
            status_code=400,
            detail="用户名需 3-32 位,只能含字母、数字、下划线、连字符"
        )

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE username = %s",
                (req.username,)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="用户名已存在")

            # 注册时同时给一个稳定 openid 前缀(区分微信登录用户)
            # 用 'pwd_' 前缀避免和微信 openid 冲突
            cursor.execute(
                """INSERT INTO users (openid, username, password_hash, nickname, is_active)
                   VALUES (%s, %s, %s, %s, 1)""",
                (
                    f"pwd_{req.username}",
                    req.username,
                    hash_password(req.password),
                    req.nickname or req.username
                )
            )
            user_id = cursor.lastrowid
            conn.commit()

            token = create_access_token(data={"user_id": user_id})
            return TokenResponse(
                access_token=token,
                user_id=user_id,
                nickname=req.nickname or req.username,
                avatar=None
            )
    finally:
        conn.close()


@router.get("/me")
def get_current_user_info(current_user: int = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, openid, username, nickname, avatar, is_admin, created_at
                   FROM users WHERE id = %s""",
                (current_user,)
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")
            return user
    finally:
        conn.close()
