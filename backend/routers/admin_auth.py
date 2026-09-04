"""管理员鉴权端点"""
from fastapi import APIRouter, Depends, HTTPException, Request
from models.admin import AdminLoginRequest, AdminLoginResponse, AdminMeResponse
from utils.admin_auth import (
    create_admin_token,
    get_current_admin,
    authenticate_admin,
)
from utils.operation_logger import log_admin_action, log

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, request: Request):
    """管理员账号密码登录"""
    user = authenticate_admin(payload.username, payload.password)
    if not user:
        # 记一条失败日志(user_id 用 -1 表示未知)
        ip, ua = log.__globals__["extract_client_info"](request) if False else (None, None)
        from utils.operation_logger import extract_client_info
        ip, ua = extract_client_info(request)
        log(
            action="admin_login_failed",
            user_id=None,
            details={"username": payload.username, "reason": "invalid_credentials"},
            ip=ip, user_agent=ua, status="failed"
        )
        raise HTTPException(status_code=401, detail="账号或密码错误,或非管理员账号")

    token = create_admin_token(user["id"])

    # 登录成功日志
    from utils.operation_logger import extract_client_info
    ip, ua = extract_client_info(request)
    log(
        user_id=user["id"],
        action="admin_login_success",
        resource_type="user", resource_id=user["id"],
        details={"username": payload.username},
        ip=ip, user_agent=ua, status="success"
    )

    return AdminLoginResponse(
        access_token=token,
        user_id=user["id"],
        username=user["username"],
        nickname=user.get("nickname"),
        avatar=user.get("avatar"),
        is_admin=True,
    )


@router.get("/me", response_model=AdminMeResponse)
def admin_me(admin: dict = Depends(get_current_admin)):
    """当前登录管理员信息

    返回 role:
      - is_admin=1 → 'super_admin'(Phase 4 之前全 admin 都当 super_admin)
      - is_admin=0 → 'viewer'(只读)
    """
    is_admin_flag = bool(admin.get("is_admin", True))
    role = "super_admin" if is_admin_flag else "viewer"
    return AdminMeResponse(
        user_id=admin["id"],
        username=admin["username"],
        nickname=admin.get("nickname"),
        avatar=admin.get("avatar"),
        is_admin=is_admin_flag,
        role=role,
        last_login_at=admin.get("last_login_at"),
    )


@router.post("/logout")
def admin_logout(admin: dict = Depends(get_current_admin), request: Request = None):
    """退出登录(无状态 JWT,客户端丢 token 即可,这里只做日志)"""
    from utils.operation_logger import extract_client_info
    if request:
        ip, ua = extract_client_info(request)
    else:
        ip, ua = None, None
    log(
        user_id=admin["id"],
        action="admin_logout",
        resource_type="user", resource_id=admin["id"],
        ip=ip, user_agent=ua, status="success"
    )
    return {"message": "已退出登录"}
