import os, sys
sys.path.insert(0, os.path.abspath("."))
from core import redis_client as rc

print("ping:", rc.ping(), "| backend:", rc.BACKEND)

# 逐条验证本项目实际用到的命令在 Redis 5.0 上是否可用
tests = [
    ("SETEX  TTL 写入",     lambda: rc.raw("SETEX", "hb:_compat_t", 60, "x")),
    ("GET   读回",          lambda: rc.raw("GET", "hb:_compat_t")),
    ("TTL   读剩余",        lambda: rc.raw("TTL", "hb:_compat_t")),
    ("INCRBY 计数器",       lambda: rc.raw("INCRBY", "hb:_compat_n", 1)),
    ("MGET  批量读",        lambda: rc.raw("MGET", "hb:_compat_n", "hb:_compat_t")),
    ("SET NX EX 锁",        lambda: rc.raw("SET", "hb:_compat_lock", "1", "NX", "EX", 10)),
    ("RPUSH 列表",          lambda: rc.raw("RPUSH", "hb:_compat_l", '{"a":1}')),
    ("LRANGE 负索引",       lambda: rc.raw("LRANGE", "hb:_compat_l", -10, -1)),
    ("LTRIM 截断",          lambda: rc.raw("LTRIM", "hb:_compat_l", -10, -1)),
    ("EXPIRE 设过期",       lambda: rc.raw("EXPIRE", "hb:_compat_l", 60)),
    ("DEL   删除",          lambda: rc.raw("DEL", "hb:_compat_t", "hb:_compat_n", "hb:_compat_lock", "hb:_compat_l")),
]
bad = 0
for name, fn in tests:
    try:
        r = fn()
        print(f"  [OK]   {name:<20} -> {r}")
    except Exception as e:
        bad += 1
        print(f"  [FAIL] {name:<20} -> {e}")
print(f"\n兼容性: {len(tests)-bad}/{len(tests)} 通过" + ("" if bad == 0 else " ⚠️"))
