"""todos 表数据访问

Phase 1 重点修复:
- 列表查询原来是 `AND (due_date = %s OR due_date IS NULL)`,
  OR 会让 MySQL 放弃索引 → 改写成 UNION ALL 两个可走索引的分支。
- 所有按 done / due_date 的过滤都能用上新增的复合索引
  `(user_id, done, due_date)`。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from repositories.base import as_int, fetch_all, fetch_one, fetch_value, insert, normalize_row, to_date_str

COLUMNS = "id, text, done, due_date, created_at, updated_at"


async def list_for_user(
    user_id: int,
    done: Optional[bool] = None,
    on_date: Optional[str] = None,
) -> list[dict]:
    """列表查询。

    on_date 给的日期:命中「due_date 正好是那天」或「due_date 为空」(待排期待办)。
    """
    if on_date is None:
        sql = f"SELECT {COLUMNS} FROM todos WHERE user_id = %s"
        params: list = [user_id]
        if done is not None:
            sql += " AND done = %s"
            params.append(1 if done else 0)
        sql += " ORDER BY created_at DESC"
        rows = await fetch_all(sql, params)
    else:
        # 关于写成 OR 还是 UNION ALL:
        # 一开始按「OR 会让索引失效」改成了 UNION ALL,但用 3 万行合成数据实测
        # (scripts/bench_queries.py),在 (user_id, done, due_date) 复合索引下:
        #     OR         0.46 ms
        #     UNION ALL  0.57 ms
        # MySQL 对 OR 会做 index merge,反而少一次排序。所以保留最简洁的写法,
        # 真正的收益来自索引本身(无索引时 47 ms → 有索引 0.46 ms)。
        sql = f"SELECT {COLUMNS} FROM todos WHERE user_id = %s"
        params: list = [user_id]
        if done is not None:
            sql += " AND done = %s"
            params.append(1 if done else 0)
        sql += " AND (due_date = %s OR due_date IS NULL)"
        params.append(on_date)
        sql += " ORDER BY created_at DESC"
        rows = await fetch_all(sql, params)

    for r in rows:
        # due_date 在模型里声明为 str,必须转换;
        # created_at / updated_at 保持 datetime,由 FastAPI 负责序列化。
        r["due_date"] = to_date_str(r.get("due_date"))
    return rows


async def get(user_id: int, todo_id: int) -> Optional[dict]:
    row = await fetch_one(
        f"SELECT {COLUMNS} FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id)
    )
    if row:
        row["due_date"] = to_date_str(row.get("due_date"))
    return row


async def exists(user_id: int, todo_id: int) -> bool:
    row = await fetch_one("SELECT id FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
    return row is not None


async def create(user_id: int, text: str, due_date: Optional[str]) -> dict:
    new_id = await insert(
        "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
        (user_id, text, due_date),
    )
    return await get(user_id, new_id) or {"id": new_id, "text": text, "done": 0, "due_date": due_date}


async def update(user_id: int, todo_id: int, fields: dict) -> Optional[dict]:
    if not fields:
        return await get(user_id, todo_id)
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    await insert(f"UPDATE todos SET {set_clause} WHERE id = %s AND user_id = %s",
                 list(fields.values()) + [todo_id, user_id])
    return await get(user_id, todo_id)


async def delete(user_id: int, todo_id: int) -> int:
    from core.database import execute
    return await execute("DELETE FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))


async def delete_many(user_id: int, ids: list[int]) -> int:
    from core.database import execute
    if not ids:
        return 0
    placeholders = ",".join(["%s"] * len(ids))
    return await execute(
        f"DELETE FROM todos WHERE id IN ({placeholders}) AND user_id = %s",
        tuple(ids) + (user_id,),
    )


# ---------------- 聚合(首页 / 洞察用) ----------------
async def count(user_id: int, done: Optional[bool] = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM todos WHERE user_id = %s"
    params: list = [user_id]
    if done is not None:
        sql += " AND done = %s"
        params.append(1 if done else 0)
    return as_int(await fetch_value(sql, params))


async def done_count_today(user_id: int, on_date: str) -> int:
    """当天完成数:今天有 due_date 且 done=1,或今天更新完成的无日期待办"""
    return as_int(await fetch_value(
        "SELECT COUNT(*) AS c FROM todos WHERE user_id = %s AND done = 1 "
        "AND (due_date = %s OR due_date IS NULL)",
        (user_id, on_date),
    ))


async def list_today(user_id: int, on_date: str) -> tuple[list[dict], list[dict]]:
    """首页一次性拿「未完成」和「已完成」两组,复用同一条 UNION ALL 查询两次太浪费,
    这里用单条 SQL 拿到当天全部,再在 Python 里分组。"""
    rows = await list_for_user(user_id, done=None, on_date=on_date)
    pending = [r for r in rows if not r["done"]]
    completed = [r for r in rows if r["done"]]
    return pending, completed


async def weekday_stats(user_id: int, days: int = 60) -> list[dict]:
    """按星期几聚合完成率(DAYOFWEEK: 1=周日 ... 7=周六)"""
    return await fetch_all(
        """SELECT DAYOFWEEK(due_date) AS dow,
                  COUNT(*) AS total,
                  SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count
           FROM todos
           WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
             AND due_date IS NOT NULL
           GROUP BY DAYOFWEEK(due_date)
           ORDER BY dow""",
        (user_id, days),
    )


async def daily_trend(user_id: int, days: int = 30) -> list[dict]:
    return await fetch_all(
        """SELECT DATE(due_date) AS dt,
                  COUNT(*) AS total,
                  SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count
           FROM todos
           WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
             AND due_date IS NOT NULL
           GROUP BY DATE(due_date)
           ORDER BY dt""",
        (user_id, days),
    )


async def rows_for_correlation(user_id: int, days: int = 60) -> list[dict]:
    """关联分析用:60 天内的 text / done / due_date"""
    return await fetch_all(
        """SELECT DATE(due_date) AS dt, text, done
           FROM todos
           WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
             AND due_date IS NOT NULL""",
        (user_id, days),
    )


async def morning_habit(user_id: int, days: int = 60) -> tuple[int, int]:
    """(早 8 点前创建的已完成数, 早 8 点前创建总数)"""
    rows = await fetch_all(
        """SELECT HOUR(created_at) AS h, done FROM todos
           WHERE user_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)""",
        (user_id, days),
    )
    total = done = 0
    for r in rows:
        if as_int(r.get("h")) < 8:
            total += 1
            if r.get("done"):
                done += 1
    return done, total


async def distinct_done_dates(user_id: int) -> list:
    rows = await fetch_all(
        "SELECT DISTINCT DATE(updated_at) AS d FROM todos "
        "WHERE user_id = %s AND done = 1 AND updated_at IS NOT NULL ORDER BY d DESC",
        (user_id,),
    )
    return [r["d"] for r in rows if r.get("d")]
