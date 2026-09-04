"""
AI Agent 多轮对话会话管理(进程内)
- 每个 session_id 绑定到具体 user_id(防越权)
- TTL 过期自动清理(默认 1 小时)
- 支持暂存待确认的破坏性动作
"""
import time
import threading
import uuid
from typing import Optional

_LOCK = threading.RLock()
_SESSIONS: dict = {}  # session_id -> session dict

_TTL_SECONDS = 3600  # 1 小时无活动即过期


class SessionNotFound(Exception):
    pass


class SessionPermissionDenied(Exception):
    pass


def _new_session(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "history": [],          # OpenAI messages 列表
        "pending_actions": None,  # 待用户确认的破坏性动作列表
        "pending_message": None,  # 待确认时的原始用户消息
        "last_summary": None,    # 待确认时给用户看的那句总结
        "created_at": time.time(),
        "last_active": time.time(),
    }


def _cleanup_expired():
    now = time.time()
    with _LOCK:
        expired = [sid for sid, s in _SESSIONS.items()
                   if now - s["last_active"] > _TTL_SECONDS]
        for sid in expired:
            del _SESSIONS[sid]


def get_or_create(session_id: Optional[str], user_id: int) -> tuple:
    """
    获取或创建会话。
    - session_id 为空:新建一个,返回 (sid, session)
    - session_id 非空:必须存在且 user_id 匹配,否则拒绝
    """
    _cleanup_expired()
    with _LOCK:
        if not session_id:
            sid = f"u{user_id}_{uuid.uuid4().hex[:16]}"
            _SESSIONS[sid] = _new_session(user_id)
            return sid, _SESSIONS[sid]

        s = _SESSIONS.get(session_id)
        if s is None:
            # 已过期或不存在,重建
            _SESSIONS[session_id] = _new_session(user_id)
            return session_id, _SESSIONS[session_id]

        if s["user_id"] != user_id:
            raise SessionPermissionDenied("会话属于其他用户")

        s["last_active"] = time.time()
        return session_id, s


def get(session_id: str, user_id: int) -> dict:
    _cleanup_expired()
    with _LOCK:
        s = _SESSIONS.get(session_id)
        if s is None:
            raise SessionNotFound("会话不存在或已过期")
        if s["user_id"] != user_id:
            raise SessionPermissionDenied("会话属于其他用户")
        s["last_active"] = time.time()
        return s


def set_pending(session_id: str, user_id: int, actions: list, message: str, summary: str):
    with _LOCK:
        s = get(session_id, user_id)
        s["pending_actions"] = actions
        s["pending_message"] = message
        s["last_summary"] = summary


def get_pending(session_id: str, user_id: int) -> Optional[list]:
    with _LOCK:
        s = get(session_id, user_id)
        return s.get("pending_actions")


def clear_pending(session_id: str, user_id: int):
    with _LOCK:
        s = get(session_id, user_id)
        s["pending_actions"] = None
        s["pending_message"] = None
        s["last_summary"] = None


def append_history(session_id: str, user_id: int, message: dict):
    with _LOCK:
        s = get(session_id, user_id)
        s["history"].append(message)
        s["last_active"] = time.time()


def reset_session(session_id: str, user_id: int):
    """清空历史(用户主动重置对话)"""
    with _LOCK:
        s = get(session_id, user_id)
        s["history"] = []
        s["pending_actions"] = None
        s["pending_message"] = None
        s["last_summary"] = None
        s["last_active"] = time.time()
