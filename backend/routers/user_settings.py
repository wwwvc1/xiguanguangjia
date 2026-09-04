"""用户设置 API (异步版)"""
import json
from fastapi import APIRouter, Depends, HTTPException
from aiomysql import DictCursor
from database import get_conn
from models.user_setting import UserSettingResponse, UserSettingUpdate
from utils.deps import get_current_user

router = APIRouter(prefix="/api/user", tags=["user_settings"])

DEFAULT_CALORIES = 1800


async def _parse_home_layout(row):
    """MySQL JSON 列读出来是 str,parse 成 list"""
    if row.get("home_layout") and isinstance(row["home_layout"], str):
        try:
            row["home_layout"] = json.loads(row["home_layout"])
        except Exception:
            row["home_layout"] = None
    return row


@router.get("/settings", response_model=UserSettingResponse)
async def get_user_settings(current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            # 懒初始化
            await cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (current_user,))
            if not await cur.fetchone():
                await cur.execute(
                    "INSERT INTO user_settings (user_id, target_calories) VALUES (%s, %s)",
                    (current_user, DEFAULT_CALORIES)
                )
                await conn.commit()
            await cur.execute(
                "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
                (current_user,)
            )
            row = await cur.fetchone()
            return await _parse_home_layout(row)


@router.put("/settings", response_model=UserSettingResponse)
async def update_user_settings(payload: UserSettingUpdate, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            # 懒初始化
            await cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (current_user,))
            if not await cur.fetchone():
                await cur.execute(
                    "INSERT INTO user_settings (user_id, target_calories) VALUES (%s, %s)",
                    (current_user, DEFAULT_CALORIES)
                )
                await conn.commit()

            updates = {}
            if payload.target_calories is not None:
                if payload.target_calories < 500 or payload.target_calories > 10000:
                    raise HTTPException(status_code=400, detail="目标热量应在 500-10000 之间")
                updates["target_calories"] = payload.target_calories
            if payload.home_layout is not None:
                updates["home_layout"] = json.dumps(payload.home_layout, ensure_ascii=False)

            if updates:
                set_clause = ", ".join(f"{k} = %s" for k in updates)
                values = list(updates.values()) + [current_user]
                await cur.execute(
                    f"UPDATE user_settings SET {set_clause} WHERE user_id = %s",
                    values
                )
                await conn.commit()

            await cur.execute(
                "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
                (current_user,)
            )
            row = await cur.fetchone()
            return await _parse_home_layout(row)
