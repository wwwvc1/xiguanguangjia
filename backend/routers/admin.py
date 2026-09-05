"""管理后台 - 用户管理 + Dashboard 统计"""
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from database import get_connection
from utils.admin_auth import get_current_admin
from utils.operation_logger import log_admin_action
from utils.achievement_engine import check_and_unlock
from models.admin import (
    UserListResponse, UserListItem, UserDetailResponse,
    UserActiveUpdate, UserResetPasswordRequest, UserQuotaUpdate,
    DashboardStats, DashboardUsers, DashboardData, DashboardAI, DashboardLLM, DashboardKnowledge
)
from utils.auth import hash_password


# ============================================================
# Pydantic 模型(本 router 用)
# ============================================================

class UserCreateRequest(BaseModel):
    """创建用户"""
    username: str = Field(..., min_length=3, max_length=64, description="登录账号")
    password: str = Field(..., min_length=6, max_length=128, description="初始密码")
    nickname: Optional[str] = Field(None, max_length=64, description="昵称")
    email: Optional[str] = Field(None, max_length=128, description="邮箱(可选,仅前端展示)")
    role: Optional[str] = Field("viewer", description="角色: super_admin / admin / viewer")
    is_active: Optional[bool] = Field(True, description="是否启用")


class UserUpdateRequest(BaseModel):
    """更新用户(部分字段)"""
    nickname: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=128)
    role: Optional[str] = Field(None, description="super_admin / admin / viewer")
    is_active: Optional[bool] = None


def _resolve_role_flags(role: Optional[str], is_admin: Optional[bool]) -> tuple[bool, str]:
    """把 role 字符串转成 (is_admin, role)"""
    if role is None and is_admin is None:
        return False, "viewer"
    r = (role or "viewer").lower()
    if r not in ("super_admin", "admin", "viewer"):
        r = "viewer"
    is_a = (r in ("super_admin", "admin")) if is_admin is None else bool(is_admin)
    return is_a, ("admin" if is_a and r == "admin" else ("super_admin" if is_a else "viewer"))


def _gen_placeholder_openid(prefix: str = "manual") -> str:
    """为非微信注册的用户生成占位 openid(必须 NOT NULL)"""
    return f"{prefix}_{secrets.token_hex(6)}"

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================ 用户管理 ============================
@router.get("/users", response_model=UserListResponse)
def list_users(
    q: Optional[str] = Query(None, description="搜索:username/nickname/openid/id"),
    is_active: Optional[bool] = Query(None),
    is_admin: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    admin: dict = Depends(get_current_admin)
):
    """用户列表(分页 + 搜索 + 筛选)"""
    where = ["1=1"]
    params: list = []
    if q:
        like = f"%{q}%"
        where.append("(u.username LIKE %s OR u.nickname LIKE %s OR u.openid LIKE %s OR CAST(u.id AS CHAR) LIKE %s)")
        params += [like, like, like, like]
    if is_active is not None:
        where.append("u.is_active = %s")
        params.append(int(is_active))
    if is_admin is not None:
        where.append("u.is_admin = %s")
        params.append(int(is_admin))
    where_sql = " AND ".join(where)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM users u WHERE {where_sql}", tuple(params))
            total = cursor.fetchone()["c"]

            offset = (page - 1) * page_size
            cursor.execute(
                f"""SELECT u.id, u.username, u.nickname, u.avatar, u.openid, u.is_admin, u.is_active,
                          u.created_at, u.last_login_at,
                          COALESCE(q.ai_calls_remaining, 100) AS ai_calls_remaining
                   FROM users u
                   LEFT JOIN user_quotas q ON q.user_id = u.id
                   WHERE {where_sql}
                   ORDER BY u.id DESC
                   LIMIT %s OFFSET %s""",
                tuple(params) + (page_size, offset)
            )
            users = cursor.fetchall()
            # 拿各用户的表数据统计
            user_ids = [u["id"] for u in users]
            data_counts = {uid: {"todos": 0, "goals": 0, "transactions": 0, "meals": 0} for uid in user_ids}
            if user_ids:
                ph = ",".join(["%s"] * len(user_ids))
                for table in ("todos", "goals", "transactions", "meals"):
                    cursor.execute(f"SELECT user_id, COUNT(*) AS c FROM {table} WHERE user_id IN ({ph}) GROUP BY user_id", tuple(user_ids))
                    for r in cursor.fetchall():
                        data_counts.setdefault(r["user_id"], {})[table] = r["c"]

            items = [
                UserListItem(
                    id=u["id"],
                    username=u.get("username"),
                    nickname=u.get("nickname"),
                    avatar=u.get("avatar"),
                    openid=u["openid"],
                    is_admin=bool(u["is_admin"]),
                    is_active=bool(u["is_active"]),
                    created_at=u["created_at"],
                    last_login_at=u.get("last_login_at"),
                    ai_calls_remaining=int(u.get("ai_calls_remaining", 100)),
                    data_counts=data_counts.get(u["id"], {})
                )
                for u in users
            ]
            return UserListResponse(total=total, page=page, page_size=page_size, items=items)
    finally:
        conn.close()


