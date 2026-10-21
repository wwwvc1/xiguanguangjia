"""目标 API (异步版)

写操作之后必须 bump 缓存版本号(goal 域),
否则首页/洞察会在 TTL 内看到旧数据 —— 和 AI 工具写库是同一类问题。
成就评估改为 BackgroundTasks,不再拖住响应。
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List
from aiomysql import DictCursor
from core import cache
from database import get_conn, get_sync_connection
from models.goal import GoalCreate, GoalUpdate, GoalResponse
from utils.deps import get_current_user

log = logging.getLogger("routers.goals")


class GoalBatchDelete(BaseModel):
    ids: List[int]

router = APIRouter(prefix="/api/goals", tags=["goals"])


async def _sync_achievements_bg(user_id: int) -> None:
    """后台评估成就;失败只记日志,不影响响应"""
    try:
        from services import achievement_service
        await achievement_service.sync_user(user_id)
    except Exception as e:
        log.warning("后台成就评估失败(user=%s): %s", user_id, e)


@router.get("/", response_model=list[GoalResponse])
async def list_goals(
    current_user: int = Depends(get_current_user),
    done: bool | None = Query(None)
):
    from utils.achievement_engine import list_metric_types
    valid_metrics = list_metric_types()
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            if done is not None:
                sql = "SELECT id, name, progress, done, start_date, end_date, linked_metric, created_at, update_time FROM goals WHERE user_id = %s AND done = %s ORDER BY created_at DESC"
                await cur.execute(sql, (current_user, done))
            else:
                sql = "SELECT id, name, progress, done, start_date, end_date, linked_metric, created_at, update_time FROM goals WHERE user_id = %s ORDER BY created_at DESC"
                await cur.execute(sql, (current_user,))
            rows = await cur.fetchall()
    # linked_metric 评估(用 sync 连接跑 — 罕见逻辑,executor 也行)
    for r in rows:
        if r.get("linked_metric") and r["linked_metric"] in valid_metrics:
            target_hint = r.get("target_value_hint")
            if target_hint:
                r["auto_progress"] = min(100, int(
                    _auto_calc_progress(current_user, r["linked_metric"], target_hint)
                ))
    return rows


def _auto_calc_progress(user_id: int, metric_type: str, target_value: int) -> int:
    """根据 metric_type 评估当前值,用于自动算进度(同步,临时用)"""
    from utils.achievement_engine import _eval_metric
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            current = _eval_metric(cur, user_id, metric_type)
    finally:
        conn.close()
    if not target_value or target_value <= 0:
        return 0
    return min(100, int(current * 100 / target_value))


@router.post("/", response_model=GoalResponse, status_code=201)
async def create_goal(goal_data: GoalCreate, background: BackgroundTasks,
                     current_user: int = Depends(get_current_user)):
    if goal_data.start_date and goal_data.end_date and goal_data.start_date > goal_data.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if goal_data.linked_metric:
        from utils.achievement_engine import list_metric_types
        valid = list_metric_types()
        if goal_data.linked_metric not in valid:
            raise HTTPException(400, f"linked_metric 必须是 {sorted(valid)} 之一")
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "INSERT INTO goals (user_id, name, progress, start_date, end_date, linked_metric) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (current_user, goal_data.name, goal_data.progress,
                 goal_data.start_date, goal_data.end_date, goal_data.linked_metric)
            )
            goal_id = cur.lastrowid
            await conn.commit()
            await cur.execute(
                "SELECT id, name, progress, done, start_date, end_date, linked_metric, created_at, update_time "
                "FROM goals WHERE id = %s",
                (goal_id,)
            )
            row = await cur.fetchone()
    await cache.abump(current_user, "goal")
    background.add_task(_sync_achievements_bg, current_user)
    return row


@router.put("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: int,
    goal_data: GoalUpdate,
    background: BackgroundTasks,
    current_user: int = Depends(get_current_user)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT id, start_date, end_date FROM goals WHERE id = %s AND user_id = %s",
                              (goal_id, current_user))
            existing = await cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="目标不存在")
            updates = {}
            if goal_data.name is not None:
                updates["name"] = goal_data.name
            if goal_data.progress is not None:
                updates["progress"] = goal_data.progress
                if goal_data.progress >= 100:
                    updates["done"] = True
            if goal_data.done is not None:
                updates["done"] = goal_data.done
            if goal_data.start_date is not None:
                updates["start_date"] = goal_data.start_date
            if goal_data.end_date is not None:
                updates["end_date"] = goal_data.end_date
            if goal_data.linked_metric is not None:
                updates["linked_metric"] = goal_data.linked_metric
            new_start = goal_data.start_date if goal_data.start_date is not None else existing.get("start_date")
            new_end = goal_data.end_date if goal_data.end_date is not None else existing.get("end_date")
            if new_start and new_end and new_start > new_end:
                raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
            if not updates:
                raise HTTPException(status_code=400, detail="没有提供更新字段")
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [goal_id]
            await cur.execute(f"UPDATE goals SET {set_clause} WHERE id = %s", values)
            await conn.commit()
            await cur.execute(
                "SELECT id, name, progress, done, start_date, end_date, linked_metric, created_at, update_time "
                "FROM goals WHERE id = %s", (goal_id,)
            )
            row = await cur.fetchone()
    await cache.abump(current_user, "goal")
    if goal_data.done is not None or goal_data.progress is not None:
        background.add_task(_sync_achievements_bg, current_user)
    return row


@router.delete("/{goal_id}")
async def delete_goal(goal_id: int, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("DELETE FROM goals WHERE id = %s AND user_id = %s",
                              (goal_id, current_user))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="目标不存在")
            await conn.commit()
    await cache.abump(current_user, "goal")
    return {"message": "已删除"}


@router.post("/batch-delete")
async def batch_delete_goals(payload: GoalBatchDelete, current_user: int = Depends(get_current_user)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            placeholders = ",".join(["%s"] * len(payload.ids))
            params = tuple(payload.ids) + (current_user,)
            await cur.execute(
                f"DELETE FROM goals WHERE id IN ({placeholders}) AND user_id = %s",
                params
            )
            deleted = cur.rowcount
            await conn.commit()
    await cache.abump(current_user, "goal")
    return {"deleted": deleted, "message": f"已删除 {deleted} 条"}
