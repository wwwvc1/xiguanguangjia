"""成就系统 API

- GET  /api/achievements            已解锁的成就
- GET  /api/achievements/available  全部成就(锁定 + 解锁 + 进度)
- POST /api/achievements/check      手动触发检查

成就评估现在**不在写请求的同步路径上**:
写操作只 bump 版本号,评估由 BackgroundTasks 异步跑;
用户打开成就页时再兜一次底,保证看到的是最新状态。
"""
from fastapi import APIRouter, Depends

from services import achievement_service
from utils.deps import get_current_user

router = APIRouter(prefix="/api/achievements", tags=["achievements"])


@router.get("")
@router.get("/")
async def get_unlocked(current_user: int = Depends(get_current_user)):
    return await achievement_service.list_unlocked(current_user)


@router.get("/available")
async def get_available(current_user: int = Depends(get_current_user)):
    return await achievement_service.list_available(current_user, sync=True)


@router.post("/check")
async def trigger_check(current_user: int = Depends(get_current_user)):
    newly = await achievement_service.sync_user(current_user)
    return {"newly_unlocked": newly, "count": len(newly)}
