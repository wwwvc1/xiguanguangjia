"""管理员鉴权依赖与 JWT 工具"""
from datetime import timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_connection
from utils.auth import create_access_token, decode_token, verify_password

security = HTTPBearer()


def create_admin_token(user_id: int) -> str:
    """签发 admin token(payload 含 is_admin=True 标记)"""
    return create_access_token({"user_id": user_id, "is_admin": True})


def get_current_admin(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    管理员依赖:
    - 解码 JWT
    - 校验 is_admin 标记
    - 查 DB 二次确认 user.is_admin=1 且 is_active=1
    - 返回完整 admin 用户信息 dict
    """
    token = creds.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    is_admin_claim = payload.get("is_admin", False)
    if not user_id or not is_admin_claim:
        raise HTTPException(status_code=403, detail="非管理员 Token")

    # 查 DB 二次校验
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, username, nickname, avatar, is_admin, is_active, last_login_at
                   FROM users WHERE id = %s""",
                (user_id,)
            )
            row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not row.get("is_admin"):
        raise HTTPException(status_code=403, detail="非管理员")
    if not row.get("is_active"):
        raise HTTPException(status_code=403, detail="账号已停用")

    is_admin_flag = bool(row.get("is_admin"))
    # 角色映射:Phase 4 之前全 admin 都视为 super_admin;Phase 4 用 user_roles 表细化
    role = "super_admin" if is_admin_flag else "viewer"
    return {
        "id": row["id"],
        "username": row.get("username"),
        "nickname": row.get("nickname"),
        "avatar": row.get("avatar"),
        "is_admin": is_admin_flag,
        "role": role,
        "last_login_at": row.get("last_login_at"),
    }


def authenticate_admin(username: str, password: str) -> dict | None:
    """
    校验管理员账号密码,成功返回 user 记录(dict),失败返回 None。
    同时更新 last_login_at。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, username, password_hash, nickname, avatar, is_admin, is_active
                   FROM users WHERE username = %s""",
                (username,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            if not row.get("is_admin"):
                return None
            if not row.get("is_active"):
                return None
            if not row.get("password_hash"):
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            # 更新最后登录时间
            cursor.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                (row["id"],)
            )
            conn.commit()
            return {
                "id": row["id"],
                "username": row["username"],
                "nickname": row.get("nickname"),
                "avatar": row.get("avatar"),
            }
    finally:
        conn.close()
