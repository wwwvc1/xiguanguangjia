"""pytest 全局 fixture
- 启动/停止后端服务
- 准备测试 token
- 准备测试用户
- 准备随机数据
"""
import os
import sys
import time
import random
import string
import subprocess
import requests
import pytest

# 把项目根目录加到 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://127.0.0.1:8000/api"
TEST_USER_PASSWORD = "Test@12345"


def _random_string(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.fixture(scope="session")
def base_url():
    """API 基础 URL"""
    return BASE_URL


@pytest.fixture(scope="session")
def server():
    """启动/停止后端 uvicorn(测试期间独占)"""
    # 默认用 18001 端口,避免和你开发用的 8000 冲突
    port = 18001
    url = f"http://127.0.0.1:{port}/api"

    env = os.environ.copy()
    # 用测试 DB(可选,如果你没建 test 数据库,就还是用 habit_tracker)
    # env["DB_NAME"] = "habit_tracker_test"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 等服务起来(最多 15 秒)
    for _ in range(30):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/", timeout=1)
            if r.status_code in (200, 404):
                break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("后端启动失败")

    yield url

    # 测试结束 → 停服务
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def test_user(server):
    """注册一个测试用户,返回 (token, user_id)"""
    username = f"test_{_random_string(8)}"
    # 注册
    r = requests.post(
        f"{server}/auth/register",
        json={"username": username, "password": TEST_USER_PASSWORD, "nickname": "测试"},
    )
    if r.status_code == 200:
        return {"token": r.json()["access_token"], "user_id": r.json()["user_id"], "username": username}
    # 失败:可能是已经注册过 → 登录
    r = requests.post(
        f"{server}/auth/login-with-password",
        json={"username": username, "password": TEST_USER_PASSWORD},
    )
    assert r.status_code == 200, f"测试用户失败: {r.text}"
    return {"token": r.json()["access_token"], "user_id": r.json()["user_id"], "username": username}


@pytest.fixture
def auth_headers(test_user):
    """带 token 的请求头"""
    return {"Authorization": f"Bearer {test_user['token']}"}


@pytest.fixture
def api(server, auth_headers):
    """API 客户端,自动带 token"""
    s = requests.Session()
    s.headers.update(auth_headers)
    s.base_url = server
    return s


@pytest.fixture
def admin_headers():
    """管理员 token(用你真实的 admin 账号登录)"""
    r = requests.post(
        f"{BASE_URL}/admin/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    )
    if r.status_code != 200:
        pytest.skip("admin 登录失败,跳过管理员测试")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
