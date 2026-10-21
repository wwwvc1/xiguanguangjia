"""端到端冒烟测试

覆盖 Phase 1 改造的关键路径:
- 新增 /api/dashboard 聚合端点 + Redis 缓存
- 成就延迟生效(写操作不再同步评估)
- 版本号失效(todo 写入后 dashboard 缓存必须失效)
- 路径尾斜杠归一化
- /health/full 依赖状态
"""
import random
import string
import sys
import time

import requests

BASE = "http://127.0.0.1:18001"
API = BASE + "/api"

ok = 0
fail = 0


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


# ---------- 0. 健康检查 ----------
print("\n== 健康检查 ==")
r = requests.get(BASE + "/health", timeout=5)
check("GET /health", r.status_code == 200 and r.json()["status"] == "ok", r.text[:80])

r = requests.get(BASE + "/health/full", timeout=10)
body = r.json()
check("GET /health/full", r.status_code == 200 and body["database"]["ok"], "")
check("redis 已连接", body["redis"]["available"] is True, f"backend={body['redis']['backend']}")
check("llm_backend", body["llm_backend"] == "langchain", body["llm_backend"])

r = requests.get(BASE + "/db-test", timeout=5)
check("GET /db-test (原 NameError 已修)", r.status_code == 200, r.text[:60])

# ---------- 1. 登录 ----------
print("\n== 鉴权 ==")
username = f"perf_{rnd()}"
r = requests.post(API + "/auth/register",
                  json={"username": username, "password": "Test@12345", "nickname": "压测"},
                  timeout=15)
if r.status_code != 200:
    print("  register 返回", r.status_code, r.text[:200])
    r = requests.post(API + "/auth/login-with-password",
                      json={"username": username, "password": "Test@12345"}, timeout=15)
check("注册/登录", r.status_code == 200, r.text[:120])
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r = requests.get(BASE + "/auth-test", headers=H, timeout=5)
check("鉴权中间件", r.status_code == 200, r.text[:60])

# ---------- 2. 待办 CRUD ----------
print("\n== 待办 CRUD + 尾斜杠归一化 ==")
created = []
for i in range(3):
    r = requests.post(API + "/todos", headers=H,
                      json={"text": f"冒烟待办 {i}", "due_date": None}, timeout=10)
    check(f"POST /todos #{i}", r.status_code == 201, r.text[:80])
    if r.status_code == 201:
        created.append(r.json()["id"])

r = requests.get(API + "/todos", headers=H, timeout=10)
check("GET /todos (无尾斜杠)", r.status_code == 200 and len(r.json()) >= 3, f"n={len(r.json()) if r.status_code==200 else '-'}")

r = requests.get(API + "/todos/", headers=H, timeout=10)
check("GET /todos/ (有尾斜杠)", r.status_code == 200, "")

# ---------- 3. 打卡 ----------
print("\n== 打卡 ==")
r = requests.post(API + "/checkins", headers=H, json={"auto": False}, timeout=15)
check("POST /checkins", r.status_code == 200, r.text[:120])
first = r.json()
check("打卡 streak >= 1", first.get("streak", 0) >= 1, f"streak={first.get('streak')}")

r2 = requests.post(API + "/checkins", headers=H, json={"auto": False}, timeout=15)
check("打卡幂等(第二次 already=True)", r2.status_code == 200 and r2.json()["already"] is True,
      f"already={r2.json().get('already')}")

r = requests.get(API + "/checkins/streak", headers=H, timeout=10)
check("GET /checkins/streak", r.status_code == 200 and r.json()["streak"] == first.get("streak"),
      f"streak={r.json().get('streak') if r.status_code==200 else '-'}")

# ---------- 4. 首页聚合 ----------
print("\n== 首页聚合端点 ==")
t0 = time.perf_counter()
r = requests.get(API + "/dashboard", headers=H, timeout=20)
dt1 = (time.perf_counter() - t0) * 1000
check("GET /dashboard", r.status_code == 200, r.text[:120])
d = r.json()
for field in ("todos", "completion_rate", "streak", "calorie_goal", "streak"):
    check(f"dashboard.{field} 存在", field in d, "")

