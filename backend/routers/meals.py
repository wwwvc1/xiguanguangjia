"""饮食 API

改造点:
- 列表接口原来对每条 meal 再查一次 meal_items(N+1),现在两条 SQL 拿完,内存归组。
- 写操作 bump "meal" 版本号,让首页热量与洞察缓存失效。
"""
from fastapi import APIRouter, Depends, HTTPException

from core import cache
from core.database import execute, fetch_all, fetch_one, insert
from models.meal import MealCreate, MealResponse
from repositories import meal_repo
from repositories.base import as_int, to_date_str
from utils.deps import get_current_user

router = APIRouter(prefix="/api/meals", tags=["meals"])

MEAL_COLUMNS = "id, user_id, meal_type, date, total_calories, created_at"


def _normalize(meal: dict | None) -> dict | None:
    if not meal:
        return meal
    meal["date"] = to_date_str(meal.get("date"))
    meal["total_calories"] = as_int(meal.get("total_calories"))
    return meal


async def _items(meal_id: int) -> list[dict]:
    return await fetch_all(
        "SELECT id, meal_id, name, portion, calories FROM meal_items WHERE meal_id = %s",
        (meal_id,),
    )


@router.get("", response_model=list[MealResponse])
@router.get("/", response_model=list[MealResponse])
async def list_meals(current_user: int = Depends(get_current_user)):
    return await meal_repo.meals_with_items(current_user)


@router.post("", response_model=MealResponse, status_code=201)
@router.post("/", response_model=MealResponse, status_code=201)
async def create_meal(meal_data: MealCreate, current_user: int = Depends(get_current_user)):
    meal_id = await insert(
        "INSERT INTO meals (user_id, meal_type, date, total_calories) VALUES (%s, %s, %s, %s)",
        (current_user, meal_data.meal_type, meal_data.date, meal_data.total_calories),
    )
    for item in meal_data.items:
        await insert(
            "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
            (meal_id, item.name, item.portion, item.calories),
        )
    await cache.abump(current_user, "meal")
    meal = _normalize(await fetch_one(f"SELECT {MEAL_COLUMNS} FROM meals WHERE id = %s", (meal_id,)))
    meal["items"] = await _items(meal_id)
    return meal


@router.put("/{meal_id}", response_model=MealResponse)
async def update_meal(meal_id: int, meal_data: MealCreate, current_user: int = Depends(get_current_user)):
    if not await fetch_one("SELECT id FROM meals WHERE id = %s AND user_id = %s", (meal_id, current_user)):
        raise HTTPException(status_code=404, detail="餐次不存在")

    await execute(
        "UPDATE meals SET meal_type = %s, date = %s, total_calories = %s WHERE id = %s",
        (meal_data.meal_type, meal_data.date, meal_data.total_calories, meal_id),
    )
    await execute("DELETE FROM meal_items WHERE meal_id = %s", (meal_id,))
    for item in meal_data.items:
        await insert(
            "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
            (meal_id, item.name, item.portion, item.calories),
        )
    await cache.abump(current_user, "meal")
    meal = _normalize(await fetch_one(f"SELECT {MEAL_COLUMNS} FROM meals WHERE id = %s", (meal_id,)))
    meal["items"] = await _items(meal_id)
    return meal


@router.delete("/{meal_id}")
async def delete_meal(meal_id: int, current_user: int = Depends(get_current_user)):
    affected = await execute("DELETE FROM meals WHERE id = %s AND user_id = %s", (meal_id, current_user))
    if affected == 0:
        raise HTTPException(status_code=404, detail="餐次不存在")
    await cache.abump(current_user, "meal")
    return {"message": "餐次删除成功"}
