"""LLM 工厂(兼容层)

历史上的调用点分两拨,这里都照顾到:

1. **裸客户端**(`OpenAI`):老代码还在用 `client.chat.completions.create(...)`。
   已标记 deprecated,但签名与行为保持不变,不要在新代码里用。
2. **LangChain 客户端**(`ChatOpenAI`):新代码统一走 `get_chat_model_*`,
   它只是 `agent/chat_model.py` 的转发,避免出现第二套优先级逻辑。

本次修复的 P0 缺陷:
`routers/ai_agent.py` 曾调用 `get_llm_client_by_id`,但这个函数**从来没被定义过**。
异常被 `except` 吞掉 → agent 链路永远走已失效的 .env 默认模型。现在补上了。

注:agent 链路现在已经统一到 `agent/core.py`(ChatOpenAI),`get_llm_client_by_id`
只作为兼容入口保留,新代码请用 `agent.chat_model.get_chat_model_for_user`。
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

import httpx
from openai import OpenAI

from agent.chat_model import (  # noqa: F401  (转发 LangChain 工厂)
    LLM_TIMEOUT,
    aget_admin_chat_model,
    aget_chat_model_for_user,
    get_admin_chat_model,
    get_chat_model_by_id,
    get_chat_model_for_user,
    to_chat_model,
)
from core.config import settings
from repositories import llm_repo


def _api_key_for(model: dict) -> str:
    key = (model.get("api_key") or "").strip()
    if key in {"", "MIGRATION_PLACEHOLDER", "sk-your-openai-api-key"}:
        return settings.OPENAI_API_KEY
    return key


# ============================================================
# 模型查询(deprecated:请直接用 repositories.llm_repo)
# ============================================================
def get_model_by_id(model_id: int) -> Optional[dict]:
    return llm_repo.model_by_id_sync(model_id)


def get_default_model() -> Optional[dict]:
    return llm_repo.default_model_sync()


def get_user_active_model(user_id: int) -> Optional[dict]:
    active_id = llm_repo.active_model_id_sync(user_id)
    if active_id:
        model = llm_repo.model_by_id_sync(active_id)
        if model and model["is_active"]:
            if model.get("owner_user_id") in (None, user_id):
                return model
    return llm_repo.default_model_sync()


# ============================================================
# 裸 OpenAI 客户端(deprecated,保留以支持 LLM_BACKEND=openai 回滚)
# ============================================================
def get_llm_client_for_user(user_id: int, model_id: Optional[int] = None) -> Tuple[OpenAI, dict]:
    """deprecated:新代码用 get_chat_model_for_user"""
    model = None
    if model_id:
        model = llm_repo.model_by_id_sync(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        if not model["is_active"]:
            raise ValueError(f"模型 {model_id} 已停用")
        if model.get("owner_user_id") is not None and model["owner_user_id"] != user_id:
            raise ValueError("无权使用该模型")

    if not model:
        model = get_user_active_model(user_id)

    if not model:
        return (
            OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL, timeout=LLM_TIMEOUT),
            {
                "id": None, "name": "环境变量默认", "model_name": settings.CHAT_MODEL,
                "base_url": settings.OPENAI_BASE_URL, "api_key": settings.OPENAI_API_KEY,
                "is_system_default": False, "owner_user_id": None,
            },
        )

    client = OpenAI(api_key=_api_key_for(model), base_url=model["base_url"], timeout=LLM_TIMEOUT)
    return client, model


def get_llm_client_by_id(model_id: int) -> Tuple[OpenAI, str]:
    """按 model_id 取 (client, model_name)

    **这是本次补齐的 P0 缺陷**:之前 routers/ai_agent.py 调用它,但函数不存在,
    异常被吞后静默降级到失效的 .env 模型。
    deprecated:新代码用 `agent.chat_model.get_chat_model_by_id`。
    """
    model = llm_repo.model_by_id_sync(model_id)
    if not model:
        raise ValueError(f"模型 {model_id} 不存在")
    if not model["is_active"]:
        raise ValueError(f"模型 {model_id} 已停用")
    client = OpenAI(api_key=_api_key_for(model), base_url=model["base_url"], timeout=LLM_TIMEOUT)
    return client, model["model_name"]


# ============================================================
# 连通性测试 / 脱敏
# ============================================================
def test_model_connection(model_id: int, prompt: str = "你好,请用一句话自我介绍。") -> dict:
    model = llm_repo.model_by_id_sync(model_id)
    if not model:
        return {"success": False, "latency_ms": 0, "reply": None, "error": "模型不存在"}

    client = OpenAI(api_key=_api_key_for(model), base_url=model["base_url"], timeout=20.0)
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=model["model_name"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.5,
        )
        latency = int((time.time() - start) * 1000)
        reply = resp.choices[0].message.content if resp.choices else "(空)"
        return {"success": True, "latency_ms": latency, "reply": reply, "error": None}
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {"success": False, "latency_ms": latency, "reply": None, "error": str(e)}


def mask_api_key(api_key: str) -> str:
    if not api_key or len(api_key) <= 8:
        return "****" if api_key else ""
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
