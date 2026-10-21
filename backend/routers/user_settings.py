"""用户设置 API

改造点:
- 走 repositories/misc_repo,不再手写 SQL 与懒初始化
- 写操作 bump "settings" 版本号(首页 layout / 热量目标会跟着更新)
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core import cache
from models.user_setting import UserSettingResponse, UserSettingUpdate
from repositories import misc_repo
from utils.deps import get_current_user

router = APIRouter(prefix="/api/user", tags=["user_settings"])


@router.get("/settings", response_model=UserSettingResponse)
async def get_user_settings(current_user: int = Depends(get_current_user)):
    return await misc_repo.get_settings(current_user)


@router.put("/settings", response_model=UserSettingResponse)
async def update_user_settings(payload: UserSettingUpdate, current_user: int = Depends(get_current_user)):
    # 确保行存在(懒初始化)
    await misc_repo.get_settings(current_user)

    fields = {}
    if payload.target_calories is not None:
        if payload.target_calories < 500 or payload.target_calories > 10000:
            raise HTTPException(status_code=400, detail="目标热量应在 500-10000 之间")
        fields["target_calories"] = payload.target_calories
    if payload.home_layout is not None:
        fields["home_layout"] = json.dumps(payload.home_layout, ensure_ascii=False)

    row = await misc_repo.update_settings(current_user, fields)
    await cache.abump(current_user, "settings")
    return row
