"""
成就系统 API
- GET /api/achievements - 已解锁的成就
- GET /api/achievements/available - 全部成就(锁定+解锁)
- POST /api/achievements/check - 手动触发检查(返回新解锁的列表)
"""
from fastapi import APIRouter, Depends
from utils.deps import get_current_user
from utils.achievement_engine import list_unlocked, list_available, check_and_unlock

router = APIRouter(prefix="/api/achievements", tags=["achievements"])


@router.get("/")
def get_unlocked(current_user: int = Depends(get_current_user)):
    """获取已解锁的成就列表"""
    return list_unlocked(current_user)


@router.get("/available")
def get_available(current_user: int = Depends(get_current_user)):
    """获取所有成就(含锁定状态)"""
    return list_available(current_user)


@router.post("/check")
def trigger_check(current_user: int = Depends(get_current_user)):
    """手动触发成就检查,返回新解锁的列表"""
    newly = check_and_unlock(current_user)
    return {"newly_unlocked": newly, "count": len(newly)}
