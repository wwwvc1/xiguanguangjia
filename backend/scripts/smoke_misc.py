"""其余路由回归(goals / reminders / export / profile / reports)

这些模块没有做业务层重构,但它们共享同一个改造后的连接池。
重点验证:autocommit=True 之后,读写是否仍然正常。
"""
import random
import string
import sys
from datetime import date

import requests

BASE = "http://127.0.0.1:18001"
API = BASE + "/api"
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name} {extra}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {extra}")


def rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


u = f"misc_{rnd()}"
r = requests.post(API + "/auth/register",
                  json={"username": u, "password": "Test@12345", "nickname": "misc"}, timeout=15)
if r.status_code != 200:
    r = requests.post(API + "/auth/login-with-password",
                      json={"username": u, "password": "Test@12345"}, timeout=15)
assert r.status_code == 200, r.text[:300]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

print("\n== 目标 goals ==")
r = requests.post(API + "/goals", headers=H, json={"name": "回归目标", "progress": 0}, timeout=15)
check("POST /goals", r.status_code in (200, 201), f"{r.status_code} {r.text[:100]}")
gid = r.json().get("id") if r.status_code in (200, 201) else None
r = requests.get(API + "/goals", headers=H, timeout=15)
check("GET /goals", r.status_code == 200 and isinstance(r.json(), list), f"n={len(r.json()) if r.status_code==200 else '-'}")
if gid:
    r = requests.put(API + f"/goals/{gid}", headers=H, json={"done": True}, timeout=15)
    check("PUT /goals (读己写)", r.status_code == 200 and r.json().get("done") is True, r.text[:100])
    r = requests.delete(API + f"/goals/{gid}", headers=H, timeout=15)
    check("DELETE /goals", r.status_code == 200, "")

print("\n== 提醒 reminders ==")
r = requests.post(API + "/reminders", headers=H,
                  json={"type": "todo", "time": "08:00:00", "enabled": True}, timeout=15)
check("POST /reminders", r.status_code in (200, 201), f"{r.status_code} {r.text[:100]}")
rid = r.json().get("id") if r.status_code in (200, 201) else None
r = requests.get(API + "/reminders", headers=H, timeout=15)
check("GET /reminders", r.status_code == 200, "")
if rid:
    requests.delete(API + f"/reminders/{rid}", headers=H, timeout=15)

print("\n== 用户资料 profile ==")
r = requests.get(API + "/user/profile", headers=H, timeout=15)
check("GET /user/profile", r.status_code == 200, r.text[:100])
r = requests.put(API + "/user/profile", headers=H, json={"nickname": "回归改名"}, timeout=15)
check("PUT /user/profile", r.status_code == 200 and r.json().get("nickname") == "回归改名", r.text[:100])

print("\n== 导出 export ==")
r = requests.get(API + "/export", headers=H, timeout=20)
check("GET /export", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

print("\n== 报告 reports(空列表) ==")
r = requests.get(API + "/reports", headers=H, timeout=20)
check("GET /reports", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

print("\n" + "=" * 50)
print(f"结果: {ok} 通过, {fail} 失败")
sys.exit(0 if fail == 0 else 1)
