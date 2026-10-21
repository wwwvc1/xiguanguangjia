"""饮食 CRUD 测试"""
import pytest
from datetime import datetime, date


def test_list_meals(api):
    """列饮食"""
    r = api.get(f"{api.base_url}/meals/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_and_get_meal(api):
    """创建 + 查回"""
    today = date.today().isoformat()
    r = api.post(f"{api.base_url}/meals/", json={
        "meal_type": "lunch",
        "date": today,
        "total_calories": 500,
        "items": [
            {"name": "米饭", "portion": "1碗", "calories": 200},
            {"name": "鸡胸肉", "portion": "100g", "calories": 300}
        ]
    })
    assert r.status_code in (200, 201), f"创建失败: {r.text}"
    meal_id = r.json()["id"]

    # 查回
    r2 = api.get(f"{api.base_url}/meals/")
    found = [m for m in r2.json() if m["id"] == meal_id]
    assert len(found) == 1
    assert found[0]["total_calories"] == 500
    assert len(found[0]["items"]) == 2

    # 清理
    api.delete(f"{api.base_url}/meals/{meal_id}")


def test_create_meal_invalid_type(api):
    """meal_type 非法值应 422"""
    r = api.post(f"{api.base_url}/meals/", json={
        "meal_type": "midnight_snack",  # 不在 enum 里
        "date": "2026-09-06",
        "total_calories": 100,
        "items": [{"name": "x", "calories": 100}]
    })
    assert r.status_code in (400, 422)