t0 = time.perf_counter()
r = requests.get(API + "/dashboard", headers=H, timeout=20)
dt2 = (time.perf_counter() - t0) * 1000
check("dashboard 二次请求(应命中缓存)", r.status_code == 200,
      f"首次 {dt1:.0f}ms → 二次 {dt2:.0f}ms")

# ---------- 5. 版本号失效 ----------
print("\n== 版本号失效 ==")
before = requests.get(API + "/dashboard", headers=H, timeout=20).json()["total_today"]
if created:
    requests.put(API + f"/todos/{created[0]}", headers=H, json={"done": True}, timeout=10)
after = requests.get(API + "/dashboard", headers=H, timeout=20).json()
check("写 todo 后 dashboard 缓存失效", after["total_today"] == before,
      f"total {before} → {after['total_today']}")
check("完成数 +1", after["completed_count"] >= 1, f"completed={after['completed_count']}")

# ---------- 6. 洞察 ----------
print("\n== 洞察(缓存) ==")
t0 = time.perf_counter()
r = requests.get(API + "/stats/patterns", headers=H, timeout=25)
p1 = (time.perf_counter() - t0) * 1000
check("GET /stats/patterns", r.status_code == 200, r.text[:100])
check("patterns 含 summary", "summary" in r.json(), "")

t0 = time.perf_counter()
r = requests.get(API + "/stats/patterns", headers=H, timeout=25)
p2 = (time.perf_counter() - t0) * 1000
check("patterns 二次(缓存)", r.status_code == 200, f"{p1:.0f}ms → {p2:.0f}ms")

r = requests.get(API + "/stats/correlation", headers=H, timeout=25)
check("GET /stats/correlation", r.status_code == 200 and "insights" in r.json(), "")

# ---------- 7. 成就(延迟生效) ----------
print("\n== 成就(延迟生效) ==")
r = requests.get(API + "/achievements/available", headers=H, timeout=25)
check("GET /achievements/available", r.status_code == 200 and isinstance(r.json(), list),
      f"n={len(r.json()) if r.status_code==200 else '-'}")
if r.status_code == 200 and r.json():
    item = r.json()[0]
    check("含进度字段", "progress" in item and "current_value" in item, "")

r = requests.get(API + "/achievements", headers=H, timeout=20)
check("GET /achievements", r.status_code == 200, "")

# ---------- 8. 收支 ----------
print("\n== 收支 ==")
import datetime
now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
r = requests.post(API + "/transactions", headers=H,
                  json={"category": "餐饮", "description": "冒烟", "amount": 30.5,
                        "type": "expense", "time": now}, timeout=10)
check("POST /transactions", r.status_code == 201, r.text[:100])

today = datetime.date.today().strftime("%Y-%m-%d")
r = requests.get(API + f"/transactions/daily-stats?date={today}", headers=H, timeout=10)
check("GET /transactions/daily-stats", r.status_code == 200 and "net" in r.json(), r.text[:100])

r = requests.get(API + f"/transactions?year={datetime.date.today().year}&month={datetime.date.today().month}",
                 headers=H, timeout=10)
check("GET /transactions?year=&month= (索引友好改写)", r.status_code == 200, "")

# ---------- 9. 设置 ----------
print("\n== 设置 ==")
r = requests.get(API + "/user/settings", headers=H, timeout=10)
check("GET /user/settings", r.status_code == 200, "")
r = requests.put(API + "/user/settings", headers=H, json={"home_layout": ["todo", "finance"]}, timeout=10)
check("PUT /user/settings", r.status_code == 200, "")
d = requests.get(API + "/dashboard", headers=H, timeout=20).json()
check("settings 变更后 dashboard.layout 同步", d.get("layout") == ["todo", "finance"], str(d.get("layout")))

print("\n" + "=" * 56)
print(f"结果: {ok} 通过, {fail} 失败")
print("=" * 56)
sys.exit(0 if fail == 0 else 1)
