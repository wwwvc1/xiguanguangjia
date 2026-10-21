import os, sys
sys.path.insert(0, os.path.abspath("."))
from core import redis_client as rc
from core.config import settings

print("=== 连接 ===")
print("backend :", rc.BACKEND)
print("ping    :", rc.ping())
cli = rc.get_redis()
if cli is None:
    print("!! 无法连接"); raise SystemExit(1)

def info_raw(section):
    # mini 后端没有 info() 封装,直接用命令
    r = rc.raw("INFO", section)
    out = {}
    for line in (r or "").splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out

srv = info_raw("server")
print("=== 服务端 ===")
for k in ("redis_version", "redis_mode", "os", "arch_bits", "process_id", "uptime_in_seconds"):
    print(f"{k:20s}: {srv.get(k)}")

mem = info_raw("memory")
print("=== 内存 ===")
for k in ("used_memory_human", "maxmemory_human", "maxmemory_policy"):
    print(f"{k:20s}: {mem.get(k)}")

st = info_raw("stats")
print("=== 统计 ===")
for k in ("total_connections_received", "total_commands_processed", "keyspace_hits", "keyspace_misses", "expired_keys", "evicted_keys"):
    print(f"{k:26s}: {st.get(k)}")

print("=== 配置 ===")
for key in ("maxmemory", "maxmemory-policy", "save", "appendonly", "timeout", "databases"):
    print(f"{key:20s}: {rc.raw('CONFIG', 'GET', key)}")

print("=== 库大小 ===")
print("DBSIZE :", rc.raw("DBSIZE"))
keys = rc.raw("KEYS", (settings.REDIS_PREFIX + ":*"))
print("本项目的 key 数量 :", len(keys) if keys else 0)
if keys:
    for k in sorted(keys)[:12]:
        print("   ", k)