@router.get("/users/{user_id}", response_model=UserDetailResponse)
def get_user_detail(user_id: int, admin: dict = Depends(get_current_admin)):
    """用户详情 + 全表数据统计"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT u.id, u.username, u.nickname, u.avatar, u.openid, u.is_admin, u.is_active,
                          u.created_at, u.last_login_at, u.password_hash IS NOT NULL AS has_password,
                          COALESCE(q.ai_calls_remaining, 100) AS ai_calls_remaining
                   FROM users u
                   LEFT JOIN user_quotas q ON q.user_id = u.id
                   WHERE u.id = %s""",
                (user_id,)
            )
            u = cursor.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            counts = {}
            for table in ("todos", "goals", "transactions", "meals", "reminders", "achievements", "reports"):
                cursor.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE user_id = %s", (user_id,))
                counts[table] = cursor.fetchone()["c"]

            return UserDetailResponse(
                id=u["id"],
                username=u.get("username"),
                nickname=u.get("nickname"),
                avatar=u.get("avatar"),
                openid=u["openid"],
                is_admin=bool(u["is_admin"]),
                is_active=bool(u["is_active"]),
                created_at=u["created_at"],
                last_login_at=u.get("last_login_at"),
                ai_calls_remaining=int(u.get("ai_calls_remaining", 100)),
                data_counts=counts
            )
    finally:
        conn.close()


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    """删除用户(级联)"""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            u = cursor.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")
            if u.get("is_admin"):
                raise HTTPException(status_code=400, detail="不能删除其他管理员")
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            log_admin_action(request, admin, "delete_user", "user", user_id, {"username": u.get("username")})
            return {"message": "已删除"}
    finally:
        conn.close()


