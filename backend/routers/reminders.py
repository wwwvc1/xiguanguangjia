"""提醒 API (异步版)"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from aiomysql import DictCursor
from database import get_conn
from models.reminder import ReminderCreate, ReminderUpdate, ReminderResponse
from utils.deps import get_current_user

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


def _wd_to_json(weekdays):
    if weekdays is None:
        return None
    if isinstance(weekdays, str):
        return weekdays
    return json.dumps(list(weekdays))


def _wd_from_json(value):
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


@router.get("/", response_model=list[ReminderResponse])
async def list_reminders(
    current_user: int = Depends(get_current_user),
    enabled: bool | None = Query(None)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            sql = "SELECT id, user_id, type, time, enabled, weekdays, created_at FROM reminders WHERE user_id = %s"
            params = [current_user]
            if enabled is not None:
                sql += " AND enabled = %s"
                params.append(enabled)
            sql += " ORDER BY created_at DESC"
            await cur.execute(sql, tuple(params))
            rows = await cur.fetchall()
            for r in rows:
                r["time"] = str(r["time"])
                r["weekdays"] = _wd_from_json(r.get("weekdays"))
            return rows


@router.post("/", response_model=ReminderResponse, status_code=201)
async def create_reminder(reminder_data: ReminderCreate, current_user: int = Depends(get_current_user)):
    if reminder_data.weekdays is not None:
        for d in reminder_data.weekdays:
            if not isinstance(d, int) or d < 0 or d > 6:
                raise HTTPException(400, "weekdays 元素必须是 0-6 的整数(0=周一)")
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "INSERT INTO reminders (user_id, type, time, enabled, weekdays) VALUES (%s, %s, %s, %s, %s)",
                (current_user, reminder_data.type, reminder_data.time,
                 reminder_data.enabled, _wd_to_json(reminder_data.weekdays))
            )
            rid = cur.lastrowid
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, type, time, enabled, weekdays, created_at FROM reminders WHERE id = %s",
                (rid,)
            )
            row = await cur.fetchone()
            row["time"] = str(row["time"])
            row["weekdays"] = _wd_from_json(row.get("weekdays"))
            return row


@router.put("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: int,
    reminder_data: ReminderUpdate,
    current_user: int = Depends(get_current_user)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT id FROM reminders WHERE id = %s AND user_id = %s",
                              (reminder_id, current_user))
            if not await cur.fetchone():
                raise HTTPException(404, "提醒不存在")
            updates = {}
            if reminder_data.type is not None:
                updates["type"] = reminder_data.type
            if reminder_data.time is not None:
                updates["time"] = reminder_data.time
            if reminder_data.enabled is not None:
                updates["enabled"] = reminder_data.enabled
            if reminder_data.weekdays is not None:
                for d in reminder_data.weekdays:
                    if not isinstance(d, int) or d < 0 or d > 6:
                        raise HTTPException(400, "weekdays 元素必须是 0-6 的整数")
                updates["weekdays"] = _wd_to_json(reminder_data.weekdays)
            if not updates:
                raise HTTPException(400, "没有提供更新字段")
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [reminder_id]
            await cur.execute(f"UPDATE reminders SET {set_clause} WHERE id = %s", values)
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, type, time, enabled, weekdays, created_at FROM reminders WHERE id = %s",
                (reminder_id,)
            )
            row = await cur.fetchone()
            row["time"] = str(row["time"])
            row["weekdays"] = _wd_from_json(row.get("weekdays"))
            return row


@router.delete("/{reminder_id}")
async def delete_reminder(reminder_id: int, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("DELETE FROM reminders WHERE id = %s AND user_id = %s",
                              (reminder_id, current_user))
            if cur.rowcount == 0:
                raise HTTPException(404, "提醒不存在")
            await conn.commit()
            return {"message": "提醒删除成功"}
