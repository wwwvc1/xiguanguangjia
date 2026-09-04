from fastapi import HTTPException,Depends,status
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from database import get_connection
from utils.auth import decode_token

security = HTTPBearer()

ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"

ROLE_HIERARCHY = {
    ROLE_ADMIN : [ROLE_MODERATOR,ROLE_USER],
    ROLE_MODERATOR : [ROLE_USER],
    ROLE_USER : []
}

def get_user_roles(user_id: int) -> list[str]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT r.name FROM roles r "
                " JOIN user_roles ur ON r.id = ur.role_id"
                " WHERE ur.user_id = %s",
                (user_id,)
            )
            return [row["name"] for row in cursor.fetchall()]
    finally:
        conn.close()

def has_role(user_roles: list[str],required_role: str) -> bool:
    """检查用户是否有指定角色(包含继承角色)"""
    if required_role in user_roles:
        return True
    for role in user_roles:
        if required_role in ROLE_HIERARCHY.get(role,[]):
            return True
    return False

def require_role(required_role: str):
    """
    RBAC 依赖工厂： 创建一个需要指定角色的依赖。
    用法：
        @router.get("/admin/users")
         def admin_only(admin: dict = Depends(require_role("admin"))):
          # admin = {"user_id": 1, "roles": ["admin"]}
    """
    async  def role_checker(credentials: HTTPAuthorizationCredentials = Depends(security)):
        token = credentials.credentials
        payload = decode_token(token)
        if payload is None:
            raise HTTPException(status_code=401,detail="无效的token或已过期")
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401,detail="token格式错误")
        user_roles = get_user_roles(user_id)
        if not has_role(user_roles,required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail = f"权限不足，需要{required_role}角色"
            )
        return {"user_id": user_id, "roles": user_roles}
    return role_checker