@router.post("/users", response_model=UserDetailResponse)
def create_user(payload: UserCreateRequest, request: Request, admin: dict = Depends(get_current_admin)):
    """管理员手动创建用户

    - 生成占位 openid(非微信登录用)
    - username 唯一
    - role: super_admin / admin / viewer(默认 viewer,只有 super_admin 才能创建 admin)
    """
    if payload.role == "super_admin" and admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="只有超级管理员才能创建超级管理员账号")

    is_a, resolved_role = _resolve_role_flags(payload.role, None)
    # 只允许超级管理员/admin 创建 admin
    if is_a and admin.get("role") not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="权限不足,无法创建管理员账号")

    pwd_hash = hash_password(payload.password)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # username 唯一
            cursor.execute("SELECT id FROM users WHERE username = %s", (payload.username,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail=f"用户名 '{payload.username}' 已存在")

            placeholder_openid = _gen_placeholder_openid()
            cursor.execute(
                """INSERT INTO users (openid, username, password_hash, nickname, is_admin, is_active, last_login_at)
                   VALUES (%s, %s, %s, %s, %s, 1, NOW())""",
                (placeholder_openid, payload.username, pwd_hash,
                 payload.nickname or payload.username, int(is_a))
            )
            new_id = cursor.lastrowid
            # 配额默认 100
            cursor.execute(
                """INSERT INTO user_quotas (user_id, ai_calls_remaining) VALUES (%s, 100)
                   ON DUPLICATE KEY UPDATE ai_calls_remaining = VALUES(ai_calls_remaining)""",
                (new_id,)
            )
            conn.commit()

            # 回读详情
            cursor.execute(
                """SELECT u.id, u.username, u.nickname, u.avatar, u.openid, u.is_admin, u.is_active,
                          u.created_at, u.last_login_at, u.password_hash IS NOT NULL AS has_password,
                          COALESCE(q.ai_calls_remaining, 100) AS ai_calls_remaining
                   FROM users u LEFT JOIN user_quotas q ON q.user_id = u.id
                   WHERE u.id = %s""",
                (new_id,)
            )
            u = cursor.fetchone()
            log_admin_action(request, admin, "create_user", "user", new_id, {
                "username": payload.username, "role": resolved_role, "is_admin": is_a
            })
            return UserDetailResponse(
                id=u["id"],
                username=u.get("username"),
                nickname=u.get("nickname"),
                avatar=u.get("avatar"),
                openid=u["openid"],
                is_admin=bool(u["is_admin"]),
                is_active=bool(u["is_active"]),
                created_at=u["created_at"],
                last_login_at=u.get("last_login_at"),
                ai_calls_remaining=int(u.get("ai_calls_remaining", 100)),
                data_counts={},
            )
    finally:
        conn.close()


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
def update_user(user_id: int, payload: UserUpdateRequest, request: Request, admin: dict = Depends(get_current_admin)):
    """更新用户(昵称/角色/邮箱)
    - 不能改自己(避免误锁)
    - 角色升降需要 super_admin 权限
    """
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的账号,请用 /admin/auth/me")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT u.id, u.username, u.nickname, u.avatar, u.openid, u.is_admin, u.is_active,
                          u.created_at, u.last_login_at,
                          COALESCE(q.ai_calls_remaining, 100) AS ai_calls_remaining
                   FROM users u LEFT JOIN user_quotas q ON q.user_id = u.id
                   WHERE u.id = %s""",
                (user_id,)
            )
            u = cursor.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            sets: list[str] = []
            params: list = []
            details: dict = {}

            if payload.nickname is not None:
                sets.append("nickname = %s")
                params.append(payload.nickname)
                details["nickname"] = payload.nickname

            if payload.is_active is not None:
                if payload.is_active is False and u["id"] == admin["id"]:
                    raise HTTPException(status_code=400, detail="不能停用自己")
                sets.append("is_active = %s")
                params.append(int(payload.is_active))
                details["is_active"] = payload.is_active

            if payload.role is not None:
                # 角色变更需要 super_admin
                if admin.get("role") != "super_admin":
                    raise HTTPException(status_code=403, detail="只有超级管理员才能调整角色")
                new_is_a, new_role = _resolve_role_flags(payload.role, None)
                if new_role == "super_admin" and u.get("is_admin") and u.get("username") == admin.get("username"):
                    raise HTTPException(status_code=400, detail="不能降权自己的超级管理员身份")
                sets.append("is_admin = %s")
                params.append(int(new_is_a))
                details["role"] = new_role

            if not sets:
                raise HTTPException(status_code=400, detail="没有提供修改字段")

            params.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", tuple(params))
            conn.commit()

            log_admin_action(request, admin, "update_user", "user", user_id, details)

            # 回读最新
            cursor.execute(
                """SELECT u.id, u.username, u.nickname, u.avatar, u.openid, u.is_admin, u.is_active,
                          u.created_at, u.last_login_at,
                          COALESCE(q.ai_calls_remaining, 100) AS ai_calls_remaining
                   FROM users u LEFT JOIN user_quotas q ON q.user_id = u.id
                   WHERE u.id = %s""",
                (user_id,)
            )
            u = cursor.fetchone()
            counts = {}
            for table in ("todos", "goals", "transactions", "meals", "reminders", "achievements", "reports"):
                cursor.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE user_id = %s", (user_id,))
                counts[table] = cursor.fetchone()["c"]
            return UserDetailResponse(
                id=u["id"],
                username=u.get("username"),
                nickname=u.get("nickname"),
                avatar=u.get("avatar"),
                openid=u["openid"],
                is_admin=bool(u["is_admin"]),
                is_active=bool(u["is_active"]),
                created_at=u["created_at"],
                last_login_at=u.get("last_login_at"),
                ai_calls_remaining=int(u.get("ai_calls_remaining", 100)),
                data_counts=counts,
            )
    finally:
        conn.close()


@router.get("/users/{user_id}/data-summary")
def get_user_data_summary(user_id: int, admin: dict = Depends(get_current_admin)):
    """单个用户各业务表的数据量统计

    返回:
      { todos: N, goals: N, transactions: N, meals: N,
        reminders: N, achievements: N, reports: N,
        ai_chats_sessions: N, ai_chats_messages: N }
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")

            counts: dict = {}
            for table in ("todos", "goals", "transactions", "meals", "reminders", "achievements", "reports"):
                cursor.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE user_id = %s", (user_id,))
                counts[table] = int(cursor.fetchone()["c"] or 0)

            cursor.execute(
                "SELECT COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS messages "
                "FROM ai_chat_logs WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            counts["ai_chats_sessions"] = int(row.get("sessions") or 0)
            counts["ai_chats_messages"] = int(row.get("messages") or 0)

            # 上次活跃(最近登录/AI 调用)
            cursor.execute("SELECT MAX(last_login_at) AS last_login FROM users WHERE id = %s", (user_id,))
            last_login = cursor.fetchone().get("last_login")
            cursor.execute(
                "SELECT MAX(created_at) AS last_ai FROM ai_chat_logs WHERE user_id = %s",
                (user_id,)
            )
            last_ai = cursor.fetchone().get("last_ai")

            return {
                "user_id": user_id,
                "data_counts": counts,
                "last_login_at": str(last_login) if last_login else None,
                "last_ai_chat_at": str(last_ai) if last_ai else None,
            }
    finally:
        conn.close()


@router.post("/users/{user_id}/recompute-achievements")
def recompute_user_achievements(
    user_id: int,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """强制重新评估该用户的成就(返回新解锁列表 + 总评估数)

    内部调用 check_and_unlock,只对未解锁过的定义评估;
    已经解锁的不会重复写入。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            u = cursor.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")
    finally:
        conn.close()

    newly = check_and_unlock(user_id)
    log_admin_action(
        request, admin,
        action="recompute_user_achievements",
        resource_type="user", resource_id=user_id,
        details={"newly_unlocked_count": len(newly), "by_admin": admin.get("username")},
    )
    # recomputed 字段给前端展示"评估了多少条定义"
    # 计算方式:总定义数 - 之前已解锁数 - 本次新解锁数
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS c FROM achievement_definitions WHERE is_active = 1")
            total_active = int(cursor.fetchone()["c"] or 0)
            cursor.execute("SELECT COUNT(*) AS c FROM achievements WHERE user_id = %s", (user_id,))
            already = int(cursor.fetchone()["c"] or 0)
        # 评估过的 = max(0, total - (already - newly_count)) 等价于 total - (已解锁且不本次新增)
        recomputed = max(0, total_active - (already - len(newly)))
    finally:
        conn.close()

    return {
        "user_id": user_id,
        "recomputed": recomputed,
        "newly_unlocked": newly,
    }


@router.patch("/users/{user_id}/active")
def toggle_user_active(user_id: int, payload: UserActiveUpdate, request: Request, admin: dict = Depends(get_current_admin)):
    """封禁/解禁"""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能封禁自己")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (int(payload.is_active), user_id))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="用户不存在")
            conn.commit()
            log_admin_action(request, admin, "toggle_user_active", "user", user_id, {"is_active": payload.is_active})
            return {"message": "已封禁" if not payload.is_active else "已解禁", "is_active": payload.is_active}
    finally:
        conn.close()


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, payload: UserResetPasswordRequest, request: Request, admin: dict = Depends(get_current_admin)):
    """重置密码"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
            pwd_hash = hash_password(payload.new_password)
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pwd_hash, user_id))
            conn.commit()
            log_admin_action(request, admin, "reset_user_password", "user", user_id)
            return {"message": "密码已重置"}
    finally:
        conn.close()


@router.patch("/users/{user_id}/quota")
def update_user_quota(user_id: int, payload: UserQuotaUpdate, request: Request, admin: dict = Depends(get_current_admin)):
    """调整 AI 配额(set 直接设,delta 加减)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
            if payload.set is not None:
                new_val = max(0, int(payload.set))
            elif payload.delta is not None:
                cursor.execute("SELECT COALESCE(ai_calls_remaining, 100) AS cur FROM user_quotas WHERE user_id = %s", (user_id,))
                cur = cursor.fetchone()
                cur_val = int(cur["cur"]) if cur else 100
                new_val = max(0, cur_val + int(payload.delta))
            else:
                raise HTTPException(status_code=400, detail="需要 set 或 delta 之一")
            cursor.execute(
                """INSERT INTO user_quotas (user_id, ai_calls_remaining) VALUES (%s, %s)
                   ON DUPLICATE KEY UPDATE ai_calls_remaining = VALUES(ai_calls_remaining)""",
                (user_id, new_val)
            )
            conn.commit()
            log_admin_action(request, admin, "update_user_quota", "user", user_id, {"new": new_val, "set": payload.set, "delta": payload.delta})
            return {"message": "已更新", "ai_calls_remaining": new_val}
    finally:
        conn.close()


# ============================ AI 聊天记录 ============================
@router.get("/users/{user_id}/ai-chats")
def get_user_ai_chats(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    admin: dict = Depends(get_current_admin)
):
    """用户的 AI 聊天记录(session 维度聚合)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")
            cursor.execute(
                """SELECT session_id,
                          MIN(created_at) AS first_at,
                          MAX(created_at) AS last_at,
                          COUNT(*) AS msg_count,
                          SUBSTRING_INDEX(GROUP_CONCAT(CASE WHEN role='user' THEN content END ORDER BY created_at SEPARATOR '|||'), '|||', 1) AS first_user,
                          MAX(model) AS model
                   FROM ai_chat_logs
                   WHERE user_id = %s
                   GROUP BY session_id
                   ORDER BY MAX(created_at) DESC
                   LIMIT %s OFFSET %s""",
                (user_id, page_size, (page - 1) * page_size)
            )
            sessions = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(DISTINCT session_id) AS c FROM ai_chat_logs WHERE user_id = %s",
                (user_id,)
            )
            total = cursor.fetchone()["c"]
            for s in sessions:
                if s.get("first_at"): s["first_at"] = str(s["first_at"])
                if s.get("last_at"): s["last_at"] = str(s["last_at"])
            return {"total": total, "items": sessions}
    finally:
        conn.close()


