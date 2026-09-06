"""后台/管理端 LLM 调用辅助
- 统一用系统默认模型(`llm_models.is_system_default=1`)
- 所有调用都自动写 `ai_chat_logs`(无遗漏)
- 不读用户激活的 LLM 模型

用法:
    from utils.llm_admin import get_admin_llm_client, ADMIN_USER_ID

    client, model_name = get_admin_llm_client()
    resp = client.chat.completions.create(model=model_name, ...)
"""
from typing import Optional, Tuple, List, Dict, Any
from openai import OpenAI
from config import settings
from database import get_connection
from utils.ai_logging import log_user_message, log_assistant_message


# 虚拟 admin user_id:用 0 占位(ai_chat_logs.user_id 允许 NULL/0)
ADMIN_USER_ID = 0
ADMIN_SESSION = "admin_console"


def get_admin_llm_client() -> Tuple[OpenAI, str]:
    """返回 (client, model_name) — 系统默认 LLM,无默认则报错"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT base_url, api_key, model_name, name FROM llm_models WHERE is_system_default = 1 AND is_active = 1 LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                # 退而求其次:用任何启用的模型
                cursor.execute(
                    "SELECT base_url, api_key, model_name, name FROM llm_models WHERE is_active = 1 ORDER BY id LIMIT 1"
                )
                row = cursor.fetchone()
            if not row:
                raise RuntimeError("系统未配置任何可用的 LLM 模型,请先在管理后台添加")
            client = OpenAI(
                api_key=row["api_key"],
                base_url=row["base_url"],
            )
            return client, row["model_name"]
    finally:
        conn.close()


def admin_chat(
    system_prompt: str,
    user_message: str,
    *,
    session_id: str = ADMIN_SESSION,
    extra_user_msg: Optional[str] = None,
    extra_user_kwargs: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> str:
    """单轮 LLM 调用:发 user + (可选额外 user) → 拿 assistant 文本
    自动:
      - log_user_message(... 原始)
      - log_user_message(... 额外的,如果给)
      - log_assistant_message(... 返回值 + token usage)
    """
    client, default_model = get_admin_llm_client()
    used_model = model or default_model

    log_user_message(ADMIN_USER_ID, session_id, user_message, model=used_model)
    if extra_user_msg:
        log_user_message(ADMIN_USER_ID, session_id, extra_user_msg, model=used_model)

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": user_message})
    if extra_user_msg:
        messages.append({"role": "user", "content": extra_user_msg})

    try:
        resp = client.chat.completions.create(
            model=used_model,
            messages=messages,
            temperature=0.6,
            max_tokens=1024,
        )
        text = (resp.choices[0].message.content or "").strip()
        # 抓 token usage
        usage = getattr(resp, "usage", None)
        p_tok = getattr(usage, "prompt_tokens", None) if usage else None
        c_tok = getattr(usage, "completion_tokens", None) if usage else None
        t_tok = getattr(usage, "total_tokens", None) if usage else None
    except Exception as e:
        log_assistant_message(ADMIN_USER_ID, session_id, f"[ERROR] {type(e).__name__}: {e}", model=used_model)
        raise

    log_assistant_message(
        ADMIN_USER_ID, session_id, text, model=used_model,
        prompt_tokens=p_tok, completion_tokens=c_tok, total_tokens=t_tok,
    )
    return text
