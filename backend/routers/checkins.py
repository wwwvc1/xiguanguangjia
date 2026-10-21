"""打卡 API

- POST /api/checkins              当天打卡(幂等)
- GET  /api/checkins              列出最近 N 天
- GET  /api/checkins/streak       当前连续打卡天数
- GET  /api/checkins/today        今日是否已打卡

改造点:
- streak 算法统一到 services/checkin_service.py(原来有三份)
- 不再用 `run_in_executor` + 同步连接
- 手动打卡触发的成就评估改为 BackgroundTasks,响应不等它
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from services import achievement_service, checkin_service
from utils.deps import get_current_user

log = logging.getLogger("routers.checkins")

router = APIRouter(prefix="/api/checkins", tags=["checkins"])


class CheckinCreate(BaseModel):
    note: Optional[str] = None
    auto: bool = False


async def _sync_achievements_bg(user_id: int) -> None:
    """后台任务:评估成就,失败只记日志"""
    try:
        await achievement_service.sync_user(user_id)
    except Exception as e:
        log.warning("后台成就评估失败(user=%s): %s", user_id, e)


@router.post("")
@router.post("/")
async def do_checkin(
    payload: CheckinCreate,
    background: BackgroundTasks,
    current_user: int = Depends(get_current_user),
):
    result = await checkin_service.do_checkin(current_user, payload.note, payload.auto)
    # auto=True 是前端静默打卡,不需要解锁提示;手动打卡则后台评估
    if not payload.auto and not result["already"]:
        background.add_task(_sync_achievements_bg, current_user)
    return result


@router.get("/today")
async def today_status(current_user: int = Depends(get_current_user)):
    return await checkin_service.today_status(current_user)


@router.get("")
@router.get("/")
async def list_recent(
    days: int = Query(30, ge=1, le=365),
    current_user: int = Depends(get_current_user),
):
    return await checkin_service.list_recent(current_user, days)


@router.get("/streak")
async def get_streak(current_user: int = Depends(get_current_user)):
    return await checkin_service.get_streak(current_user)
