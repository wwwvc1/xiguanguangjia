"""JMeter 压测前置 — 创建 1 个测试用户 + 拿 token

用法:
    python scripts/jmeter/setup_data.py

会输出:
    email:    test_jmeter@xxx
    password: Test@12345
    token:    eyJxxx...
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

BASE = "http://127.0.0.1:8000/api"
USERNAME = f"jmeter_{os.getpid()}"
PASSWORD = "Test@12345"

# 注册(失败就登录)
r = requests.post(f"{BASE}/auth/register", json={"username": USERNAME, "password": PASSWORD, "nickname": "JMeter压测"})
if r.status_code != 200:
    r = requests.post(f"{BASE}/auth/login-with-password", json={"username": USERNAME, "password": PASSWORD})

print(f"\n账号: {USERNAME}")
print(f"密码: {PASSWORD}")
print(f"token: {r.json().get('access_token')}")
print(f"user_id: {r.json().get('user_id')}")

# 保存到文件给 JMeter 用
out = {
    "base_url": "http://127.0.0.1:8000",
    "api_base": BASE,
    "username": USERNAME,
    "password": PASSWORD,
    "token": r.json().get("access_token"),
    "user_id": r.json().get("user_id"),
}
with open(os.path.join(os.path.dirname(__file__), "auth.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n保存到: scripts/jmeter/auth.json")
