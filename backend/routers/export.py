"""
数据导出 - 支持 JSON / CSV 格式
- GET /api/export?format=json → 全量数据 JSON 文件
- GET /api/export/transactions?format=csv → 单表 CSV
"""
import csv
import io
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from database import get_connection
from utils.deps import get_current_user

router = APIRouter(prefix="/api/export", tags=["export"])


def _fetch_all_user_data(user_id: int) -> dict:
    """拉取用户的全量数据"""
    conn = get_connection()
    data = {
        "exported_at": datetime.now().isoformat(),
        "user_id": user_id,
        "todos": [],
        "goals": [],
        "transactions": [],
        "meals": [],
        "reminders": [],
        "user_settings": None
    }
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            for r in cursor.fetchall():
                if r.get("due_date"):
                    r["due_date"] = str(r["due_date"])
                data["todos"].append(r)

            cursor.execute(
                "SELECT id, name, progress, done, created_at, update_time FROM goals WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            data["goals"] = cursor.fetchall()

            cursor.execute(
                "SELECT id, category, description, amount, type, time, created_at FROM transactions WHERE user_id = %s ORDER BY time DESC",
                (user_id,)
            )
            for r in cursor.fetchall():
                r["amount"] = float(r["amount"])
                if r.get("time"):
                    r["time"] = str(r["time"])
                data["transactions"].append(r)

            cursor.execute(
                "SELECT id, meal_type, date, total_calories, created_at FROM meals WHERE user_id = %s ORDER BY date DESC",
                (user_id,)
            )
            meals = cursor.fetchall()
            for m in meals:
                if m.get("date"):
                    m["date"] = str(m["date"])
                cursor.execute(
                    "SELECT id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                    (m["id"],)
                )
                m["items"] = cursor.fetchall()
            data["meals"] = meals

            cursor.execute(
                "SELECT id, type, time, enabled, created_at FROM reminders WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            for r in cursor.fetchall():
                if r.get("time"):
                    r["time"] = str(r["time"])
                data["reminders"].append(r)

            cursor.execute(
                "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            settings_row = cursor.fetchone()
            if settings_row:
                if settings_row.get("home_layout") and isinstance(settings_row["home_layout"], str):
                    try:
                        settings_row["home_layout"] = json.loads(settings_row["home_layout"])
                    except Exception:
                        pass
                data["user_settings"] = settings_row
    finally:
        conn.close()
    return data


@router.get("/")
def export_all(
    current_user: int = Depends(get_current_user),
    format: str = Query("json", pattern="^(json)$"),
    summary: bool = Query(False, description="只返回摘要(条数),不下载文件")
):
    """导出全量数据(JSON 格式)"""
    data = _fetch_all_user_data(current_user)
    if summary:
        return {
            "summary": True,
            "counts": {
                "todos": len(data["todos"]),
                "goals": len(data["goals"]),
                "transactions": len(data["transactions"]),
                "meals": len(data["meals"]),
                "reminders": len(data["reminders"])
            },
            "exported_at": data["exported_at"]
        }
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    filename = f"habit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/json; charset=utf-8"
        }
    )


@router.get("/transactions")
def export_transactions_csv(
    current_user: int = Depends(get_current_user),
    format: str = Query("csv", pattern="^(csv)$"),
    summary: bool = Query(False)
):
    """导出收支为 CSV"""
    if summary:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS c, "
                    "SUM(CASE WHEN type='income' THEN ABS(amount) ELSE 0 END) AS income, "
                    "SUM(CASE WHEN type='expense' THEN ABS(amount) ELSE 0 END) AS expense "
                    "FROM transactions WHERE user_id = %s",
                    (current_user,)
                )
                r = cursor.fetchone()
        finally:
            conn.close()
        return {
            "summary": True,
            "count": int(r["c"] or 0),
            "income": float(r["income"] or 0),
            "expense": float(r["expense"] or 0)
        }
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, type, category, description, amount, time, created_at FROM transactions WHERE user_id = %s ORDER BY time DESC",
                (current_user,)
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    # 用 UTF-8 BOM 让 Excel 正确识别中文
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf)
    writer.writerow(["ID", "类型", "分类", "描述", "金额(原始)", "时间", "创建时间"])
    for r in rows:
        writer.writerow([
            r["id"],
            "收入" if r["type"] == "income" else "支出",
            r["category"],
            r.get("description", ""),
            r["amount"],
            str(r.get("time", "")),
            str(r.get("created_at", ""))
        ])

    filename = f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8"
        }
    )
