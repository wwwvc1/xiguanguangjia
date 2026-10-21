"""验证:AI 工具写库后,首页缓存是否立即失效

复现用户报的场景:
  1. 打开首页(填充 dashboard 缓存)
  2. 通过 AI 工具加一条待办(模拟 agent 写库)
  3. 再打开首页 —— 必须能立刻看到,不能等 60 秒 TTL
"""
import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from core import cache
from utils.ai_crud_tools import execute_tool

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


u = f"aich_{rnd()}"
r = requests.post(API + "/auth/register",
                  json={"username": u, "password": "Test@12345", "nickname": "ai缓存"}, timeout=15)
if r.status_code != 200:
    r = requests.post(API + "/auth/login-with-password",
                      json={"username": u, "password": "Test@12345"}, timeout=15)
assert r.status_code == 200, r.text[:300]
token = r.json()["access_token"]
uid = r.json()["user_id"]
H = {"Authorization": f"Bearer {token}"}
print(f"测试用户 user_id={uid}")

d1 = requests.get(API + "/dashboard", headers=H, timeout=20).json()
before = d1["total_today"]
v1 = cache.get_versions(uid, ["todo"]).get("todo", 0)
print(f"\n初始: total_today={before}  ver:todo={v1}")

d2 = requests.get(API + "/dashboard", headers=H, timeout=20).json()
check("缓存已预热(两次一致)", d2["total_today"] == before, f"{before} -> {d2['total_today']}")

print("\n通过 execute_tool 加一条待办(AI agent 走的就是这里)...")
res = execute_tool("add_todo", {"text": "AI 生成的待办", "due_date": None}, uid)
check("工具执行成功", not res.get("error"), str(res)[:120])

v2 = cache.get_versions(uid, ["todo"]).get("todo", 0)
check("ver:todo 已自增", v2 > v1, f"{v1} -> {v2}")

d3 = requests.get(API + "/dashboard", headers=H, timeout=20).json()
after = d3["total_today"]
check("首页立即可见(+1,没等 TTL)", after == before + 1, f"{before} -> {after}")

new_texts = [t["text"] for t in d3["todos"]]
check("新待办出现在 todos 里", "AI 生成的待办" in new_texts, str(new_texts[:5]))

v3 = cache.get_versions(uid, ["todo"]).get("todo", 0)
execute_tool("list_todos", {}, uid)
v4 = cache.get_versions(uid, ["todo"]).get("todo", 0)
check("读工具不改版本号", v3 == v4, f"{v3} -> {v4}")

vtx1 = cache.get_versions(uid, ["tx"]).get("tx", 0)
execute_tool("add_transaction", {"category": "餐饮", "description": "AI记账",
                                "amount": 18.5, "type": "expense",
                                "time": "2026-10-21 12:00:00"}, uid)
vtx2 = cache.get_versions(uid, ["tx"]).get("tx", 0)
check("add_transaction 失效 tx 域", vtx2 > vtx1, f"{vtx1} -> {vtx2}")

print("\n" + "=" * 50)
print(f"结果: {ok} 通过, {fail} 失败")
sys.exit(0 if fail == 0 else 1)
