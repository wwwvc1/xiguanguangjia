"""数据访问底座

两套连接管理并存,是为了让「异步化」可以分批推进,而不是一次性大爆炸:

- **异步池(aiomysql)** — 新代码、已迁移的路由走这里。
  用法: `async with get_conn() as conn: async with conn.cursor(DictCursor) as cur: ...`
  也可以用更省事的 `await fetch_all(sql, params)` / `fetch_one` / `execute`。

- **同步池(pymysql)** — 尚未迁移的旧模块走这里。
  关键改动:`get_connection()` 不再每次 `pymysql.connect()`,而是从池里借。
  返回值的 `close()` 被重写为「归还到池」,所以旧代码里
  `conn = get_connection(); try: ... finally: conn.close()` 一行都不用改。

历史上 `get_connection()` 每调一次就是一次 TCP 握手 + MySQL 认证,
25+ 处调用点分布在请求热路径上 —— 这是 Phase 1 修复的核心。
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Iterable, Optional, Sequence

import aiomysql
import pymysql
from aiomysql import DictCursor as AsyncDictCursor
from pymysql.cursors import DictCursor

from core.config import settings

log = logging.getLogger("core.db")

# ============================================================
# 异步池
# ============================================================
_pool: Optional[aiomysql.Pool] = None


async def init_db_pool() -> aiomysql.Pool:
    """FastAPI startup 时调用"""
    global _pool
    if _pool is not None:
        return _pool
    _pool = await aiomysql.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        minsize=settings.DB_POOL_MIN,
        maxsize=settings.DB_POOL_MAX,
        pool_recycle=1800,          # 避免 MySQL wait_timeout 断掉空闲连接
        # ⚠️ 必须 autocommit=True:
        # MySQL 默认隔离级别是 REPEATABLE READ,事务快照在**首条 SELECT** 时建立。
        # 池化连接如果只做过读、从不 commit/rollback,这条连接会永久停留在旧快照上,
        # 之后读到「刚被别的连接插入的行」时返回 None(实测:INSERT 成功后紧接的
        # SELECT 偶发拿不到行,表现为 POST /todos 间歇性 500)。
        # autocommit=True 让每条语句各自成为一个事务,彻底消除悬挂快照;
        # 需要原子性的多语句场景显式用 `async with transaction()`。
        autocommit=True,
    )
    return _pool


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> aiomysql.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_db_pool() first")
    return _pool


def get_conn():
    """异步连接上下文管理器(自动 commit / rollback / 归还)"""
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_db_pool() at startup")
    return _pool.acquire()


@asynccontextmanager
async def cursor():
    """`async with cursor() as cur:` —— 单条语句的省事写法(自动提交)"""
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            yield cur


async def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            await cur.execute(sql, tuple(params or ()))
            return list(await cur.fetchall())


async def fetch_one(sql: str, params: Sequence[Any] | None = None) -> Optional[dict]:
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            await cur.execute(sql, tuple(params or ()))
            return await cur.fetchone()


async def fetch_value(sql: str, params: Sequence[Any] | None = None, default: Any = None) -> Any:
    """取单行第一列,给 COUNT/SUM 这类聚合用"""
    row = await fetch_one(sql, params)
    if not row:
        return default
    return next(iter(row.values()))


async def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    """执行写语句并提交,返回影响行数"""
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            await cur.execute(sql, tuple(params or ()))
            affected = cur.rowcount
        await conn.commit()
        return affected


async def insert(sql: str, params: Sequence[Any] | None = None) -> int:
    """执行 INSERT 并提交,返回自增 id"""
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            await cur.execute(sql, tuple(params or ()))
            new_id = cur.lastrowid
        await conn.commit()
        return int(new_id or 0)


async def executemany(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    async with get_conn() as conn:
        async with conn.cursor(AsyncDictCursor) as cur:
            await cur.executemany(sql, list(seq))
            affected = cur.rowcount
        await conn.commit()
        return int(affected or 0)


# ============================================================
# 同步池(给未迁移的旧模块)
# ============================================================
class _PooledConnection:
    """借自同步池的连接。

    对调用方来说长得和 pymysql.Connection 一模一样(其余属性透传),
    只有 `close()` 的语义变成「归还」。重复 close 是安全的 no-op。
    """

    __slots__ = ("_raw", "_pool", "_released")

    def __init__(self, raw: pymysql.connections.Connection, pool: "SyncConnectionPool"):
        self._raw = raw
        self._pool = pool
        self._released = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        self._pool.release(self._raw)


class SyncConnectionPool:
    """极简线程安全同步连接池(不引入 DBUtils 依赖)。

    - 按需创建,上限 max_size
    - 借出前 `ping(reconnect=True)`,自动救回被 MySQL 断掉的空闲连接
    - 归还时 rollback,清掉未提交的事务残留
    """

    def __init__(self, min_size: int = 2, max_size: int = 12, acquire_timeout: float = 5.0, **conn_kwargs: Any):
        self._min_size = max(0, min_size)
        self._max_size = max(1, max_size)
        self._acquire_timeout = acquire_timeout
        self._conn_kwargs = conn_kwargs
        self._idle: "queue.LifoQueue[pymysql.connections.Connection]" = queue.LifoQueue(maxsize=self._max_size)
        self._created = 0
        self._lock = threading.Lock()
        self._closed = False

    # -- internal -------------------------------------------------
    def _new_conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._conn_kwargs)

    def _try_reuse(self) -> Optional[pymysql.connections.Connection]:
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            return None

    # -- public ---------------------------------------------------
    def acquire(self) -> _PooledConnection:
        if self._closed:
            raise RuntimeError("connection pool is closed")

        while True:
            raw = self._try_reuse()
            if raw is not None:
                try:
                    raw.ping(reconnect=True)
                    return _PooledConnection(raw, self)
                except Exception:
                    # 这个连接废了,丢掉再换一个
                    with self._lock:
                        self._created -= 1
                    try:
                        raw.close()
                    except Exception:
                        pass
                    continue

            with self._lock:
                if self._created < self._max_size:
                    self._created += 1
                    should_create = True
                else:
                    should_create = False

            if should_create:
                try:
                    return _PooledConnection(self._new_conn(), self)
                except Exception:
                    with self._lock:
                        self._created -= 1
                    raise

            # 池满了,等别人归还
            try:
                raw = self._idle.get(timeout=self._acquire_timeout)
            except queue.Empty:
                raise TimeoutError(
                    f"sync DB pool exhausted (max={self._max_size}); "
                    "increase DB_SYNC_POOL_MAX or migrate the caller to async"
                )
            try:
                raw.ping(reconnect=True)
                return _PooledConnection(raw, self)
            except Exception:
                with self._lock:
                    self._created -= 1
                try:
                    raw.close()
                except Exception:
                    pass

    def release(self, raw: pymysql.connections.Connection) -> None:
        if self._closed:
            try:
                raw.close()
            except Exception:
                pass
            return
        try:
            raw.rollback()          # 清掉未提交事务,避免脏状态串到下一个借用者
        except Exception:
            try:
                raw.close()
            except Exception:
                pass
            with self._lock:
                self._created -= 1
            return
        try:
            self._idle.put_nowait(raw)
        except queue.Full:
            try:
                raw.close()
            except Exception:
                pass
            with self._lock:
                self._created -= 1

    def warmup(self) -> None:
        conns = []
        try:
            for _ in range(min(self._min_size, self._max_size)):
                conns.append(self.acquire())
        except Exception as e:  # 预热失败不致命
            log.warning("sync pool warmup failed: %s", e)
        finally:
            for c in conns:
                c.close()

    def close_all(self) -> None:
        self._closed = True
        while True:
            try:
                raw = self._idle.get_nowait()
            except queue.Empty:
                break
            try:
                raw.close()
            except Exception:
                pass

    @property
    def size(self) -> int:
        return self._created


_sync_pool: Optional[SyncConnectionPool] = None
_sync_pool_lock = threading.Lock()


def get_sync_pool() -> SyncConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        with _sync_pool_lock:
            if _sync_pool is None:
                _sync_pool = SyncConnectionPool(
                    min_size=settings.DB_SYNC_POOL_MIN,
                    max_size=settings.DB_SYNC_POOL_MAX,
                    acquire_timeout=5.0,
                    host=settings.DB_HOST,
                    port=settings.DB_PORT,
                    user=settings.DB_USER,
                    password=settings.DB_PASSWORD,
                    database=settings.DB_NAME,
                    charset="utf8mb4",
                    cursorclass=DictCursor,
                    autocommit=False,
                )
    return _sync_pool


def get_sync_connection() -> _PooledConnection:
    """从同步池借一个连接。

    兼容老写法:`conn = get_sync_connection(); try: ... finally: conn.close()`
    `close()` 现在是归还,不是断开。
    """
    return get_sync_pool().acquire()


# 向后兼容别名 —— 大量旧模块用的是这个名字
get_connection = get_sync_connection


def close_sync_pool() -> None:
    global _sync_pool
    if _sync_pool is not None:
        _sync_pool.close_all()
        _sync_pool = None


def init_sync_pool(warmup: bool = True) -> None:
    pool = get_sync_pool()
    if warmup:
        pool.warmup()


# ============================================================
# 事务辅助
# ============================================================
@asynccontextmanager
async def transaction():
    """`async with transaction() as conn:` —— 多条语句同一事务

    池是 autocommit=True,所以这里要显式 `begin()` 把多语句收进同一个事务。
    """
    async with get_conn() as conn:
        await conn.begin()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


def sync_transaction():
    """同步版事务上下文(未迁移模块用)"""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        conn = get_sync_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return _cm()


__all__ = [
    "init_db_pool", "close_db_pool", "get_pool", "get_conn", "cursor",
    "fetch_all", "fetch_one", "fetch_value", "execute", "insert", "executemany",
    "get_sync_pool", "get_sync_connection", "get_connection",
    "init_sync_pool", "close_sync_pool", "transaction", "sync_transaction",
    "SyncConnectionPool",
]
