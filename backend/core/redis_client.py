"""Redis 客户端

核心原则:**Redis 是加速层,不是正确性依赖**。

三条硬性设计:
1. `socket_timeout` / `socket_connect_timeout` 必须是短值(默认 0.2s)。
   Redis 一旦卡住,不能让每个请求都白等;超时后立刻降级走 MySQL。
2. **熔断**:连续失败 N 次后短路 M 秒,期间所有缓存调用直接返回 None,
   连网络都不碰。否则 Redis 挂掉时每个请求都要白付一次超时。
3. **后端可替换**:优先用官方 `redis` 包(支持集群/哨兵/异步),
   装不上时自动回退到 `core/mini_redis.py`(纯标准库 RESP2 实现)。
   两者对外方法签名一致,上层无感。

异步变体(`aget_json` 等)在 mini 后端下通过 `asyncio.to_thread` 执行,
避免在事件循环里做阻塞 socket IO。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

from core.config import settings
from core.mini_redis import MiniRedis

log = logging.getLogger("core.redis")

try:  # 优先官方包
    import redis as _redis_lib
    _REDIS_PY = True
except Exception:
    _redis_lib = None
    _REDIS_PY = False

# 后端标识:redis-py / mini / none
BACKEND: Optional[str] = None


# ============================================================
# 熔断状态
# ============================================================
_lock = threading.Lock()
_failures = 0
_circuit_open_until = 0.0
_available: Optional[bool] = None

_sync_client: Any = None
_async_client: Any = None   # 只有 redis-py 后端才有


def _circuit_open() -> bool:
    return time.time() < _circuit_open_until


def _mark_success() -> None:
    global _failures
    with _lock:
        _failures = 0


def _mark_failure(err: Exception | None = None) -> None:
    global _failures, _circuit_open_until
    with _lock:
        _failures += 1
        if _failures >= settings.REDIS_FAILURE_THRESHOLD:
            _circuit_open_until = time.time() + settings.REDIS_CIRCUIT_COOLDOWN
            if _failures == settings.REDIS_FAILURE_THRESHOLD:
                log.warning(
                    "Redis 连续失败 %d 次,熔断 %.0fs(期间缓存直连 MySQL)%s",
                    _failures, settings.REDIS_CIRCUIT_COOLDOWN,
                    f": {err}" if err else "",
                )


def reset_circuit() -> None:
    global _failures, _circuit_open_until
    with _lock:
        _failures = 0
        _circuit_open_until = 0.0


# ============================================================
# 客户端
# ============================================================
def _pool_kwargs() -> dict:
    return dict(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
        health_check_interval=30,
        decode_responses=True,
    )


def get_redis():
    """同步客户端;不可用时返回 None"""
    global _sync_client, BACKEND
    if not settings.REDIS_ENABLED or _circuit_open():
        return None
    if _sync_client is None:
        with _lock:
            if _sync_client is None:
                if _REDIS_PY:
                    pool = _redis_lib.ConnectionPool(**_pool_kwargs())
                    _sync_client = _redis_lib.Redis(connection_pool=pool)
                    BACKEND = "redis-py"
                else:
                    kwargs = _pool_kwargs()
                    kwargs.pop("health_check_interval", None)
                    kwargs.pop("decode_responses", None)
                    _sync_client = MiniRedis(**kwargs)
                    BACKEND = "mini"
                log.info("Redis 后端: %s (%s:%s/%s)",
                         BACKEND, settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
    return _sync_client


async def get_async_redis():
    """异步客户端;mini 后端下返回 None,由调用方走 to_thread"""
    global _async_client
    if not settings.REDIS_ENABLED or not _REDIS_PY or _circuit_open():
        return None
    if _async_client is None:
        import redis.asyncio as _aioredis
        kwargs = _pool_kwargs()
        kwargs.pop("health_check_interval", None)
        _async_client = _aioredis.Redis(**kwargs)
    return _async_client


def ping() -> bool:
    global _available
    cli = get_redis()
    if cli is None:
        _available = False
        return False
    try:
        ok = bool(cli.ping())
        _available = ok
        if ok:
            _mark_success()
        return ok
    except Exception as e:
        _available = False
        _mark_failure(e)
        return False


def init_redis() -> bool:
    """启动自检。失败只警告,不阻塞启动。"""
    if not settings.REDIS_ENABLED:
        log.info("Redis 已通过 REDIS_ENABLED=false 关闭")
        return False
    ok = ping()
    if ok:
        log.info("Redis 连接正常 (backend=%s)", BACKEND)
    else:
        log.warning("Redis 不可用,缓存层降级(应用继续以直连 MySQL 运行)")
    return ok


def status() -> dict:
    return {
        "enabled": settings.REDIS_ENABLED,
        "backend": BACKEND,
        "available": bool(_available) and not _circuit_open(),
        "circuit_open": _circuit_open(),
        "failures": _failures,
    }


def close_redis() -> None:
    global _sync_client, _async_client
    if _sync_client is not None:
        try:
            _sync_client.close()
        except Exception:
            pass
        _sync_client = None
    if _async_client is not None:
        try:
            _async_client.close()
        except Exception:
            pass
        _async_client = None


# ============================================================
# Key
# ============================================================
def rk(*parts: Any) -> str:
    return ":".join([settings.REDIS_PREFIX] + [str(p) for p in parts])


# ============================================================
# 读写(全部兜底,失败只降级不抛)
# ============================================================
def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def get_json(key: str) -> Optional[Any]:
    cli = get_redis()
    if cli is None:
        return None
    try:
        raw = cli.get(key)
        _mark_success()
        return json.loads(raw) if raw else None
    except Exception as e:
        _mark_failure(e)
        return None


def set_json(key: str, value: Any, ttl: int) -> bool:
    cli = get_redis()
    if cli is None:
        return False
    try:
        pipe = cli.pipeline(transaction=False)
        pipe.set(key, _dumps(value))
        if ttl and ttl > 0:
            pipe.expire(key, int(ttl))
        pipe.execute()
        _mark_success()
        return True
    except Exception as e:
        _mark_failure(e)
        return False


def delete(*keys: str) -> int:
    cli = get_redis()
    if cli is None or not keys:
        return 0
    try:
        n = cli.delete(*keys)
        _mark_success()
        return int(n)
    except Exception as e:
        _mark_failure(e)
        return 0


def incr(key: str, amount: int = 1, ttl: Optional[int] = None) -> Optional[int]:
    cli = get_redis()
    if cli is None:
        return None
    try:
        pipe = cli.pipeline(transaction=False)
        pipe.incrby(key, amount)
        if ttl:
            pipe.expire(key, int(ttl))
        res = pipe.execute()
        _mark_success()
        return int(res[0]) if res else None
    except Exception as e:
        _mark_failure(e)
        return None


def set_nx(key: str, value: Any, ttl: int) -> bool:
    """SET key value NX EX ttl —— 分布式锁原语"""
    cli = get_redis()
    if cli is None:
        return False
    try:
        ok = cli.set(key, _dumps(value), nx=True, ex=int(ttl))
        _mark_success()
        return bool(ok)
    except Exception as e:
        _mark_failure(e)
        return False


def mget_int_sync(keys: list[str]) -> list[int]:
    cli = get_redis()
    if cli is None:
        return [0] * len(keys)
    try:
        vals = cli.mget(keys)
        _mark_success()
        return [int(v) if v is not None else 0 for v in vals]
    except Exception as e:
        _mark_failure(e)
        return [0] * len(keys)


# ============================================================
# 通用命令逃生口(给 list/hash 之类用)
# ============================================================
def raw(*args: Any) -> Any:
    """执行任意命令。redis-py 用 execute_command,mini 用 execute。"""
    cli = get_redis()
    if cli is None:
        return None
    try:
        if hasattr(cli, "execute_command"):
            res = cli.execute_command(*args)
        else:
            res = cli.execute(list(args))
        _mark_success()
        return res
    except Exception as e:
        _mark_failure(e)
        return None


async def araw(*args: Any) -> Any:
    cli = await get_async_redis()
    if cli is not None:
        try:
            res = await cli.execute_command(*args)
            _mark_success()
            return res
        except Exception as e:
            _mark_failure(e)
            return None
    return await asyncio.to_thread(raw, *args)


# ============================================================
# 异步变体
# ============================================================
async def aget_json(key: str) -> Optional[Any]:
    cli = await get_async_redis()
    if cli is not None:
        try:
            raw = await cli.get(key)
            _mark_success()
            return json.loads(raw) if raw else None
        except Exception as e:
            _mark_failure(e)
            return None
    return await asyncio.to_thread(get_json, key)


async def aset_json(key: str, value: Any, ttl: int) -> bool:
    cli = await get_async_redis()
    if cli is not None:
        try:
            pipe = cli.pipeline(transaction=False)
            pipe.set(key, _dumps(value))
            if ttl and ttl > 0:
                pipe.expire(key, int(ttl))
            await pipe.execute()
            _mark_success()
            return True
        except Exception as e:
            _mark_failure(e)
            return False
    return await asyncio.to_thread(set_json, key, value, ttl)


async def aincr(key: str, amount: int = 1, ttl: Optional[int] = None) -> Optional[int]:
    cli = await get_async_redis()
    if cli is not None:
        try:
            pipe = cli.pipeline(transaction=False)
            pipe.incrby(key, amount)
            if ttl:
                pipe.expire(key, int(ttl))
            res = await pipe.execute()
            _mark_success()
            return int(res[0]) if res else None
        except Exception as e:
            _mark_failure(e)
            return None
    return await asyncio.to_thread(incr, key, amount, ttl)


async def mget_int(keys: list[str]) -> list[int]:
    cli = await get_async_redis()
    if cli is not None:
        try:
            vals = await cli.mget(keys)
            _mark_success()
            return [int(v) if v is not None else 0 for v in vals]
        except Exception as e:
            _mark_failure(e)
            return [0] * len(keys)
    return await asyncio.to_thread(mget_int_sync, keys)
