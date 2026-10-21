"""缓存 + 版本号失效

## 为什么用版本号,而不是精确 DEL

写操作后要失效的派生缓存往往不止一个:改一笔收支会影响
仪表盘、stats/patterns、stats/correlation、成就进度……

精确 DEL 的问题是「新增缓存时你必然漏一个」,漏了就线上飘脏数据。
版本号方案把失效变成一次 INCR:

    ver:{uid}:tx    ← 任何 transactions 写操作 +1

读取时,缓存里存一份写入当时的版本快照;
对不上就当作未命中回源。写方**不需要知道**有多少派生 key。

代价:偶尔多一次回源(版本变了但内容其实没变)。
收益:漏失效的概率归零。TTL 再兜最后一道底。

版本号本身也存在 Redis 里 —— Redis 挂了缓存层整体降级,
也就不存在「版本对不上但缓存还在」的问题。
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Iterable, Optional

from core import redis_client as rc
from core.config import settings

log = logging.getLogger("core.cache")

# 已知的失效域。新增域在这里登记一处即可。
DOMAINS = (
    "todo", "goal", "tx", "meal", "reminder",
    "checkin", "settings", "achievement", "llm", "report",
)

_ENVELOPE_V = "v"
_ENVELOPE_D = "d"


# ============================================================
# 版本号
# ============================================================
def ver_key(user_id: int, domain: str) -> str:
    return rc.rk("ver", user_id, domain)


def bump(user_id: int, *domains: str, ttl_days: int = 30) -> None:
    """写操作后调用。Redis 不可用时静默跳过(此时缓存也不可用)。"""
    if not domains:
        return
    for d in domains:
        rc.incr(ver_key(user_id, d), 1, ttl=ttl_days * 86400)


async def abump(user_id: int, *domains: str, ttl_days: int = 30) -> None:
    if not domains:
        return
    for d in domains:
        await rc.aincr(ver_key(user_id, d), 1, ttl=ttl_days * 86400)


def get_versions(user_id: int, domains: Iterable[str]) -> dict[str, int]:
    """一次 MGET 拿多个域的版本号。Redis 不可用时返回全 0。"""
    doms = list(domains)
    if not doms:
        return {}
    vals = rc.mget_int_sync([ver_key(user_id, d) for d in doms])
    return dict(zip(doms, vals))


async def aget_versions(user_id: int, domains: Iterable[str]) -> dict[str, int]:
    doms = list(domains)
    if not doms:
        return {}
    vals = await rc.mget_int([ver_key(user_id, d) for d in doms])
    return dict(zip(doms, vals))


def snapshot(user_id: int, *domains: str) -> dict[str, int]:
    return get_versions(user_id, domains)


async def asnapshot(user_id: int, *domains: str) -> dict[str, int]:
    return await aget_versions(user_id, domains)


# ============================================================
# 带版本校验的读写
# ============================================================
def get_cached(key: str, versions: Optional[dict[str, int]] = None) -> Optional[Any]:
    """命中返回数据,未命中或版本不符返回 None"""
    payload = rc.get_json(key)
    if not payload or not isinstance(payload, dict):
        return None
    if versions is not None and payload.get(_ENVELOPE_V) != versions:
        return None
    return payload.get(_ENVELOPE_D)


async def aget_cached(key: str, versions: Optional[dict[str, int]] = None) -> Optional[Any]:
    payload = await rc.aget_json(key)
    if not payload or not isinstance(payload, dict):
        return None
    if versions is not None and payload.get(_ENVELOPE_V) != versions:
        return None
    return payload.get(_ENVELOPE_D)


def set_cached(key: str, data: Any, ttl: int, versions: Optional[dict[str, int]] = None) -> bool:
    return rc.set_json(key, {_ENVELOPE_V: versions, _ENVELOPE_D: data}, ttl)


async def aset_cached(key: str, data: Any, ttl: int, versions: Optional[dict[str, int]] = None) -> bool:
    return await rc.aset_json(key, {_ENVELOPE_V: versions, _ENVELOPE_D: data}, ttl)


# ============================================================
# 便捷包装
# ============================================================
def cached(
    key: str,
    ttl: int,
    loader: Callable[[], Any],
    *,
    user_id: Optional[int] = None,
    domains: Iterable[str] = (),
) -> Any:
    """同步:读缓存 → 未命中则 loader() 并回写"""
    versions = snapshot(user_id, *domains) if (user_id is not None and domains) else None
    hit = get_cached(key, versions)
    if hit is not None:
        return hit
    data = loader()
    if data is not None:
        set_cached(key, data, ttl, versions)
    return data


async def acached(
    key: str,
    ttl: int,
    loader: Callable[[], Awaitable[Any]],
    *,
    user_id: Optional[int] = None,
    domains: Iterable[str] = (),
) -> Any:
    """异步:读缓存 → 未命中则 await loader() 并回写"""
    versions = await asnapshot(user_id, *domains) if (user_id is not None and domains) else None
    hit = await aget_cached(key, versions)
    if hit is not None:
        return hit
    data = await loader()
    if data is not None:
        await aset_cached(key, data, ttl, versions)
    return data


def invalidate(key: str) -> None:
    rc.delete(key)


def cache_key(*parts: Any) -> str:
    return rc.rk(*parts)


__all__ = [
    "DOMAINS", "ver_key", "bump", "abump", "get_versions", "aget_versions",
    "snapshot", "asnapshot", "get_cached", "aget_cached", "set_cached", "aset_cached",
    "cached", "acached", "invalidate", "cache_key",
]
