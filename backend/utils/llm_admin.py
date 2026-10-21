"""后台/管理端 LLM 调用辅助

- 统一用系统默认模型(`llm_models.is_system_default=1`)
- 所有调用自动写 `ai_chat_logs`
- 不读用户激活的模型

改造点:底层从裸 `OpenAI` 换成 `ChatOpenAI`,但 `admin_chat` 的**签名和返回值不变**,
所以报表 / 洞察 / AI 创建等调用方一行都不用改。
另外新增 `admin_chat_async`,给 async 路由用(避免在事件循环里跑同步 LLM 调用)。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agent.chat_model import aget_admin_chat_model, get_admin_chat_model
from utils.ai_logging import log_assistant_message, log_user_message

log = logging.getLogger("utils.llm_admin")

ADMIN_USER_ID = 0
ADMIN_SESSION = "admin_console"


def get_admin_llm_client():
    """兼容旧调用方:返回 (LangChain ChatOpenAI, model_name)

    注意:返回值不再是裸 OpenAI 客户端。目前所有调用方都只用
    `client.chat.completions.create(...)` —— 如果有,请改用 `admin_chat`。
    """
    llm, model = get_admin_chat_model()
    return llm, model["model_name"]


def _build_messages(system_prompt: str, user_message: str, extra_user_msg: Optional[str]):
    from langchain_core.messages import HumanMessage, SystemMessage
    msgs = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    if extra_user_msg:
        msgs.append(HumanMessage(content=extra_user_msg))
    return msgs


def _usage(resp) -> dict:
    meta = getattr(resp, "usage_metadata", None) or {}
    return {
        "prompt_tokens": meta.get("input_tokens"),
        "completion_tokens": meta.get("output_tokens"),
        "total_tokens": meta.get("total_tokens"),
    }


def admin_chat(
    system_prompt: str,
    user_message: str,
    *,
    session_id: str = ADMIN_SESSION,
    extra_user_msg: Optional[str] = None,
    extra_user_kwargs: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> str:
    """单轮 LLM 调用(同步)。签名与改造前完全一致。"""
    llm, model_record = get_admin_chat_model()
    used_model = model or model_record["model_name"]

    log_user_message(ADMIN_USER_ID, session_id, user_message, model=used_model)
    if extra_user_msg:
        log_user_message(ADMIN_USER_ID, session_id, extra_user_msg, model=used_model)

    try:
        resp = llm.invoke(_build_messages(system_prompt, user_message, extra_user_msg))
        text = (resp.content or "").strip() if isinstance(resp.content, str) else str(resp.content or "").strip()
        usage = _usage(resp)
    except Exception as e:
        log_assistant_message(ADMIN_USER_ID, session_id, f"[ERROR] {type(e).__name__}: {e}", model=used_model)
        raise

    log_assistant_message(ADMIN_USER_ID, session_id, text, model=used_model, **usage)
    return text


async def admin_chat_async(
    system_prompt: str,
    user_message: str,
    *,
    session_id: str = ADMIN_SESSION,
    extra_user_msg: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """单轮 LLM 调用(异步)—— 给 async 路由用"""
    llm, model_record = await aget_admin_chat_model()
    used_model = model or model_record["model_name"]

    log_user_message(ADMIN_USER_ID, session_id, user_message, model=used_model)
    if extra_user_msg:
        log_user_message(ADMIN_USER_ID, session_id, extra_user_msg, model=used_model)

    try:
        resp = await llm.ainvoke(_build_messages(system_prompt, user_message, extra_user_msg))
        text = (resp.content or "").strip() if isinstance(resp.content, str) else str(resp.content or "").strip()
        usage = _usage(resp)
    except Exception as e:
        log_assistant_message(ADMIN_USER_ID, session_id, f"[ERROR] {type(e).__name__}: {e}", model=used_model)
        raise

    log_assistant_message(ADMIN_USER_ID, session_id, text, model=used_model, **usage)
    return text
