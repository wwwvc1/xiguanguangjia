"""AI 对话日志工具
- 把每条 user/assistant/tool 消息写入 ai_chat_logs
- 供 routers/ai_general.py / ai_professional.py / utils/ai_agent.py 共用
- 失败时只 print,不抛异常(日志失败不能影响主流程)
"""
import json
from typing import Optional, Any

from database import get_connection


def log_ai_message(
    user_id: int,
    session_id: str,
    role: str,                 # 'user' | 'assistant' | 'tool' | 'system'
    content: str,
    model: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_id: Optional[str] = None,
) -> bool:
    """单条日志写入。返回是否成功(失败仅 print)"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO ai_chat_logs
                       (user_id, session_id, role, content, tool_calls, model)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        user_id,
                        session_id,
                        role,
                        content,
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


def log_assistant_message(user_id: int, session_id: str, content: str, model: Optional[str] = None, tool_calls: Optional[list] = None) -> bool:
    return log_ai_message(user_id, session_id, "assistant", content, model=model, tool_calls=tool_calls)


def log_tool_message(user_id: int, session_id: str, content: str, tool_call_id: str, model: Optional[str] = None) -> bool:
    return log_ai_message(user_id, session_id, "tool", content, model=model, tool_call_id=tool_call_id)
