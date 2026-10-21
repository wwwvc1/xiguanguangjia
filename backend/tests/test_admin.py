"""管理后台 / 小程序端只读接口测试(鉴权已登录)"""
import pytest


def test_list_transactions_admin(api):
    """小程序当前用户的事务"""
    r = api.get(f"{api.base_url}/transactions/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_user_settings(api):
    """用户设置(自动创建 + 读)"""
    r = api.get(f"{api.base_url}/user/settings")
    assert r.status_code == 200
    data = r.json()
    assert "target_calories" in data
    assert "home_layout" in data


def test_update_user_profile(api):
    """更新昵称"""
    r = api.put(f"{api.base_url}/user/profile", json={"nickname": "测试新昵称"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "测试新昵称"
    # 还原
    api.put(f"{api.base_url}/user/profile", json={"nickname": "测试"})


def test_list_goals(api):
    r = api.get(f"{api.base_url}/goals/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_reminders(api):
    r = api.get(f"{api.base_url}/reminders/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_checkins(api):
    r = api.get(f"{api.base_url}/checkins/?days=30")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "count" in data


def test_checkin_streak(api):
    r = api.get(f"{api.base_url}/checkins/streak")
    assert r.status_code == 200
    assert "streak" in r.json()


def test_stats_patterns(api):
    """数据洞察 - 习惯模式"""
    r = api.get(f"{api.base_url}/stats/patterns")
    assert r.status_code == 200


def test_stats_correlation(api):
    """数据洞察 - 关联分析"""
    r = api.get(f"{api.base_url}/stats/correlation")
    assert r.status_code == 200
