"""操作日志写入工具"""
import json
from typing import Optional, Any
from fastapi import Request
from database import get_connection


def _safe_json(obj: Any) -> Optional[str]:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return None


def log(
    *,
    action: str,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Any = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "success",
) -> int:
    """写一条操作日志,返回 log id。失败不抛异常(日志不应该影响主流程)"""
    try:
        details_json = _safe_json(details) if details is not None else None
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO operation_logs
                       (user_id, action, resource_type, resource_id, details, ip, user_agent, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, action, resource_type, resource_id, details_json, ip, user_agent, status)
                )
                log_id = cursor.lastrowid
            conn.commit()
            return log_id
        finally:
            conn.close()
    except Exception as e:
        print(f"[OperationLog] 写入失败: {e}")
        return 0


def extract_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """从 Request 提取 IP 和 user_agent"""
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else None)
    )
    ua = request.headers.get("user-agent")
    return ip, ua


def log_admin_action(
    request: Request,
    admin: dict,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Any = None,
    status: str = "success",
):
    """管理员操作的便捷日志记录"""
    ip, ua = extract_client_info(request)
    return log(
        user_id=admin["id"],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip=ip,
        user_agent=ua,
        status=status,
    )
