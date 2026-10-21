"""AI 对话上下文存储

改造前:`routers/ai_general.py` 里一个模块级 `dict`:

    _chat_history: dict[str, list[dict]] = {}

三个问题:
1. 进程重启 → 上下文全丢;
2. 多 worker 部署 → 用户状态忽冷忽热;
3. **永不清理** → 长期运行内存泄漏;
4. 而且代码只读不写(从来没 append 过),等于一直空。

改造后:Redis LIST + LTRIM + TTL;Redis 不可用时回退到**有界**的进程内 dict。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from typing import Any, Optional

from core import redis_client as rc

log = logging.getLogger("services.chat_session")

MAX_TURNS = 10
TTL_SECONDS = 24 * 3600
_MAX_LOCAL_KEYS = 256

# 回退用的进程内存储(有界)
_local: "OrderedDict[str, list[dict]]" = OrderedDict()


def _key(user_id: int, session: str) -> str:
    return rc.rk("chat", user_id, session)


def _push_local(key: str, turn: dict) -> None:
    hist = _local.setdefault(key, [])
    hist.append(turn)
    del hist[:-MAX_TURNS]
    _local.move_to_end(key)
    while len(_local) > _MAX_LOCAL_KEYS:
        _local.popitem(last=False)


def _load_local(key: str) -> list[dict]:
    return list(_local.get(key, []))


# ============================================================
# 读
# ============================================================
def load_history_sync(user_id: int, session: str) -> list[dict]:
    key = _key(user_id, session)
    rows = rc.raw("LRANGE", key, -MAX_TURNS, -1)
    if rows is None:
        return _load_local(key)
    out = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


async def load_history(user_id: int, session: str) -> list[dict]:
    key = _key(user_id, session)
    rows = await rc.araw("LRANGE", key, -MAX_TURNS, -1)
    if rows is None:
        return _load_local(key)
    out = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


# ============================================================
# 写
# ============================================================
def _append_args(key: str, turn: dict) -> list:
    return ["RPUSH", key, json.dumps(turn, ensure_ascii=False, default=str)]


async def append_turn(user_id: int, session: str, user_msg: str, assistant_msg: str) -> None:
    key = _key(user_id, session)
    turn = {"user": user_msg, "assistant": assistant_msg}
    res = await rc.araw(*_append_args(key, turn))
    if res is None:
        _push_local(key, turn)
        return
    await rc.araw("LTRIM", key, -MAX_TURNS, -1)
    await rc.araw("EXPIRE", key, TTL_SECONDS)


async def clear_history(user_id: int, session: str) -> None:
    key = _key(user_id, session)
    _local.pop(key, None)
    await rc.araw("DEL", key)


async def history_as_messages(user_id: int, session: str) -> list[dict]:
    """转成 OpenAI 风格的消息列表(给 LangChain 用)"""
    out = []
    for turn in await load_history(user_id, session):
        if turn.get("user"):
            out.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            out.append({"role": "assistant", "content": turn["assistant"]})
    return out
