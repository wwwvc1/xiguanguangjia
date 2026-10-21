"""数据洞察业务

改造前:`def get_patterns()` 是**同步**路由,里面跑 5 条 60 天范围聚合 SQL,
还要连开同步连接 —— 会把 anyio 线程池占住。
改造后:全异步 + 走连接池 + 结果缓存 300s(这些数字对秒级新鲜度完全不敏感)。

所有按日期过滤的查询都用 `DATE_SUB(CURDATE(), INTERVAL n DAY)` 半开区间,
能吃上 Phase 1 新增的 `(user_id, due_date)` / `(user_id, time)` 索引。
"""
from __future__ import annotations

import logging
from typing import Optional

from core import cache
from core.config import settings
from repositories import transaction_repo, todo_repo, meal_repo
from services import checkin_service

log = logging.getLogger("services.stats")

DOW_MAP = {1: "周日", 2: "周一", 3: "周二", 4: "周三", 5: "周四", 6: "周五", 7: "周六"}


def _to_date_str(d) -> str:
    return str(d)[:10]


# ============================================================
# 习惯模式识别
# ============================================================
async def patterns(user_id: int) -> dict:
    key = cache.cache_key("stats", "patterns", user_id)
    return await cache.acached(
        key, settings.CACHE_TTL_STATS,
        lambda: _build_patterns(user_id),
        user_id=user_id, domains=("todo", "tx", "checkin"),
    ) or {}


async def _build_patterns(user_id: int) -> dict:
    result = {
        "todo_weekday_stats": [],
        "completion_trend": [],
        "tx_category_stats": [],
        "streak_days": 0,
        "summary": {},
    }

    # 1. 按星期几的完成率(过去 60 天)
    for r in await todo_repo.weekday_stats(user_id, 60):
        total = int(r["total"] or 0)
        done = int(r["done_count"] or 0)
        result["todo_weekday_stats"].append({
            "weekday": DOW_MAP.get(r["dow"], str(r["dow"])),
            "dow": r["dow"],
            "total": total,
            "done": done,
            "completion_rate": round(done / total * 100, 1) if total else 0,
        })

    # 2. 30 天完成率趋势
    for r in await todo_repo.daily_trend(user_id, 30):
        total = int(r["total"] or 0)
        done = int(r["done_count"] or 0)
        result["completion_trend"].append({
            "date": _to_date_str(r["dt"]),
            "total": total,
            "done": done,
            "rate": round(done / total * 100, 1) if total else 0,
        })

    # 3. 收支分类统计(过去 30 天)
    for r in await transaction_repo.category_stats(user_id, 30):
        result["tx_category_stats"].append({
            "category": r["category"],
            "type": r["type"],
            "count": int(r["cnt"] or 0),
            "total": float(r["total"] or 0),
        })

    # 4. 连续打卡(统一走 checkin_service,不再内联第三份实现)
    streak_info = await checkin_service.get_streak(user_id)
    result["streak_days"] = streak_info["streak"]

    # 5. 汇总
    total_done = sum(s["done"] for s in result["todo_weekday_stats"])
    total_todos = sum(s["total"] for s in result["todo_weekday_stats"])
    result["summary"] = {
        "overall_completion_rate": round(total_done / total_todos * 100, 1) if total_todos else 0,
        "total_todos_60d": total_todos,
        "streak_days": result["streak_days"],
        "tx_count_30d": sum(s["count"] for s in result["tx_category_stats"]),
    }
    return result


# ============================================================
# 跨维度关联
# ============================================================
EXERCISE_KEYWORDS = ("运动", "跑", "健身", "瑜伽", "打球", "游泳", "锻炼", "步行", "走路")


async def correlation(user_id: int) -> dict:
    key = cache.cache_key("stats", "corr", user_id)
    return await cache.acached(
        key, settings.CACHE_TTL_STATS,
        lambda: _build_correlation(user_id),
        user_id=user_id, domains=("todo", "tx", "meal"),
    ) or {"insights": []}


async def _build_correlation(user_id: int) -> dict:
    result: dict = {"insights": []}

    # 每天是否做了"运动"类待办
    todos_by_date: dict[str, list[dict]] = {}
    for r in await todo_repo.rows_for_correlation(user_id, 60):
        d = _to_date_str(r["dt"])
        todos_by_date.setdefault(d, []).append({
            "text": r.get("text") or "",
            "done": bool(r.get("done")),
        })

    # 1. 运动日 vs 休息日的热量
    cal_by_date = await meal_repo.calories_by_date(user_id, 60)
    exercise_days, rest_days = [], []
    for d, items in todos_by_date.items():
        if d not in cal_by_date:
            continue
        has_exercise = any(
            it["done"] and any(kw in it["text"] for kw in EXERCISE_KEYWORDS)
            for it in items
        )
        (exercise_days if has_exercise else rest_days).append(cal_by_date[d])

    if exercise_days and rest_days:
        avg_ex = sum(exercise_days) / len(exercise_days)
        avg_rest = sum(rest_days) / len(rest_days)
        diff = avg_ex - avg_rest
        if abs(diff) > 50:
            result["insights"].append({
                "title": "运动日 vs 休息日的饮食差异",
                "detail": f"运动日平均摄入 {int(avg_ex)} kcal,休息日 {int(avg_rest)} kcal,差异 {int(abs(diff))} kcal",
                "type": "exercise_calorie",
                "direction": "up" if diff > 0 else "down",
            })

    # 2. 大额支出日 vs 完成率
    expense_by_date = await transaction_repo.expense_by_date(user_id, 60)
    high, low = [], []
    for d, items in todos_by_date.items():
        if not items:
            continue
        exp = expense_by_date.get(d, 0)
        rate = sum(1 for it in items if it["done"]) / len(items)
        (high if exp > 100 else low).append(rate)

    if len(high) >= 3 and len(low) >= 3:
        avg_high = sum(high) / len(high)
        avg_low = sum(low) / len(low)
        if abs(avg_high - avg_low) > 0.15:
            result["insights"].append({
                "title": "支出与待办完成率",
                "detail": f"大额支出日(>¥100)完成率 {int(avg_high*100)}%,普通日 {int(avg_low*100)}%",
                "type": "expense_completion",
                "direction": "down" if avg_high < avg_low else "up",
            })

    # 3. 早起习惯
    morning_done, morning_total = await todo_repo.morning_habit(user_id, 60)
    if morning_total >= 5:
        rate = morning_done / morning_total
        result["insights"].append({
            "title": "早起习惯",
            "detail": f"早起(早 8 点前)创建待办共 {morning_total} 条,完成率 {int(rate*100)}%",
            "type": "morning_habit",
            "rate": rate,
        })

    if not result["insights"]:
        result["insights"].append({
            "title": "数据积累中",
            "detail": "继续记录 2 周,这里会显示你的个性化关联分析",
            "type": "insufficient",
        })
    return result
