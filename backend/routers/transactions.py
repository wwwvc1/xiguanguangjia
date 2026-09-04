"""收支 API (异步版)"""
from fastapi import APIRouter, Depends, HTTPException, Query
from aiomysql import DictCursor
from database import get_conn
from models.transaction import TransactionCreate, TransactionUpdate, TransactionResponse
from utils.deps import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    current_user: int = Depends(get_current_user),
    type: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            base_sql = "SELECT id, user_id, category, description, amount, type, time, created_at FROM transactions WHERE user_id = %s"
            params = [current_user]
            if type is not None:
                base_sql += " AND type = %s"
                params.append(type)
            if year is not None and month is not None:
                base_sql += " AND YEAR(time) = %s AND MONTH(time) = %s"
                params.extend([year, month])
            base_sql += " ORDER BY time DESC"
            await cur.execute(base_sql, tuple(params))
            rows = await cur.fetchall()
            for row in rows:
                row["amount"] = float(row["amount"])
            return rows


@router.post("/", response_model=TransactionResponse, status_code=201)
async def create_transaction(tx_data: TransactionCreate, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "INSERT INTO transactions (user_id, category, description, amount, type, time) VALUES (%s, %s, %s, %s, %s, %s)",
                (current_user, tx_data.category, tx_data.description, tx_data.amount, tx_data.type, tx_data.time)
            )
            tx_id = cur.lastrowid
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, category, description, amount, type, time, created_at FROM transactions WHERE id = %s",
                (tx_id,)
            )
            row = await cur.fetchone()
            row["amount"] = float(row["amount"])
            return row


@router.put("/{tx_id}", response_model=TransactionResponse)
async def update_transaction(
    tx_id: int,
    tx_data: TransactionUpdate,
    current_user: int = Depends(get_current_user)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("SELECT id FROM transactions WHERE id = %s AND user_id = %s", (tx_id, current_user))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="交易不存在")
            updates = {}
            if tx_data.category is not None:
                updates["category"] = tx_data.category
            if tx_data.description is not None:
                updates["description"] = tx_data.description
            if tx_data.amount is not None:
                updates["amount"] = tx_data.amount
            if tx_data.type is not None:
                updates["type"] = tx_data.type
            if tx_data.time is not None:
                updates["time"] = tx_data.time
            if not updates:
                raise HTTPException(status_code=400, detail="没有提供更新字段")
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [tx_id]
            await cur.execute(f"UPDATE transactions SET {set_clause} WHERE id = %s", values)
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, category, description, amount, type, time, created_at FROM transactions WHERE id = %s",
                (tx_id,)
            )
            row = await cur.fetchone()
            row["amount"] = float(row["amount"])
            return row


@router.delete("/{tx_id}")
async def delete_transaction(tx_id: int, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (tx_id, current_user))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="交易不存在")
            await conn.commit()
            return {"message": "交易删除成功"}


@router.get("/summary")
async def get_monthly_summary(
    current_user: int = Depends(get_current_user),
    month: str = Query(..., description="月份，格式为YYYY-MM")
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            year, mon = month.split("-")
            date_start = f"{year}-{mon}-01 00:00:00"
            if mon == "12":
                date_end = f"{int(year)+1}-01-01 00:00:00"
            else:
                date_end = f"{year}-{int(mon)+1:02d}-01 00:00:00"
            await cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE user_id = %s AND type = 'income' AND time >= %s AND time < %s",
                (current_user, date_start, date_end)
            )
            income = float((await cur.fetchone())["total"])
            await cur.execute(
                "SELECT COALESCE(SUM(ABS(amount)),0) AS total FROM transactions WHERE user_id = %s AND type = 'expense' AND time >= %s AND time < %s",
                (current_user, date_start, date_end)
            )
            expense = float((await cur.fetchone())["total"])
            return {
                "month": month,
                "income": income,
                "expense": expense,
                "net": income - expense
            }


@router.get("/daily-stats")
async def get_daily_stats(
    current_user: int = Depends(get_current_user),
    date: str = Query(..., description="日期，格式为YYYY-MM-DD")
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            date_start = f"{date} 00:00:00"
            date_end = f"{date} 23:59:59"
            await cur.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE user_id = %s AND type = 'income' AND time >= %s AND time <= %s",
                (current_user, date_start, date_end)
            )
            income = float((await cur.fetchone())["total"])
            await cur.execute(
                "SELECT COALESCE(SUM(ABS(amount)),0) AS total FROM transactions WHERE user_id = %s AND type = 'expense' AND time >= %s AND time <= %s",
                (current_user, date_start, date_end)
            )
            expense = float((await cur.fetchone())["total"])
            return {
                "date": date,
                "income": income,
                "expense": expense,
                "net": income - expense
            }


@router.get("/today", response_model=list[TransactionResponse])
async def get_today_transactions(current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, user_id, category, description, amount, type, time, created_at FROM transactions "
                "WHERE user_id = %s AND DATE(time) = CURDATE() ORDER BY time DESC",
                (current_user,)
            )
            rows = await cur.fetchall()
            for row in rows:
                row["amount"] = float(row["amount"])
            return rows
