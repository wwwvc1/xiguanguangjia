"""收支 API

改造点:
- 删掉了每个请求都 `print` 完整 SQL 的调试代码(生产纯损耗 + 泄敏)
- `YEAR(time)/MONTH(time)` 函数包裹改成时间区间,能吃索引
- daily-stats / summary 各合成一条 SQL(原来跑两次 SUM)
- 写操作 bump 版本号
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core import cache
from models.transaction import TransactionCreate, TransactionResponse, TransactionUpdate
from repositories import transaction_repo
from utils.deps import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionResponse])
@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    current_user: int = Depends(get_current_user),
    type: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    return await transaction_repo.list_for_user(current_user, type, year, month)


@router.post("", response_model=TransactionResponse, status_code=201)
@router.post("/", response_model=TransactionResponse, status_code=201)
async def create_transaction(tx_data: TransactionCreate, current_user: int = Depends(get_current_user)):
    row = await transaction_repo.create(
        current_user, tx_data.category, tx_data.description,
        tx_data.amount, tx_data.type, tx_data.time,
    )
    await cache.abump(current_user, "tx")
    return row


@router.put("/{tx_id}", response_model=TransactionResponse)
async def update_transaction(
    tx_id: int,
    tx_data: TransactionUpdate,
    current_user: int = Depends(get_current_user),
):
    if not await transaction_repo.exists(current_user, tx_id):
        raise HTTPException(status_code=404, detail="交易不存在")

    fields = {}
    for key in ("category", "description", "amount", "type", "time"):
        value = getattr(tx_data, key)
        if value is not None:
            fields[key] = value
    if not fields:
        raise HTTPException(status_code=400, detail="没有提供更新字段")

    row = await transaction_repo.update(current_user, tx_id, fields)
    await cache.abump(current_user, "tx")
    return row


@router.delete("/{tx_id}")
async def delete_transaction(tx_id: int, current_user: int = Depends(get_current_user)):
    affected = await transaction_repo.delete(current_user, tx_id)
    if affected == 0:
        raise HTTPException(status_code=404, detail="交易不存在")
    await cache.abump(current_user, "tx")
    return {"message": "交易删除成功"}


@router.get("/summary")
async def get_monthly_summary(
    month: str = Query(..., description="月份,格式 YYYY-MM"),
    current_user: int = Depends(get_current_user),
):
    try:
        year_s, mon_s = month.split("-")
        year, mon = int(year_s), int(mon_s)
    except Exception:
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
    return await transaction_repo.monthly_summary(current_user, year, mon)


@router.get("/daily-stats")
async def get_daily_stats(
    date: str = Query(..., description="日期,格式 YYYY-MM-DD"),
    current_user: int = Depends(get_current_user),
):
    return await transaction_repo.daily_stats(current_user, date)


@router.get("/today")
async def get_today_transactions(
    date: Optional[str] = Query(None, description="默认今天"),
    current_user: int = Depends(get_current_user),
):
    from datetime import date as _date
    day = date or _date.today().strftime("%Y-%m-%d")
    return await transaction_repo.list_today(current_user, day)
