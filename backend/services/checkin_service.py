"""打卡业务

改造前 streak 算法有 **三份** 实现:
- routers/checkins.py::_calc_streak(同步连接,跑在 executor 里)
- routers/checkins.py::get_streak(异步)
- routers/stats.py::get_patterns 内联一段

三者对「昨天打过、今天还没打」的处理还不完全一致。现在统一到这里。

幂等三重保障:
1. `checkins(user_id, checkin_date)` 唯一索引(Phase 1 迁移脚本新增)
2. INSERT 捕获 1062 视为「已存在」
3. Redis 锁(SET NX EX)减少并发下的无谓插入尝试
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from core import cache, redis_client as rc
from repositories import checkin_repo

log = logging.getLogger("services.checkin")


# ============================================================
# streak 单一实现
# ============================================================
def compute_streak(dates: list, today: Optional[date] = None, allow_yesterday: bool = True) -> dict:
    """从「打卡日期降序」列表算连续天数。

    allow_yesterday=True:今天没打但昨天打了,仍然算 streak(首页想要的效果)。
    allow_yesterday=False:必须打到今天才算。
    返回 {streak, today_checked, last_date, missed_yesterday}
    """
    today = today or date.today()
    if not dates:
        return {"streak": 0, "today_checked": False, "last_date": None, "missed_yesterday": False}

    last = dates[0]
    if isinstance(last, str):
        last = date.fromisoformat(last[:10])

    missed_yesterday = (last == today - timedelta(days=2))

    if last == today:
        today_checked = True
        start = today
    elif last == today - timedelta(days=1):
        today_checked = False
        if not allow_yesterday:
            return {"streak": 0, "today_checked": False,
                    "last_date": str(last), "missed_yesterday": False}
        start = last
    else:
        return {"streak": 0, "today_checked": False,
                "last_date": str(last), "missed_yesterday": missed_yesterday}

    date_set = set()
    for d in dates:
        date_set.add(date.fromisoformat(d[:10]) if isinstance(d, str) else d)

    streak = 0
    expected = start
    while expected in date_set:
        streak += 1
        expected -= timedelta(days=1)

    return {"streak": streak, "today_checked": today_checked,
            "last_date": str(last), "missed_yesterday": False}


async def get_streak(user_id: int) -> dict:
    dates = await checkin_repo.recent_dates(user_id, limit=365)
    return compute_streak(dates)


async def today_status(user_id: int) -> dict:
    row = await checkin_repo.get_by_date(user_id, date.today().strftime("%Y-%m-%d"))
    return {"checked_in": row is not None, "checkin": row}


# ============================================================
# 打卡
# ============================================================
async def do_checkin(user_id: int, note: Optional[str] = None, auto: bool = False) -> dict:
    """返回 {already, auto, streak, checkin}

    注意:这里**不再**触发成就评估。成就改成延迟生效
    (写操作后由 BackgroundTasks 异步评估,详见 services/achievement_service.py)。
    """
    today = date.today().strftime("%Y-%m-%d")

    lock_key = rc.rk("lock", "checkin", user_id, today)
    got_lock = rc.set_nx(lock_key, 1, ttl=10)
    if not got_lock:
        # 拿不到锁多半是并发重复请求,直接按「已存在」路径处理
        pass

    existing = await checkin_repo.get_by_date(user_id, today)
    if existing:
        streak_info = await get_streak(user_id)
        return {
            "already": True,
            "auto": auto,
            "streak": streak_info["streak"],
            "checkin": existing,
            "newly_unlocked": [],
        }

    created = await checkin_repo.create(user_id, today, note, auto)
    streak_info = await get_streak(user_id)

    if created is None:
        # 并发下被别人抢先插入
        existing = await checkin_repo.get_by_date(user_id, today)
        return {
            "already": True,
            "auto": auto,
            "streak": streak_info["streak"],
            "checkin": existing,
            "newly_unlocked": [],
        }

    await cache.abump(user_id, "checkin", "todo")
    return {
        "already": False,
        "auto": auto,
        "streak": streak_info["streak"],
        "checkin": created,
        "newly_unlocked": [],
    }


async def list_recent(user_id: int, days: int = 30) -> dict:
    since = (date.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    items = await checkin_repo.list_recent(user_id, since)
    return {"items": items, "count": len(items)}
