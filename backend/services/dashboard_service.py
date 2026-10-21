"""首页仪表盘业务

改造前首页一次 onShow 打 **7 个请求**(6 个 Promise.all + 1 个自动打卡 POST),
每个都要过一次 JWT 校验,服务端各跑各的 SQL。
其中 `/todos?done=false` 和 `/todos?done=true` 查的还是同一张表。

改造后:
- 单个 `GET /api/dashboard` 返回首页所需全部字段
- 服务端用 `asyncio.gather` 并发跑 5 条轻查询(不是 7 次 HTTP 往返)
- 整包缓存 60s,配版本号失效
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional

from core import cache
from core.config import settings
from repositories import checkin_repo, meal_repo, misc_repo, todo_repo, transaction_repo
from services import checkin_service

log = logging.getLogger("services.dashboard")

DASH_DOMAINS = ("todo", "tx", "meal", "checkin", "settings")


async def build_dashboard(user_id: int, day: Optional[str] = None) -> dict:
    today = day or date.today().strftime("%Y-%m-%d")
    key = cache.cache_key("dash", user_id, today)
    return await cache.acached(
        key, settings.CACHE_TTL_DASHBOARD,
        lambda: _build(user_id, today),
        user_id=user_id, domains=DASH_DOMAINS,
    ) or {}


async def _build(user_id: int, today: str) -> dict:
    # 5 条查询并发跑在同一个异步池上
    todos_task = todo_repo.list_for_user(user_id, done=None, on_date=today)
    tx_task = transaction_repo.daily_stats(user_id, today)
    checkin_task = checkin_repo.recent_dates(user_id, limit=365)
    cal_task = meal_repo.calories_on(user_id, today)
    settings_task = misc_repo.get_settings(user_id)

    todos, tx, checkin_dates, calories, user_settings = await asyncio.gather(
        todos_task, tx_task, checkin_task, cal_task, settings_task,
        return_exceptions=True,
    )

    # 单个查询失败不应该让整个首页失败,给出降级值
    if isinstance(todos, BaseException):
        log.warning("dashboard todos 查询失败(user=%s): %s", user_id, todos)
        todos = []
    if isinstance(tx, BaseException):
        log.warning("dashboard tx 查询失败(user=%s): %s", user_id, tx)
        tx = {"income": 0.0, "expense": 0.0, "net": 0.0}
    if isinstance(checkin_dates, BaseException):
        checkin_dates = []
    if isinstance(calories, BaseException):
        calories = 0
    if isinstance(user_settings, BaseException):
        user_settings = {"target_calories": misc_repo.DEFAULT_CALORIES, "home_layout": None}

    pending = [t for t in todos if not t["done"]]
    completed = [t for t in todos if t["done"]]
    total = len(pending) + len(completed)
    completion_rate = round(len(completed) / total * 100) if total else 0

    streak_info = checkin_service.compute_streak(checkin_dates)
    goal = int(user_settings.get("target_calories") or misc_repo.DEFAULT_CALORIES)
    layout = user_settings.get("home_layout")

    return {
        "date": today,
        "todos": pending,
        "completed": completed,
        "completed_count": len(completed),
        "total_today": total,
        "completion_rate": completion_rate,
        "income": tx.get("income", 0.0),
        "expense": tx.get("expense", 0.0),
        "net": tx.get("net", 0.0),
        # 兼容旧字段名,前端可以增量迁移
        "today_income": tx.get("income", 0.0),
        "today_expense": tx.get("expense", 0.0),
        "today_net": tx.get("net", 0.0),
        "streak": streak_info["streak"],
        "today_checked": streak_info["today_checked"],
        "calories": int(calories or 0),
        "today_calories": int(calories or 0),
        "calorie_goal": goal,
        "settings": user_settings,
        "layout": layout if isinstance(layout, list) else None,
    }
