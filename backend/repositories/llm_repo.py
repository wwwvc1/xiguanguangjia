"""llm_models / user_settings.active_model_id 数据访问

同时提供 **同步** 与 **异步** 两套:
- 同步:给仍在 sync 上下文里的调用方(工具链、管理端、LangChain 同步客户端构造)
- 异步:给 async 路由

两边都走连接池,不再每次 `pymysql.connect()`。
"""
from __future__ import annotations

from typing import Optional

from core.database import fetch_all, fetch_one
from repositories.base import as_int

LLM_COLUMNS = ("id, name, base_url, api_key, model_name, is_system_default, "
               "is_active, owner_user_id, created_at, updated_at")


def _normalize(row: Optional[dict]) -> Optional[dict]:
    if row:
        row["is_active"] = bool(row.get("is_active"))
        row["is_system_default"] = bool(row.get("is_system_default"))
    return row


# ============================================================
# 同步
# ============================================================
def _sync_fetch_one(sql: str, params: tuple = ()) -> Optional[dict]:
    from core.database import get_sync_connection
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def _sync_fetch_value(sql: str, params: tuple = ()) -> Optional[dict]:
    return _sync_fetch_one(sql, params)


def model_by_id_sync(model_id: int) -> Optional[dict]:
    return _normalize(_sync_fetch_one(
        f"SELECT {LLM_COLUMNS} FROM llm_models WHERE id = %s", (model_id,)))


def default_model_sync() -> Optional[dict]:
    # ORDER BY id 不能省:如果库里有两条 is_system_default=1
    # (手工跑 UPDATE 很容易造成),不加排序时 LIMIT 1 取哪条是不确定的,
    # 表现就是"改了模型但有时生效有时不生效"。
    row = _sync_fetch_one(
        f"SELECT {LLM_COLUMNS} FROM llm_models "
        "WHERE is_system_default = 1 AND is_active = 1 ORDER BY id LIMIT 1")
    if not row:
        row = _sync_fetch_one(
            f"SELECT {LLM_COLUMNS} FROM llm_models WHERE is_active = 1 ORDER BY id LIMIT 1")
    return _normalize(row)


def active_model_id_sync(user_id: int) -> Optional[int]:
    row = _sync_fetch_one(
        "SELECT active_model_id FROM user_settings WHERE user_id = %s AND active_model_id IS NOT NULL",
        (user_id,))
    return as_int(row["active_model_id"]) if row and row.get("active_model_id") else None


# ============================================================
# 异步
# ============================================================
async def model_by_id(model_id: int) -> Optional[dict]:
    return _normalize(await fetch_one(
        f"SELECT {LLM_COLUMNS} FROM llm_models WHERE id = %s", (model_id,)))


async def default_model() -> Optional[dict]:
    # 同 default_model_sync:ORDER BY id 保证结果确定
    row = await fetch_one(
        f"SELECT {LLM_COLUMNS} FROM llm_models "
        "WHERE is_system_default = 1 AND is_active = 1 ORDER BY id LIMIT 1")
    if not row:
        row = await fetch_one(
            f"SELECT {LLM_COLUMNS} FROM llm_models WHERE is_active = 1 ORDER BY id LIMIT 1")
    return _normalize(row)


async def active_model_id(user_id: int) -> Optional[int]:
    row = await fetch_one(
        "SELECT active_model_id FROM user_settings WHERE user_id = %s AND active_model_id IS NOT NULL",
        (user_id,))
    return as_int(row["active_model_id"]) if row and row.get("active_model_id") else None


async def models_for_user(user_id: int) -> list[dict]:
    rows = await fetch_all(
        f"SELECT {LLM_COLUMNS} FROM llm_models "
        "WHERE is_active = 1 AND (owner_user_id IS NULL OR owner_user_id = %s) "
        "ORDER BY is_system_default DESC, id ASC",
        (user_id,))
    return [_normalize(r) for r in rows]
