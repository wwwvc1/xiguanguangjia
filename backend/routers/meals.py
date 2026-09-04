"""饮食 API (异步版)"""
from fastapi import APIRouter, Depends, HTTPException
from aiomysql import DictCursor
from database import get_conn
from models.meal import MealCreate, MealResponse
from utils.deps import get_current_user

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("/", response_model=list[MealResponse])
async def list_meals(current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, user_id, meal_type, date, total_calories, created_at FROM meals "
                "WHERE user_id = %s ORDER BY date DESC, id DESC",
                (current_user,)
            )
            meals = await cur.fetchall()
            for meal in meals:
                await cur.execute(
                    "SELECT id, meal_id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                    (meal["id"],)
                )
                meal["items"] = await cur.fetchall()
            return meals


@router.post("/", response_model=MealResponse, status_code=201)
async def create_meal(meal_data: MealCreate, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "INSERT INTO meals (user_id, meal_type, date, total_calories) VALUES (%s, %s, %s, %s)",
                (current_user, meal_data.meal_type, meal_data.date, meal_data.total_calories)
            )
            meal_id = cur.lastrowid
            for item in meal_data.items:
                await cur.execute(
                    "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
                    (meal_id, item.name, item.portion, item.calories)
                )
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, meal_type, date, total_calories, created_at FROM meals WHERE id = %s",
                (meal_id,)
            )
            meal = await cur.fetchone()
            await cur.execute(
                "SELECT id, meal_id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                (meal_id,)
            )
            meal["items"] = await cur.fetchall()
            return meal


@router.put("/{meal_id}", response_model=MealResponse)
async def update_meal(
    meal_id: int,
    meal_data: MealCreate,
    current_user: int = Depends(get_current_user)
):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id FROM meals WHERE id = %s AND user_id = %s",
                (meal_id, current_user)
            )
            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="餐次不存在")
            await cur.execute(
                "UPDATE meals SET meal_type = %s, date = %s, total_calories = %s WHERE id = %s",
                (meal_data.meal_type, meal_data.date, meal_data.total_calories, meal_id)
            )
            await cur.execute("DELETE FROM meal_items WHERE meal_id = %s", (meal_id,))
            for item in meal_data.items:
                await cur.execute(
                    "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
                    (meal_id, item.name, item.portion, item.calories)
                )
            await conn.commit()
            await cur.execute(
                "SELECT id, user_id, meal_type, date, total_calories, created_at FROM meals WHERE id = %s",
                (meal_id,)
            )
            meal = await cur.fetchone()
            await cur.execute(
                "SELECT id, meal_id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                (meal_id,)
            )
            meal["items"] = await cur.fetchall()
            return meal


@router.delete("/{meal_id}")
async def delete_meal(meal_id: int, current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute("DELETE FROM meals WHERE id = %s AND user_id = %s", (meal_id, current_user))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="餐次不存在")
            await conn.commit()
            return {"message": "餐次删除成功"}
