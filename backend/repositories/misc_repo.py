"""user_settings 数据访问 + 若干兼容转发

注:meals 的访问已独立到 `repositories/meal_repo.py`,
llm_models 的访问已独立到 `repositories/llm_repo.py`。
这里只保留 user_settings,以及给旧调用方的转发别名。
"""
from __future__ import annotations

import json

from core.database import execute, fetch_one
from repositories.llm_repo import (  # noqa: F401  (兼容转发)
    active_model_id as llm_active_model_id,
    default_model as llm_default_model,
    model_by_id as llm_model_by_id,
    models_for_user as llm_models_for_user,
)
from repositories.meal_repo import (  # noqa: F401  (兼容转发)
    calories_by_date, calories_on, meals_with_items,
)

DEFAULT_CALORIES = 1800


def _parse_layout(row: dict) -> dict:
    layout = row.get("home_layout")
    if isinstance(layout, str):
        try:
            row["home_layout"] = json.loads(layout)
        except Exception:
            row["home_layout"] = None
    if row.get("updated_at"):
        row["updated_at"] = str(row["updated_at"])
    return row


async def get_settings(user_id: int) -> dict:
    """读设置;不存在则懒初始化(与改造前接口行为一致)"""
    row = await fetch_one(
        "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
        (user_id,),
    )
    if not row:
        await execute(
            "INSERT IGNORE INTO user_settings (user_id, target_calories) VALUES (%s, %s)",
            (user_id, DEFAULT_CALORIES),
        )
        row = await fetch_one(
            "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
            (user_id,),
        ) or {"user_id": user_id, "target_calories": DEFAULT_CALORIES, "home_layout": None,
              "updated_at": None}
    return _parse_layout(row)


async def update_settings(user_id: int, fields: dict) -> dict:
    if fields:
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        await execute(f"UPDATE user_settings SET {set_clause} WHERE user_id = %s",
                      list(fields.values()) + [user_id])
    return await get_settings(user_id)
