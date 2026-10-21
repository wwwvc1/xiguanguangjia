"""待办 API

改造点(Phase 1):
1. **成就评估移出同步路径** —— 原来每次 create/update 都要等 `check_and_unlock`
   把 20 条成就定义全量评估一遍(40+ SQL)。现在交给 BackgroundTasks,
   响应立刻返回,评估在后台跑。
2. SQL 全部下沉到 repositories/todo_repo.py,OR 条件改写成 UNION ALL 走索引。
3. 写操作后 bump 缓存版本号,让首页/洞察/成就缓存自动失效。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from core import cache
from models.todo import TodoCreate, TodoCreateBatch, TodoResponse, TodoUpdate
from repositories import todo_repo
from services import achievement_service
from utils.deps import get_current_user

log = logging.getLogger("routers.todos")
router = APIRouter(prefix="/api/todos", tags=["todos"])


class TodoBatchDelete(BaseModel):
    ids: List[int]


async def _sync_achievements_bg(user_id: int) -> None:
    try:
        await achievement_service.sync_user(user_id)
    except Exception as e:
        log.warning("后台成就评估失败(user=%s): %s", user_id, e)


# ---------------- 列表 ----------------
@router.get("", response_model=list[TodoResponse])
@router.get("/", response_model=list[TodoResponse])
async def list_todos(
    current_user: int = Depends(get_current_user),
    done: Optional[bool] = Query(None),
    date: Optional[str] = Query(None, description="筛选指定日期的待办,格式 YYYY-MM-DD"),
):
    return await todo_repo.list_for_user(current_user, done=done, on_date=date)


# ---------------- 创建 ----------------
@router.post("", response_model=TodoResponse, status_code=201)
@router.post("/", response_model=TodoResponse, status_code=201)
async def create_todo(
    todo_data: TodoCreate,
    background: BackgroundTasks,
    current_user: int = Depends(get_current_user),
):
    row = await todo_repo.create(current_user, todo_data.text, todo_data.due_date)
    await cache.abump(current_user, "todo")
    background.add_task(_sync_achievements_bg, current_user)
    return row


@router.post("/batch", response_model=list[TodoResponse], status_code=201)
async def create_todos_batch(
    todo_data: TodoCreateBatch,
    background: BackgroundTasks,
    current_user: int = Depends(get_current_user),
):
    start = datetime.strptime(todo_data.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(todo_data.end_date, "%Y-%m-%d").date()
    if start > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    created = []
    current = start
    while current <= end:
        created.append({"text": todo_data.text, "due_date": str(current)})
        current += timedelta(days=1)

    # 一次性批量插入,不再逐条 await(原来 N 天就是 N 次 round-trip)
    # 用事务保证"要么全进,要么全不进"
    from core.database import transaction
    async with transaction() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                [(current_user, c["text"], c["due_date"]) for c in created],
            )
    await cache.abump(current_user, "todo")
    background.add_task(_sync_achievements_bg, current_user)

    return await todo_repo.list_for_user(current_user, done=False)


# ---------------- 更新 ----------------
@router.put("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: int,
    todo_data: TodoUpdate,
    background: BackgroundTasks,
    current_user: int = Depends(get_current_user),
):
    if not await todo_repo.exists(current_user, todo_id):
        raise HTTPException(status_code=404, detail="待办不存在")

    fields = {}
    if todo_data.text is not None:
        fields["text"] = todo_data.text
    if todo_data.done is not None:
        fields["done"] = 1 if todo_data.done else 0
    if todo_data.due_date is not None:
        fields["due_date"] = todo_data.due_date
    if not fields:
        raise HTTPException(status_code=400, detail="没有提供更新字段")

    row = await todo_repo.update(current_user, todo_id, fields)
    await cache.abump(current_user, "todo")
    if todo_data.done is not None:
        background.add_task(_sync_achievements_bg, current_user)
    return row


# ---------------- 删除 ----------------
@router.delete("/{todo_id}")
async def delete_todo(todo_id: int, current_user: int = Depends(get_current_user)):
    affected = await todo_repo.delete(current_user, todo_id)
    if affected == 0:
        raise HTTPException(status_code=404, detail="待办不存在")
    await cache.abump(current_user, "todo")
    return {"message": "已删除"}


@router.post("/batch-delete")
async def batch_delete_todos(payload: TodoBatchDelete, current_user: int = Depends(get_current_user)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    deleted = await todo_repo.delete_many(current_user, payload.ids)
    await cache.abump(current_user, "todo")
    return {"deleted": deleted, "message": f"已删除 {deleted} 条"}
