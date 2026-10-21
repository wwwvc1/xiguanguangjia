"""checkins 表数据访问

打卡幂等靠 **数据库唯一索引** `(user_id, checkin_date)` 保证,
Redis 锁只是第二道防线(见 services/checkin_service.py)。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.database import execute, fetch_all, fetch_one, insert
from repositories.base import as_int, to_date_str

COLUMNS = "id, checkin_date, note, auto, created_at"


async def get_by_date(user_id: int, day: str) -> Optional[dict]:
    row = await fetch_one(
        f"SELECT {COLUMNS} FROM checkins WHERE user_id = %s AND checkin_date = %s",
        (user_id, day),
    )
    return _normalize(row) if row else None


async def create(user_id: int, day: str, note: Optional[str], auto: bool) -> Optional[dict]:
    """插入打卡。命中唯一索引时返回 None(调用方判定为「已存在」)。"""
    try:
        new_id = await insert(
            "INSERT INTO checkins (user_id, checkin_date, note, auto) VALUES (%s, %s, %s, %s)",
            (user_id, day, note, 1 if auto else 0),
        )
    except Exception as e:
        # 1062 = Duplicate entry
        if "Duplicate" in str(e) or "1062" in str(e):
            return None
        raise
    if not new_id:
        return None
    return await get_by_date(user_id, day)


async def recent_dates(user_id: int, limit: int = 365) -> list:
    rows = await fetch_all(
        "SELECT DISTINCT checkin_date FROM checkins "
        "WHERE user_id = %s ORDER BY checkin_date DESC LIMIT %s",
        (user_id, limit),
    )
    return [r["checkin_date"] for r in rows]


async def list_recent(user_id: int, since: str) -> list[dict]:
    rows = await fetch_all(
        f"SELECT {COLUMNS} FROM checkins WHERE user_id = %s AND checkin_date >= %s "
        "ORDER BY checkin_date DESC",
        (user_id, since),
    )
    return [_normalize(r) for r in rows]


def _normalize(row: dict) -> dict:
    row["date"] = to_date_str(row.pop("checkin_date", None))
    row["created_at"] = str(row["created_at"]) if row.get("created_at") else None
    row["auto"] = as_int(row.get("auto"))
    return row