@router.get("/users/{user_id}/ai-chats/{session_id}")
def get_user_ai_chat_detail(
    user_id: int, session_id: str,
    admin: dict = Depends(get_current_admin)
):
    """单个 session 的完整消息"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, role, content, tool_calls, model, created_at
                   FROM ai_chat_logs
                   WHERE user_id = %s AND session_id = %s
                   ORDER BY created_at ASC""",
                (user_id, session_id)
            )
            rows = cursor.fetchall()
            for r in rows:
                if r.get("created_at"): r["created_at"] = str(r["created_at"])
                if r.get("tool_calls") and isinstance(r["tool_calls"], str):
                    try: r["tool_calls"] = json.loads(r["tool_calls"])
                    except: pass
            return {"session_id": session_id, "messages": rows}
    finally:
        conn.close()


@router.delete("/users/{user_id}/ai-chats/{session_id}")
def delete_user_ai_chat_session(
    user_id: int,
    session_id: str,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """删除单条 AI 会话(全部消息)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")

            # 先统计要被删的行数(给日志用)
            cursor.execute(
                "SELECT COUNT(*) AS c FROM ai_chat_logs WHERE user_id = %s AND session_id = %s",
                (user_id, session_id),
            )
            msg_count = int(cursor.fetchone()["c"] or 0)

            cursor.execute(
                "DELETE FROM ai_chat_logs WHERE user_id = %s AND session_id = %s",
                (user_id, session_id),
            )
            deleted = cursor.rowcount
            conn.commit()

            log_admin_action(
                request, admin,
                action="delete_ai_chat_session",
                resource_type="ai_chat_session", resource_id=session_id,
                details={"target_user_id": user_id, "msg_count": msg_count},
            )
            return {"deleted": deleted, "session_id": session_id}
    finally:
        conn.close()


@router.delete("/users/{user_id}/ai-chats")
def delete_user_all_ai_chats(
    user_id: int,
    request: Request,
    before: Optional[str] = Query(
        None, description="YYYY-MM-DD,只删除此日期之前的会话;不传则全部删除"
    ),
    admin: dict = Depends(get_current_admin),
):
    """批量删除某用户的 AI 聊天记录

    Query:
      - before (可选): YYYY-MM-DD,只删 created_at < before 的会话
                       不传 → 全部删除该用户所有会话

    返回:{ deleted: number }
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="用户不存在")

            if before:
                cursor.execute(
                    "DELETE FROM ai_chat_logs WHERE user_id = %s AND created_at < %s",
                    (user_id, before + " 00:00:00"),
                )
            else:
                cursor.execute(
                    "DELETE FROM ai_chat_logs WHERE user_id = %s",
                    (user_id,),
                )
            deleted = cursor.rowcount
            conn.commit()

            log_admin_action(
                request, admin,
                action="delete_ai_chats_bulk",
                resource_type="user", resource_id=user_id,
                details={"deleted": deleted, "before": before},
            )
            return {"deleted": deleted, "before": before}
    finally:
        conn.close()


