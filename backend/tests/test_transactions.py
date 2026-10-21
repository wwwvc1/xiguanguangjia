"""收支 CRUD 测试"""
import pytest
from datetime import datetime


def test_create_expense(api):
    """创建支出"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    r = api.post(f"{api.base_url}/transactions/", json={
        "category": "餐饮", "amount": -50, "type": "expense",
        "time": now, "description": "测试"
    })
    assert r.status_code == 200, f"创建失败: {r.text}"
    data = r.json()
    assert data["category"] == "餐饮"
    assert data["type"] == "expense"
    # 清理
    api.delete(f"{api.base_url}/transactions/{data['id']}")


def test_create_income(api):
    """创建收入"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    r = api.post(f"{api.base_url}/transactions/", json={
        "category": "工资", "amount": 5000, "type": "income",
        "time": now
    })
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "income"
    api.delete(f"{api.base_url}/transactions/{data['id']}")


def test_list_transactions_by_month(api):
    """按月份筛选"""
    r = api.get(f"{api.base_url}/transactions/?year=2026&month=9")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_daily_stats(api):
    """每日收支汇总"""
    r = api.get(f"{api.base_url}/transactions/daily-stats?date=2026-09-06")
    assert r.status_code == 200
    data = r.json()
    assert "income" in data and "expense" in data and "net" in data
    assert data["net"] == data["income"] - data["expense"]


def test_summary(api):
    """月度汇总"""
    r = api.get(f"{api.base_url}/transactions/summary?month=2026-09")
    assert r.status_code == 200
    data = r.json()
    assert "income" in data
    assert "expense" in data
    assert "net" in data
