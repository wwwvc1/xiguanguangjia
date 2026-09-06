"""AI 对话日志工具
- 把每条 user/assistant/tool 消息写入 ai_chat_logs
- 失败时只 print 不抛异常(日志失败不能影响主流程)
- 如果 ai_chat_logs 缺 token 列,自动降级:不写不读 token 字段
"""
import json
from typing import Optional, Any
from database import get_connection


# 模块级缓存:启动时检测一次,避免每次写都查 schema
_TOKEN_COLS_AVAILABLE: Optional[bool] = None


def _token_columns_available() -> bool:
    """检查 ai_chat_logs 表是否有 prompt_tokens 列(没跑迁移就降级)"""
    global _TOKEN_COLS_AVAILABLE
    if _TOKEN_COLS_AVAILABLE is not None:
        return _TOKEN_COLS_AVAILABLE
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) AS c FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE()
                         AND TABLE_NAME = 'ai_chat_logs'
                         AND COLUMN_NAME = 'prompt_tokens'"""
                )
                _TOKEN_COLS_AVAILABLE = cur.fetchone()["c"] > 0
        finally:
            conn.close()
    except Exception:
        _TOKEN_COLS_AVAILABLE = False
    return _TOKEN_COLS_AVAILABLE


def log_ai_message(
    user_id: int,
    session_id: str,
    role: str,                 # 'user' | 'assistant' | 'tool' | 'system'
    content: str,
    model: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_id: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> bool:
    """单条日志写入。返回是否成功(失败仅 print)"""
    try:
        has_tokens = _token_columns_available()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if has_tokens:
                    cur.execute(
                        """INSERT INTO ai_chat_logs
                           (user_id, session_id, role, content, tool_calls, model,
                            prompt_tokens, completion_tokens, total_tokens)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            user_id, session_id, role, content,
                            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                            model, prompt_tokens, completion_tokens, total_tokens,
                        )
                    )
                else:
                    cur.execute(
                        """INSERT INTO ai_chat_logs
                           (user_id, session_id, role, content, tool_calls, model)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            user_id, session_id, role, content,
                            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                            model,
                        )
                    )
                conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"[ai_logging] 写入失败: {e}")
        return False


def log_user_message(user_id: int, session_id: str, content: str, model: Optional[str] = None) -> bool:
    return log_ai_message(user_id, session_id, "user", content, model=model)


def log_assistant_message(
    user_id: int, session_id: str, content: str,
    model: Optional[str] = None, tool_calls: Optional[list] = None,
    prompt_tokens: Optional[int] = None, completion_tokens: Optional[int] = None, total_tokens: Optional[int] = None
) -> bool:
    return log_ai_message(
        user_id, session_id, "assistant", content, model=model, tool_calls=tool_calls,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
    )


def log_tool_message(user_id: int, session_id: str, content: str, tool_call_id: str, model: Optional[str] = None) -> bool:
    return log_ai_message(user_id, session_id, "tool", content, model=model, tool_call_id=tool_call_id)
