"""transactions 表数据访问

Phase 1 重点修复:
- 原 `WHERE YEAR(time)=? AND MONTH(time)=?` 是函数包裹,索引直接失效
  → 改成 `time >= ? AND time < ?` 半开区间,能吃 (user_id, time) 索引。
- 所有按天/月聚合的查询统一走时间区间,不再对列做函数运算。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from repositories.base import as_float, as_int, fetch_all, fetch_one, fetch_value, insert, to_date_str

COLUMNS = "id, user_id, category, description, amount, type, time, created_at"


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = f"{year:04d}-{month:02d}-01 00:00:00"
    if month == 12:
        end = f"{year + 1:04d}-01-01 00:00:00"
    else:
        end = f"{year:04d}-{month + 1:02d}-01 00:00:00"
    return start, end


def _day_range(day: str) -> tuple[str, str]:
    d = datetime.strptime(day[:10], "%Y-%m-%d")
    start = d.strftime("%Y-%m-%d 00:00:00")
    end = (d + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    return start, end


def _normalize(row: dict) -> dict:
    # amount 是 DECIMAL,转 float 给模型层用;
    # time / created_at 保持 datetime,由 FastAPI 序列化。
    row["amount"] = as_float(row.get("amount"))
    return row


async def list_for_user(
    user_id: int,
    type_: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> list[dict]:
    sql = f"SELECT {COLUMNS} FROM transactions WHERE user_id = %s"
    params: list = [user_id]
    if type_:
        sql += " AND type = %s"
        params.append(type_)
    if year is not None and month is not None:
        start, end = _month_range(year, month)
        sql += " AND time >= %s AND time < %s"
        params.extend([start, end])
    sql += " ORDER BY time DESC"
    return [_normalize(r) for r in await fetch_all(sql, params)]


async def get(user_id: int, tx_id: int) -> Optional[dict]:
    row = await fetch_one(f"SELECT {COLUMNS} FROM transactions WHERE id = %s AND user_id = %s",
                          (tx_id, user_id))
    return _normalize(row) if row else None


async def exists(user_id: int, tx_id: int) -> bool:
    return (await fetch_one("SELECT id FROM transactions WHERE id = %s AND user_id = %s",
                            (tx_id, user_id))) is not None


async def create(user_id: int, category: str, description: Optional[str], amount: float,
                 type_: str, time_: datetime | str) -> dict:
    new_id = await insert(
        "INSERT INTO transactions (user_id, category, description, amount, type, time) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, category, description, amount, type_, time_),
    )
    return await get(user_id, new_id) or {"id": new_id}


async def update(user_id: int, tx_id: int, fields: dict) -> Optional[dict]:
    if not fields:
        return await get(user_id, tx_id)
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    await insert(f"UPDATE transactions SET {set_clause} WHERE id = %s AND user_id = %s",
                 list(fields.values()) + [tx_id, user_id])
    return await get(user_id, tx_id)


async def delete(user_id: int, tx_id: int) -> int:
    from core.database import execute
    return await execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))


# ---------------- 聚合 ----------------
async def daily_stats(user_id: int, day: str) -> dict:
    """单日收入/支出/结余(一条 SQL 拿完,原来要跑两次 SUM)"""
    start, end = _day_range(day)
    row = await fetch_one(
        """SELECT
             COALESCE(SUM(CASE WHEN type = 'income'  THEN amount ELSE 0 END), 0) AS income,
             COALESCE(SUM(CASE WHEN type = 'expense' THEN ABS(amount) ELSE 0 END), 0) AS expense
           FROM transactions
           WHERE user_id = %s AND time >= %s AND time < %s""",
        (user_id, start, end),
    )
    income = as_float(row.get("income") if row else 0)
    expense = as_float(row.get("expense") if row else 0)
    return {"income": income, "expense": expense, "net": income - expense}


async def monthly_summary(user_id: int, year: int, month: int) -> dict:
    start, end = _month_range(year, month)
    row = await fetch_one(
        """SELECT
             COALESCE(SUM(CASE WHEN type = 'income'  THEN amount ELSE 0 END), 0) AS income,
             COALESCE(SUM(CASE WHEN type = 'expense' THEN ABS(amount) ELSE 0 END), 0) AS expense
           FROM transactions
           WHERE user_id = %s AND time >= %s AND time < %s""",
        (user_id, start, end),
    )
    income = as_float(row.get("income") if row else 0)
    expense = as_float(row.get("expense") if row else 0)
    return {"month": f"{year:04d}-{month:02d}", "income": income, "expense": expense,
            "net": income - expense}


async def category_stats(user_id: int, days: int = 30) -> list[dict]:
    return await fetch_all(
        """SELECT category, type, COUNT(*) AS cnt, SUM(ABS(amount)) AS total
           FROM transactions
           WHERE user_id = %s AND time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
           GROUP BY category, type
           ORDER BY total DESC""",
        (user_id, days),
    )


async def sum_by_type(user_id: int, days: int) -> dict:
    """{type: {count, total}}"""
    rows = await fetch_all(
        """SELECT type, COUNT(*) AS cnt, SUM(ABS(amount)) AS total
           FROM transactions
           WHERE user_id = %s AND time >= DATE_SUB(NOW(), INTERVAL %s DAY)
           GROUP BY type""",
        (user_id, days),
    )
    return {r["type"]: {"count": as_int(r["cnt"]), "total": as_float(r["total"])} for r in rows}


async def expense_by_date(user_id: int, days: int = 60) -> dict[str, float]:
    rows = await fetch_all(
        """SELECT DATE(time) AS dt, SUM(ABS(amount)) AS total
           FROM transactions
           WHERE user_id = %s AND type = 'expense'
             AND time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
           GROUP BY DATE(time)""",
        (user_id, days),
    )
    return {to_date_str(r["dt"]): as_float(r["total"]) for r in rows if r.get("dt")}


async def rows_for_correlation(user_id: int, days: int = 60) -> list[dict]:
    return await fetch_all(
        """SELECT id, category, description, amount, type, time, created_at
           FROM transactions
           WHERE user_id = %s AND time >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
           ORDER BY time DESC""",
        (user_id, days),
    )


async def list_today(user_id: int, day: str) -> list[dict]:
    start, end = _day_range(day)
    rows = await fetch_all(
        f"SELECT {COLUMNS} FROM transactions WHERE user_id = %s AND time >= %s AND time < %s "
        "ORDER BY time DESC",
        (user_id, start, end),
    )
    return [_normalize(r) for r in rows]
