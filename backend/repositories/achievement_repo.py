"""achievements / achievement_definitions 数据访问

Phase 1 重点修复:
- 原 `list_unlocked` 在循环里为每条成就反查 icon → N+1,改成一次 JOIN。
- 原 `_eval_metric` 分散在引擎里,现在统一由 `metric_value()` 一个函数负责,
  方便加缓存(services/achievement_service.py 会按 metric 缓存)。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.database import execute, fetch_all, fetch_one, fetch_value, insert
from repositories.base import as_float, as_int, to_date_str

DEF_COLUMNS = "id, code, name, description, icon, metric_type, target_value, is_active, sort_order"


async def definitions(active_only: bool = True) -> list[dict]:
    sql = f"SELECT {DEF_COLUMNS} FROM achievement_definitions"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY sort_order ASC, id ASC"
    rows = await fetch_all(sql)
    for r in rows:
        r["target_value"] = as_int(r.get("target_value"))
        r["is_active"] = bool(r.get("is_active", 1))
    return rows


async def definition_by_id(ach_id: int) -> Optional[dict]:
    return await fetch_one(f"SELECT {DEF_COLUMNS} FROM achievement_definitions WHERE id = %s", (ach_id,))


async def unlocked_rows(user_id: int) -> list[dict]:
    """已解锁成就 + icon(一次 JOIN,不再每条反查)"""
    rows = await fetch_all(
        """SELECT a.id, a.type, a.name, a.description, a.unlocked_at,
                  COALESCE(d.icon, '🏅') AS icon
           FROM achievements a
           LEFT JOIN achievement_definitions d ON d.code = a.type
           WHERE a.user_id = %s
           ORDER BY a.unlocked_at DESC""",
        (user_id,),
    )
    for r in rows:
        r["unlocked_at"] = str(r["unlocked_at"]) if r.get("unlocked_at") else None
    return rows


async def unlocked_codes(user_id: int) -> set[str]:
    rows = await fetch_all("SELECT type FROM achievements WHERE user_id = %s", (user_id,))
    return {r["type"] for r in rows if r.get("type")}


async def insert_unlock(user_id: int, code: str, name: str, description: str) -> bool:
    """唯一索引 (user_id, type) 已存在时返回 False"""
    try:
        await insert(
            "INSERT INTO achievements (user_id, type, name, description) VALUES (%s, %s, %s, %s)",
            (user_id, code, name, description),
        )
        return True
    except Exception as e:
        if "Duplicate" in str(e) or "1062" in str(e):
            return False
        raise


# ============================================================
# metric 评估 —— 一个 metric 一条 SQL
# ============================================================
async def metric_value(user_id: int, metric_type: str) -> int:
    if metric_type == "todo_count":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s", (user_id,)))
    if metric_type == "done_todo":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s AND done = 1", (user_id,)))
    if metric_type == "goal_count":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s", (user_id,)))
    if metric_type == "done_goal":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s AND done = 1", (user_id,)))
    if metric_type == "tx_count":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM transactions WHERE user_id = %s", (user_id,)))
    if metric_type == "tx_income_total":
        return as_int(await fetch_value(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE user_id = %s AND type='income'",
            (user_id,)))
    if metric_type == "tx_expense_total":
        return as_int(await fetch_value(
            "SELECT COALESCE(SUM(ABS(amount)),0) AS s FROM transactions WHERE user_id = %s AND type='expense'",
            (user_id,)))
    if metric_type == "meal_count":
        return as_int(await fetch_value("SELECT COUNT(*) AS c FROM meals WHERE user_id = %s", (user_id,)))
    if metric_type == "early_reminder":
        return as_int(await fetch_value(
            "SELECT COUNT(*) AS c FROM reminders WHERE user_id = %s AND enabled = 1 AND TIME(time) < '07:00:00'",
            (user_id,)))
    if metric_type == "consecutive_checkin":
        from repositories import todo_repo
        return _streak_from_dates(await todo_repo.distinct_done_dates(user_id))
    return 0


def _streak_from_dates(dates: list) -> int:
    if not dates:
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak


SUPPORTED_METRICS = {
    "todo_count", "done_todo", "goal_count", "done_goal",
    "tx_count", "tx_income_total", "tx_expense_total",
    "meal_count", "early_reminder", "consecutive_checkin",
}
