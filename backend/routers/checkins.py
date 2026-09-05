"""
打卡 API (异步版)
- POST /api/checkins              当天打卡(幂等,已打过返回已存在)
  body: { note?: string, auto?: bool }
  auto=true: 前端自动触发(登录后首页 onShow),不触发成就解锁
  auto=false(默认): 用户手动,会触发 check_and_unlock
- GET  /api/checkins              列出最近 N 天(默认 30)
- GET  /api/checkins/streak       当前连续打卡天数
- GET  /api/checkins/today        今日是否已打卡
"""
import asyncio
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from aiomysql import DictCursor
from database import get_conn
from utils.deps import get_current_user
from utils.achievement_engine import check_and_unlock

router = APIRouter(prefix="/api/checkins", tags=["checkins"])


class CheckinCreate(BaseModel):
    note: Optional[str] = None
    auto: bool = False  # True=前端自动触发,跳过成就解锁


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def _calc_streak(user_id: int) -> int:
    """计算并返回当前连续打卡天数(供 do_checkin / get_streak 共用)"""
    conn = None
    from database import get_sync_connection
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT checkin_date FROM checkins "
                "WHERE user_id = %s ORDER BY checkin_date DESC LIMIT 365",
                (user_id,)
            )
            dates = [r["checkin_date"] for r in cur.fetchall()]
    finally:
        conn.close()
    if not dates:
        return 0
    today = date.today()
    last = dates[0]
    if last < today - timedelta(days=1):
        return 0
    start = today if last == today else last
    streak = 0
    expected = start
    date_set = set(dates)
    while expected in date_set:
        streak += 1
        expected -= timedelta(days=1)
    return streak


@router.post("/")
async def do_checkin(payload: CheckinCreate, current_user: int = Depends(get_current_user)):
    """当天打卡(一天一次,重复打返回已有记录)

    三分支:
    - 已有今日记录 → 不插入,只返回当前 streak
    - auto=True → 插入(auto=1),**不**触发 check_and_unlock
    - auto=False → 插入(auto=0),触发 check_and_unlock
    """
    today = _today_str()
    is_auto = bool(payload.auto)
    row = None
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, checkin_date, note, created_at, auto FROM checkins "
                "WHERE user_id = %s AND checkin_date = %s",
                (current_user, today)
            )
            existing = await cur.fetchone()
            if existing:
                # 已有今日记录(幂等)
                streak = await asyncio.get_event_loop().run_in_executor(None, _calc_streak, current_user)
                return {
                    "already": True,
                    "auto": is_auto,
                    "streak": streak,
                    "checkin": {
                        "id": existing["id"],
                        "date": str(existing["checkin_date"]),
                        "note": existing.get("note"),
                        "auto": int(existing.get("auto", 0)),
                        "created_at": str(existing["created_at"])
                    },
                    "newly_unlocked": []
                }
            # 新打卡
            await cur.execute(
                "INSERT INTO checkins (user_id, checkin_date, note, auto) VALUES (%s, %s, %s, %s)",
                (current_user, today, payload.note, 1 if is_auto else 0)
            )
            new_id = cur.lastrowid
            await conn.commit()
            await cur.execute(
                "SELECT id, checkin_date, note, created_at, auto FROM checkins WHERE id = %s",
                (new_id,)
            )
            row = await cur.fetchone()
    # 计算新 streak(已包含今天)
    streak = await asyncio.get_event_loop().run_in_executor(None, _calc_streak, current_user)
    if is_auto:
        newly = []
    else:
        try:
            newly = await asyncio.get_event_loop().run_in_executor(None, check_and_unlock, current_user)
        except Exception as e:
            print(f"[Checkin] check_and_unlock failed: {e}")
            newly = []
    return {
        "already": False,
        "auto": is_auto,
        "streak": streak,
        "checkin": {
            "id": row["id"],
            "date": str(row["checkin_date"]),
            "note": row.get("note"),
            "auto": int(row.get("auto", 0)),
            "created_at": str(row["created_at"])
        },
        "newly_unlocked": newly
    }


@router.get("/today")
async def today_status(current_user: int = Depends(get_current_user)):
    """今日是否已打卡"""
    today = _today_str()
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, checkin_date, note, created_at, auto FROM checkins "
                "WHERE user_id = %s AND checkin_date = %s",
                (current_user, today)
            )
            row = await cur.fetchone()
            return {
                "checked_in": row is not None,
                "checkin": ({
                    "id": row["id"], "date": str(row["checkin_date"]),
                    "note": row.get("note"), "auto": int(row.get("auto", 0)),
                    "created_at": str(row["created_at"])
                } if row else None)
            }


@router.get("/")
async def list_recent(days: int = Query(30, ge=1, le=365), current_user: int = Depends(get_current_user)):
    """列出最近 N 天的打卡记录"""
    since = (date.today() - timedelta(days=days-1)).strftime("%Y-%m-%d")
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, checkin_date, note, auto, created_at FROM checkins "
                "WHERE user_id = %s AND checkin_date >= %s ORDER BY checkin_date DESC",
                (current_user, since)
            )
            rows = await cur.fetchall()
            for r in rows:
                r["date"] = str(r.pop("checkin_date"))
                r["created_at"] = str(r["created_at"])
                r["auto"] = int(r.get("auto", 0))
    return {"items": rows, "count": len(rows)}


@router.get("/streak")
async def get_streak(current_user: int = Depends(get_current_user)):
    """当前连续打卡天数(从今天/昨天往前数连续)"""
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT DISTINCT checkin_date FROM checkins "
                "WHERE user_id = %s ORDER BY checkin_date DESC LIMIT 365",
                (current_user,)
            )
            dates = [r["checkin_date"] for r in await cur.fetchall()]

    if not dates:
        return {"streak": 0, "today_checked": False, "last_date": None, "missed_yesterday": False}

    today = date.today()
    last = dates[0]
    missed_yesterday = (last == today - timedelta(days=2))
    if last == today:
        today_checked = True
        start = today
    elif last == today - timedelta(days=1):
        today_checked = False
        start = last
    else:
        return {
            "streak": 0,
            "today_checked": False,
            "last_date": str(last),
            "missed_yesterday": missed_yesterday
        }

    streak = 0
    expected = start
    date_set = set(dates)
    while expected in date_set:
        streak += 1
        expected -= timedelta(days=1)

    return {
        "streak": streak,
        "today_checked": today_checked,
        "last_date": str(last),
        "missed_yesterday": False
    }