# ============================ Dashboard ============================
@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(admin: dict = Depends(get_current_admin)):
    """Dashboard 统计"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 用户
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            users_total = cursor.fetchone()["c"]
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT COUNT(*) AS c FROM users WHERE last_login_at >= %s", (seven_days_ago,))
            active_7d = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM users WHERE created_at >= %s", (seven_days_ago,))
            new_7d = cursor.fetchone()["c"]
            active_rate = round(active_7d / users_total, 3) if users_total > 0 else 0

            # 数据表统计
            counts = {}
            for table in ("todos", "goals", "transactions", "meals", "reminders", "achievements", "reports"):
                cursor.execute(f"SELECT COUNT(*) AS c FROM {table}")
                counts[table] = cursor.fetchone()["c"]

            # AI 调用
            cursor.execute("SELECT COUNT(*) AS c FROM ai_chat_logs WHERE created_at >= %s", (seven_days_ago,))
            ai_calls_7d = cursor.fetchone()["c"]
            today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
            cursor.execute("SELECT COUNT(*) AS c FROM ai_chat_logs WHERE created_at >= %s", (today_start,))
            ai_calls_today = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(DISTINCT user_id) AS c FROM ai_chat_logs WHERE created_at >= %s", (seven_days_ago,))
            ai_unique_7d = cursor.fetchone()["c"]

            # LLM
            cursor.execute("SELECT COUNT(*) AS c FROM llm_models WHERE is_active = 1")
            models_total = cursor.fetchone()["c"]
            cursor.execute("SELECT id, name FROM llm_models WHERE is_system_default = 1 LIMIT 1")
            default = cursor.fetchone()

            # 知识库(同时含静态 + 上传,以 Chroma 为权威源)
            from utils.ai_rag import get_rag_engine
            chroma_docs = get_rag_engine().list_documents()
            kb_docs = len(chroma_docs)
            kb_chunks = sum(d.get("chunk_count", 0) for d in chroma_docs)

            # 日志
            cursor.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE created_at >= %s", (seven_days_ago,))
            logs_7d = cursor.fetchone()["c"]

            return DashboardStats(
                users=DashboardUsers(total=users_total, active_7d=active_7d, new_7d=new_7d, active_rate=active_rate),
                data=DashboardData(**counts),
                ai=DashboardAI(calls_7d=ai_calls_7d, calls_today=ai_calls_today, unique_users_7d=ai_unique_7d),
                llm=DashboardLLM(models_total=models_total, system_default_id=default["id"] if default else None, system_default_name=default["name"] if default else None),
                knowledge=DashboardKnowledge(documents=kb_docs, chunks=int(kb_chunks)),
                logs_7d=logs_7d
            )
    finally:
        conn.close()
