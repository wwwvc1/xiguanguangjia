"""兼容 shim —— 真正的实现现在在 core/database.py

**重要行为变化**:`get_connection()` 不再每次新建 TCP 连接,
而是从同步连接池借, `close()` = 归还。旧调用代码无需修改。

新代码请直接 `from core.database import ...` 或优先用异步接口。
"""
from core.database import (  # noqa: F401
    SyncConnectionPool,
    close_db_pool,
    close_sync_pool,
    cursor,
    execute,
    executemany,
    fetch_all,
    fetch_one,
    fetch_value,
    get_conn,
    get_connection,
    get_pool,
    get_sync_connection,
    get_sync_pool,
    init_db_pool,
    init_sync_pool,
    insert,
    sync_transaction,
    transaction,
)

__all__ = [
    "init_db_pool", "close_db_pool", "get_pool", "get_conn", "cursor",
    "fetch_all", "fetch_one", "fetch_value", "execute", "insert", "executemany",
    "get_sync_pool", "get_sync_connection", "get_connection",
    "init_sync_pool", "close_sync_pool", "transaction", "sync_transaction",
    "SyncConnectionPool",
]
