"""首页仪表盘 API

`GET /api/dashboard?date=YYYY-MM-DD`

一次返回首页所有数据,替代原来的 6 个请求。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from services import dashboard_service
from utils.deps import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
@router.get("/")
async def get_dashboard(
    date_: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD,默认今天"),
    current_user: int = Depends(get_current_user),
):
    return await dashboard_service.build_dashboard(current_user, date_)
