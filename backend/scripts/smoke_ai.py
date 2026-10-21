"""AI 链路冒烟测试

重点验证**契约**而非模型质量:
- SSE 事件格式与事件类型(前端只认这些)
- LangChain 改造后不再静默降级到失效 key
- RAG 可检索

外网不通时 LLM 会返回 error 事件 —— 这也是合法结果,只要事件类型对。
"""
import json
import random
import string
import sys

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


def parse_sse(resp):
    events = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            events.append(json.loads(line[6:]))
        except Exception:
            pass
    return events


def rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# 登录
username = f"ai_{rnd()}"
r = requests.post(API + "/auth/register",
                  json={"username": username, "password": "Test@12345", "nickname": "ai"},
                  timeout=15)
if r.status_code != 200:
    r = requests.post(API + "/auth/login-with-password",
                      json={"username": username, "password": "Test@12345"}, timeout=15)
assert r.status_code == 200, r.text[:200]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# ---------- 1. RAG ----------
print("\n== RAG 检索 ==")
r = requests.get(BASE + "/ai/test-rag", params={"query": "怎么坚持早起打卡"}, timeout=90)
check("GET /ai/test-rag", r.status_code == 200, r.text[:100])
if r.status_code == 200:
    body = r.json()
    check("返回 results 字段", "results" in body, f"n={len(body.get('results', []))}")

# ---------- 2. 通用聊天(真流式) ----------
print("\n== /api/ai/chat/general (LangChain astream) ==")
try:
    r = requests.post(API + "/ai/chat/general", headers=H,
                      json={"message": "你好"}, timeout=120, stream=True)
    ctype = r.headers.get("content-type", "")
    check("HTTP 200", r.status_code == 200, str(r.status_code))
    check("content-type 是 SSE", "text/event-stream" in ctype, ctype)
    events = parse_sse(r)
    types = [e.get("type") for e in events]
    check("事件带 type 字段", all(t for t in types) if types else False, str(types[:6]))
    check("有 text_delta 或 error(不是空响应)",
          ("text_delta" in types) or ("error" in types), str(types[:6]))
    if "text_delta" in types:
        check("以 done 收尾", types[-1] == "done", types[-1])
        print("       (模型可用,收到真实回复)")
    else:
        print("       (模型不可达,收到 error 事件 —— 契约正确)")
except Exception as e:
    check("general 请求未抛异常", False, str(e)[:120])

# ---------- 3. 专业 Agent(SSE + 工具) ----------
print("\n== /api/ai/chat/professional (LangChain bind_tools) ==")
try:
    r = requests.post(API + "/ai/chat/professional", headers=H,
                      json={"message": "我有多少待办"}, timeout=120, stream=True)
    check("HTTP 200", r.status_code == 200, str(r.status_code))
    events = parse_sse(r)
    types = [e.get("type") for e in events]
    check("有 text_delta / tool_call / error 之一",
          bool({"text_delta", "tool_call", "error"} & set(types)), str(types[:8]))
except Exception as e:
    check("professional 请求未抛异常", False, str(e)[:120])

# ---------- 4. 不再静默降级 ----------
print("\n== 模型解析不再静默降级 ==")
r = requests.post(API + "/ai/agent", headers=H,
                  json={"message": "你好", "model_id": 999999}, timeout=60)
check("无效 model_id 显式报错(不再偷偷用 .env)",
      r.status_code == 500 and "模型" in r.text, f"{r.status_code} {r.text[:120]}")

# ---------- 5. 有效 model_id 能选中 ----------
r = requests.post(API + "/ai/agent", headers=H,
                  json={"message": "你好", "model_id": 13}, timeout=120)
check("model_id=13 能进入主循环(不是 500 模型不可用)",
      not (r.status_code == 500 and "模型" in r.text),
      f"{r.status_code} {r.text[:120]}")

print("\n" + "=" * 56)
print(f"结果: {ok} 通过, {fail} 失败")
print("=" * 56)
sys.exit(0 if fail == 0 else 1)
