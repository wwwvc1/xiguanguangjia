"""
数据库访问层(异步)
- 启动时建 aiomysql 连接池(min=2, max=10)
- 异步路由用 `async with get_conn() as conn:` 获取连接
- 同步脚本(初始化/迁移)用 `get_sync_connection()`
"""
import aiomysql
import pymysql
from pymysql.cursors import DictCursor
from config import settings

# 全局连接池(async 路由用)
_pool: aiomysql.Pool | None = None


async def init_db_pool() -> aiomysql.Pool:
    """在 FastAPI startup 时调用,创建全局连接池"""
    global _pool
    if _pool is not None:
        return _pool
    _pool = await aiomysql.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset='utf8mb4',
        minsize=2,
        maxsize=10,
        autocommit=False,
    )
    return _pool


async def close_db_pool():
    """在 FastAPI shutdown 时调用"""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_pool() -> aiomysql.Pool:
    """获取已初始化的连接池(同步路由或初始化脚本用)"""
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_db_pool() first")
    return _pool


def get_sync_connection():
    """同步连接 — 仅用于初始化脚本(不通过 pool)"""
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset='utf8mb4',
        cursorclass=DictCursor,
        autocommit=False,
    )


# 向后兼容别名(Phase B/D 改 async 后会删掉)
get_connection = get_sync_connection


# ============================================================
# 异步路由用法:
#   async with get_conn() as conn:        # _pool.acquire() 返回的 context manager
#       async with conn.cursor(DictCursor) as cur:
#           await cur.execute(...)
#           rows = await cur.fetchall()
#   退出 with 块时,aiomysql 自动 commit/rollback + release 回池
# ============================================================

def get_conn():
    """从池拿一个连接的 context manager(直接用 async with)"""
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_db_pool() at startup")
    return _pool.acquire()
