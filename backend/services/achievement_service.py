"""成就业务

## 改造前的问题

`check_and_unlock()` 挂在**每个写请求的同步路径**上:
勾一个待办 → 遍历 20 条定义 × (已解锁查询 + metric 全表 COUNT)
≈ 40+ 条 SQL + 1 次新建连接,只为让响应多带一个 `newly_unlocked`。

## 改造后

1. **移出热路径**:写请求只负责返回结果,成就评估交给 BackgroundTasks,
   响应先返回,评估在后台跑。前端在成就页 onShow 时自然能看到新解锁。
2. **metric 缓存**:每个 metric 按「域版本号」缓存(CACHE_TTL_METRIC),
   todos 变了才重算 todo 相关 metric。
3. **只算该算的**:已经解锁的定义直接跳过;同一个 metric_type 只算一次
   (多条定义共享一个 metric 是常见配置)。
4. **单条查询**:每个 metric 一条索引友好 SQL(`WHERE user_id = ?`),
   不再嵌套开 3 个连接。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core import cache
from core.config import settings
from repositories import achievement_repo, todo_repo

log = logging.getLogger("services.achievement")

# metric → 失效域(任一域版本号变化就重算)
METRIC_DOMAIN = {
    "todo_count": "todo",
    "done_todo": "todo",
    "consecutive_checkin": "todo",
    "goal_count": "goal",
    "done_goal": "goal",
    "tx_count": "tx",
    "tx_income_total": "tx",
    "tx_expense_total": "tx",
    "meal_count": "meal",
    "early_reminder": "reminder",
}

ALL_ACH_DOMAINS = ("achievement", "todo", "goal", "tx", "meal", "reminder", "checkin")

# 定义表改动很少,进程内缓存 60s,避免每次请求都查
_defs_cache: tuple[float, list[dict]] | None = None
_DEFS_TTL = 60.0


async def get_definitions(active_only: bool = True, force: bool = False) -> list[dict]:
    global _defs_cache
    now = time.time()
    if not force and _defs_cache and (now - _defs_cache[0]) < _DEFS_TTL:
        defs = _defs_cache[1]
        return [d for d in defs if d["is_active"]] if active_only else defs
    defs = await achievement_repo.definitions(active_only=False)
    _defs_cache = (now, defs)
    return [d for d in defs if d["is_active"]] if active_only else defs


def invalidate_definitions() -> None:
    global _defs_cache
    _defs_cache = None


# ============================================================
# metric(带版本缓存)
# ============================================================
def _metric_key(user_id: int, metric_type: str) -> str:
    return cache.cache_key("metric", user_id, metric_type)


async def metric_cached(user_id: int, metric_type: str) -> int:
    domain = METRIC_DOMAIN.get(metric_type, "todo")
    return await cache.acached(
        _metric_key(user_id, metric_type),
        settings.CACHE_TTL_METRIC,
        lambda: achievement_repo.metric_value(user_id, metric_type),
        user_id=user_id,
        domains=(domain,),
    ) or 0


# ============================================================
# 评估 / 解锁
# ============================================================
async def sync_user(user_id: int) -> list[dict]:
    """评估所有启用定义,写入新解锁记录。返回新解锁列表。"""
    defs = await get_definitions(active_only=True)
    if not defs:
        return []

    unlocked = await achievement_repo.unlocked_codes(user_id)
    pending = [d for d in defs if d["code"] not in unlocked]
    if not pending:
        return []

    # 同一个 metric 只算一次
    needed_metrics = {d["metric_type"] for d in pending if d["metric_type"] in achievement_repo.SUPPORTED_METRICS}
    values: dict[str, int] = {}
    for metric in needed_metrics:
        try:
            values[metric] = await metric_cached(user_id, metric)
        except Exception as e:
            log.warning("metric %s 评估失败(user=%s): %s", metric, user_id, e)

    newly: list[dict] = []
    for d in pending:
        current = values.get(d["metric_type"], 0)
        if current < d["target_value"]:
            continue
        ok = await achievement_repo.insert_unlock(user_id, d["code"], d["name"], d.get("description") or "")
        if ok:
            newly.append({
                "type": d["code"],
                "name": d["name"],
                "description": d.get("description") or "",
                "icon": d.get("icon") or "🏅",
                "just_unlocked": True,
                "current_value": current,
                "target_value": d["target_value"],
                "metric_type": d["metric_type"],
            })

    if newly:
        await cache.abump(user_id, "achievement")
        log.info("user %s 解锁 %d 个成就: %s", user_id, len(newly), [n["type"] for n in newly])
    return newly


def sync_user_sync(user_id: int) -> list[dict]:
    """同步版(给还在 sync 上下文的调用方,如 scheduler)"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(sync_user(user_id))
    # 已在事件循环里 —— 不允许嵌套 run,交给后台任务
    loop.create_task(sync_user(user_id))
    return []


# ============================================================
# 查询(带缓存)
# ============================================================
async def list_unlocked(user_id: int) -> list[dict]:
    key = cache.cache_key("achv", "unlocked", user_id)
    return await cache.acached(
        key, settings.CACHE_TTL_ACHIEVEMENTS,
        lambda: achievement_repo.unlocked_rows(user_id),
        user_id=user_id, domains=ALL_ACH_DOMAINS,
    ) or []


async def list_available(user_id: int, sync: bool = True) -> list[dict]:
    """全部定义 + 解锁状态 + 当前进度。

    sync=True 时先跑一次评估 —— 用户主动打开成就页,顺手把该解锁的补上,
    这样「延迟生效」在体验上等价于「打开时一定是最新」。
    """
    if sync:
        try:
            await sync_user(user_id)
        except Exception as e:
            log.warning("成就评估失败(user=%s): %s", user_id, e)

    key = cache.cache_key("achv", "available", user_id)
    return await cache.acached(
        key, settings.CACHE_TTL_ACHIEVEMENTS,
        lambda: _build_available(user_id),
        user_id=user_id, domains=ALL_ACH_DOMAINS,
    ) or []


async def _build_available(user_id: int) -> list[dict]:
    unlocked_rows = await achievement_repo.unlocked_rows(user_id)
    unlocked_map = {a["type"]: a for a in unlocked_rows}
    defs = await get_definitions(active_only=False)

    # 需要的 metric 一次性算完
    needed = {d["metric_type"] for d in defs
              if d.get("is_active") and d["metric_type"] in achievement_repo.SUPPORTED_METRICS}
    values: dict[str, int] = {}
    for metric in needed:
        try:
            values[metric] = await metric_cached(user_id, metric)
        except Exception:
            values[metric] = 0

    result = []
    for d in defs:
        item = {
            "id": d["id"],
            "code": d["code"],
            "name": d["name"],
            "description": d.get("description"),
            "icon": d.get("icon") or "🏅",
            "metric_type": d["metric_type"],
            "target_value": d["target_value"],
            "is_active": d["is_active"],
            "unlocked": d["code"] in unlocked_map,
        }
        if item["unlocked"]:
            item["unlocked_at"] = unlocked_map[d["code"]].get("unlocked_at")
        if d["is_active"]:
            cur_val = values.get(d["metric_type"], 0)
            item["current_value"] = cur_val
            item["progress"] = min(1.0, cur_val / max(1, d["target_value"]))
        result.append(item)
    return result


async def streak_from_todos(user_id: int) -> int:
    """兼容旧 metric:基于 todos 完成日期的连续天数"""
    return achievement_repo._streak_from_dates(await todo_repo.distinct_done_dates(user_id))
