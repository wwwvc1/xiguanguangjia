"""meals / meal_items 数据访问

改造点:列表接口原来对每条 meal 再查一次 meal_items(N+1),
这里拆成「两次查询 + 内存归组」。
"""
from __future__ import annotations

from core.database import fetch_all, fetch_value
from repositories.base import as_float, as_int, to_date_str

MEAL_COLUMNS = "id, user_id, meal_type, date, total_calories, created_at"


async def meals_with_items(user_id: int) -> list[dict]:
    meals = await fetch_all(
        f"SELECT {MEAL_COLUMNS} FROM meals WHERE user_id = %s ORDER BY date DESC, id DESC",
        (user_id,),
    )
    if not meals:
        return []

    ids = [m["id"] for m in meals]
    placeholders = ",".join(["%s"] * len(ids))
    items = await fetch_all(
        f"SELECT id, meal_id, name, portion, calories FROM meal_items "
        f"WHERE meal_id IN ({placeholders})",
        tuple(ids),
    )

    by_meal: dict[int, list] = {}
    for it in items:
        by_meal.setdefault(as_int(it["meal_id"]), []).append(it)

    for m in meals:
        m["date"] = to_date_str(m.get("date"))
        m["total_calories"] = as_int(m.get("total_calories"))
        m["items"] = by_meal.get(as_int(m["id"]), [])
    return meals


async def calories_on(user_id: int, day: str) -> int:
    return as_int(await fetch_value(
        "SELECT COALESCE(SUM(total_calories),0) AS c FROM meals WHERE user_id = %s AND date = %s",
        (user_id, day),
    ))


async def calories_by_date(user_id: int, days: int = 60) -> dict[str, float]:
    rows = await fetch_all(
        "SELECT date, SUM(total_calories) AS cal FROM meals "
        "WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) GROUP BY date",
        (user_id, days),
    )
    return {to_date_str(r["date"]): as_float(r["cal"]) for r in rows if r.get("date")}
