"""管理员 - 系统日志查询 & 统计"""
import json
import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from database import get_connection
from utils.admin_auth import get_current_admin
from models.operation_log import OperationLogResponse, OperationLogListResponse, OperationLogStatsItem

router = APIRouter(prefix="/api/admin/logs", tags=["admin-logs"])


def _to_response(row: dict) -> OperationLogResponse:
    """DB 行 -> 响应模型"""
    details = row.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            pass
    return OperationLogResponse(
        id=row["id"],
        user_id=row.get("user_id"),
        username=row.get("username"),
        action=row["action"],
        resource_type=row.get("resource_type"),
        resource_id=row.get("resource_id"),
        details=details,
        ip=row.get("ip"),
        user_agent=row.get("user_agent"),
        status=row.get("status", "success"),
        created_at=row["created_at"],
    )


@router.get("", response_model=OperationLogListResponse)
def list_logs(
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="success|failed"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    admin: dict = Depends(get_current_admin)
):
    """日志列表(分页 + 多维筛选)"""
    where = ["1=1"]
    params: list = []
    if user_id is not None:
        where.append("l.user_id = %s")
        params.append(user_id)
    if action:
        where.append("l.action = %s")
        params.append(action)
    if status:
        where.append("l.status = %s")
        params.append(status)
    if date_from:
        where.append("l.created_at >= %s")
        params.append(date_from + " 00:00:00")
    if date_to:
        where.append("l.created_at <= %s")
        params.append(date_to + " 23:59:59")
    where_sql = " AND ".join(where)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS c FROM operation_logs l WHERE {where_sql}", tuple(params))
            total = cursor.fetchone()["c"]

            offset = (page - 1) * page_size
            cursor.execute(
                f"""SELECT l.*, u.username
                    FROM operation_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE {where_sql}
                    ORDER BY l.id DESC
                    LIMIT %s OFFSET %s""",
                tuple(params) + (page_size, offset)
            )
            rows = cursor.fetchall()
            return OperationLogListResponse(
                total=total, page=page, page_size=page_size,
                items=[_to_response(r) for r in rows]
            )
    finally:
        conn.close()


@router.get("/actions")
def list_distinct_actions(admin: dict = Depends(get_current_admin)):
    """所有出现过的 action 类型(给筛选下拉用)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT action FROM operation_logs ORDER BY action")
            return {"actions": [r["action"] for r in cursor.fetchall()]}
    finally:
        conn.close()


@router.get("/stats")
def log_stats(days: int = Query(7, ge=1, le=90), admin: dict = Depends(get_current_admin)):
    """按 action 聚合最近 N 天"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT action, COUNT(*) AS c
                   FROM operation_logs
                   WHERE created_at >= %s
                   GROUP BY action
                   ORDER BY c DESC""",
                (since,)
            )
            items = [OperationLogStatsItem(action=r["action"], count=r["c"]) for r in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) AS c FROM operation_logs WHERE created_at >= %s", (since,))
            total = cursor.fetchone()["c"]
            cursor.execute(
                """SELECT DATE(created_at) AS d, COUNT(*) AS c
                   FROM operation_logs
                   WHERE created_at >= %s
                   GROUP BY DATE(created_at)
                   ORDER BY d""",
                (since,)
            )
            daily = [{"date": str(r["d"]), "count": r["c"]} for r in cursor.fetchall()]
            return {"total": total, "days": days, "by_action": items, "daily": daily}
    finally:
        conn.close()


@router.get("/export")
def export_logs_csv(
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    """导出 CSV"""
    where = ["1=1"]
    params: list = []
    if user_id is not None:
        where.append("l.user_id = %s"); params.append(user_id)
    if action:
        where.append("l.action = %s"); params.append(action)
    if date_from:
        where.append("l.created_at >= %s"); params.append(date_from + " 00:00:00")
    if date_to:
        where.append("l.created_at <= %s"); params.append(date_to + " 23:59:59")
    where_sql = " AND ".join(where)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""SELECT l.*, u.username
                    FROM operation_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE {where_sql}
                    ORDER BY l.id DESC
                    LIMIT 5000""",
                tuple(params)
            )
            rows = cursor.fetchall()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["ID", "时间", "用户ID", "用户名", "操作", "资源类型", "资源ID", "状态", "IP", "详情"])
        for r in rows:
            writer.writerow([
                r["id"], r["created_at"], r.get("user_id"), r.get("username"),
                r["action"], r.get("resource_type"), r.get("resource_id"),
                r.get("status"), r.get("ip"),
                json.dumps(r.get("details"), ensure_ascii=False) if r.get("details") else ""
            ])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=operation_logs.csv"}
        )
    finally:
        conn.close()
