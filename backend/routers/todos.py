"""
待办 API (异步版)
- 所有路由 async def,SQL 操作前加 await
- 连接通过 get_conn() 异步上下文管理
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List
from aiomysql import DictCursor
from database import get_conn
from models.todo import TodoCreate, TodoCreateBatch, TodoUpdate, TodoResponse
from utils.deps import get_current_user


class TodoBatchDelete(BaseModel):
    ids: List[int]

router = APIRouter(prefix="/api/todos", tags=["todos"])


# --- 列表查询 ---
@router.get("/", response_model=list[TodoResponse])
async def list_todos(
    current_user: int = Depends(get_current_user),
    done: bool | None = Query(None),
    date: str | None = Query(None, description="筛选指定日期的待办，格式YYYY-MM-DD")
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            sql = "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE user_id = %s"
            params = [current_user]
            if done is not None:
                sql += " AND done = %s"
                params.append(done)
            if date is not None:
                sql += " AND (due_date = %s OR due_date IS NULL)"
                params.append(date)
            sql += " ORDER BY created_at DESC"
            await cur.execute(sql, tuple(params))
            rows = await cur.fetchall()
            for row in rows:
                if row.get('due_date'):
                    row['due_date'] = str(row['due_date'])
            return rows


# --- 创建单个待办 ---
@router.post("/", response_model=TodoResponse, status_code=201)
async def create_todo(todo_data: TodoCreate, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                (current_user, todo_data.text, todo_data.due_date)
            )
            todo_id = cur.lastrowid
            await conn.commit()
            await cur.execute(
                "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE id = %s",
                (todo_id,)
            )
            row = await cur.fetchone()
            if row.get('due_date'):
                row['due_date'] = str(row['due_date'])
    # 成就检查(独立连接,不影响响应;此处仍是 sync,在 executor 跑)
    try:
        import asyncio
        from utils.achievement_engine import check_and_unlock
        newly = await asyncio.get_event_loop().run_in_executor(None, check_and_unlock, current_user)
        if newly:
            row["newly_unlocked"] = newly
    except Exception as e:
        print(f"[成就检查] 失败: {e}")
    return row


# --- 批量创建待办(日期区间) ---
@router.post("/batch", response_model=list[TodoResponse], status_code=201)
async def create_todos_batch(todo_data: TodoCreateBatch, current_user: int = Depends(get_current_user)):
    from datetime import datetime, timedelta
    start = datetime.strptime(todo_data.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(todo_data.end_date, "%Y-%m-%d").date()
    if start > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    created = []
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            current = start
            while current <= end:
                await cur.execute(
                    "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                    (current_user, todo_data.text, str(current))
                )
                todo_id = cur.lastrowid
                created.append({
                    "id": todo_id,
                    "text": todo_data.text,
                    "done": False,
                    "due_date": str(current),
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                })
                current += timedelta(days=1)
            await conn.commit()

    return created


# --- 更新 ---
@router.put("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: int,
    todo_data: TodoUpdate,
    current_user: int = Depends(get_current_user)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT id FROM todos WHERE id = %s AND user_id = %s", (todo_id, current_user))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="待办不存在")
            updates = {}
            if todo_data.text is not None:
                updates["text"] = todo_data.text
            if todo_data.done is not None:
                updates["done"] = todo_data.done
            if todo_data.due_date is not None:
                updates["due_date"] = todo_data.due_date
            if not updates:
                raise HTTPException(status_code=400, detail="没有提供更新字段")
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [todo_id]
            await cur.execute(f"UPDATE todos SET {set_clause} WHERE id = %s", values)
            await conn.commit()
            await cur.execute(
                "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE id = %s",
                (todo_id,)
            )
            row = await cur.fetchone()
            if row.get('due_date'):
                row['due_date'] = str(row['due_date'])
    if todo_data.done is not None:
        try:
            import asyncio
            from utils.achievement_engine import check_and_unlock
            newly = await asyncio.get_event_loop().run_in_executor(None, check_and_unlock, current_user)
            if newly:
                row["newly_unlocked"] = newly
        except Exception as e:
            print(f"[成就检查] 失败: {e}")
    return row


# --- 删除 ---
@router.delete("/{todo_id}")
async def delete_todo(todo_id: int, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("DELETE FROM todos WHERE id = %s AND user_id = %s", (todo_id, current_user))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="待办不存在")
            await conn.commit()
            return {"message": "已删除"}


# --- 批量删除 ---
@router.post("/batch-delete")
async def batch_delete_todos(payload: TodoBatchDelete, current_user: int = Depends(get_current_user)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            placeholders = ",".join(["%s"] * len(payload.ids))
            params = tuple(payload.ids) + (current_user,)
            await cur.execute(
                f"DELETE FROM todos WHERE id IN ({placeholders}) AND user_id = %s",
                params
            )
            deleted = cur.rowcount
            await conn.commit()
            return {"deleted": deleted, "message": f"已删除 {deleted} 条"}
