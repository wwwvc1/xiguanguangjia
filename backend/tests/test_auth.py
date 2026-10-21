"""登录 / 注册 / token 测试"""
import pytest


@pytest.mark.smoke
def test_wechat_login_creates_user(api):
    """微信登录(测试 mock)— 应能拿到 token"""
    r = api.post(f"{api.base_url}/auth/login", json={"code": "test_smoke_001"})
    assert r.status_code == 200, f"登录失败: {r.text}"
    data = r.json()
    assert "access_token" in data
    assert "user_id" in data
    # mock_user_dev 模式 → 同一 user_id(我们用 code=any 那种)
    # 这里跑测试时用唯一 code,可能创建新用户


@pytest.mark.smoke
def test_register_login_flow(api):
    """注册 → 登录 完整流程"""
    import random, string
    username = f"pytest_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    # 注册
    r = api.post(f"{api.base_url}/auth/register", json={
        "username": username, "password": "Test@12345", "nickname": "pytest"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]

    # 登录
    r2 = api.post(f"{api.base_url}/auth/login-with-password", json={
        "username": username, "password": "Test@12345"
    })
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_register_duplicate_username_fails(api):
    """重复注册应失败"""
    import random, string
    username = f"dup_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    api.post(f"{api.base_url}/auth/register", json={"username": username, "password": "Test@12345"})

    # 第二次注册同 username
    r = api.post(f"{api.base_url}/auth/register", json={"username": username, "password": "Test@12345"})
    assert r.status_code == 409  # conflict


def test_login_wrong_password_fails(api):
    """错误密码应 401"""
    import random, string
    username = f"wrong_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    api.post(f"{api.base_url}/auth/register", json={"username": username, "password": "Test@12345"})

    r = api.post(f"{api.base_url}/auth/login-with-password", json={
        "username": username, "password": "wrong_password"
    })
    assert r.status_code == 401


def test_register_password_too_short(api):
    """密码少于 6 位应 422(校验失败)"""
    import random, string
    username = f"short_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    r = api.post(f"{api.base_url}/auth/register", json={
        "username": username, "password": "123"  # 太短
    })
    assert r.status_code in (400, 422)


def test_unauthorized_access_returns_401(server):
    """无 token 访问应 401"""
    r = requests := __import__("requests").get(f"{server}/todos/")
    assert r.status_code in (401, 403)
