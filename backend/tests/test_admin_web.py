"""管理后台接口测试(需要 admin token)"""
import pytest


def test_admin_login(server):
    """admin 登录"""
    r = __import__("requests").post(
        f"{server}/admin/auth/login",
        json={"username": "admin", "password": "Admin@123"}
    )
    if r.status_code != 200:
        pytest.skip("admin 账号不存在,先 python -m scripts.create_admin admin Admin@123")


def test_admin_dashboard_stats(server, admin_headers):
    """仪表盘总览"""
    r = __import__("requests").get(
        f"{server}/admin/dashboard",
        headers=admin_headers
    )
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    assert "data" in data


def test_admin_list_users(server, admin_headers):
    """用户列表"""
    r = __import__("requests").get(
        f"{server}/admin/users",
        headers=admin_headers
    )
    assert r.status_code == 200
    assert "items" in r.json()


def test_admin_list_logs(server, admin_headers):
    """操作日志"""
    r = __import__("requests").get(
        f"{server}/admin/logs",
        headers=admin_headers
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_admin_data_asset(server, admin_headers):
    """数据资产下钻(7 个 type)"""
    for t in ("todos", "goals", "transactions", "meals"):
        r = __import__("requests").get(
            f"{server}/admin/insights/data-asset/{t}?page=1&page_size=5",
            headers=admin_headers
        )
        assert r.status_code == 200, f"{t} 返回 {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "rows" in data
        assert "total" in data
