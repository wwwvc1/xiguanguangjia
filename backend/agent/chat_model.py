"""ChatOpenAI 工厂

对外只暴露三个入口:
- `get_chat_model_for_user(user_id, model_id)` → (ChatOpenAI, model_record)
- `get_chat_model_by_id(model_id)`             → (ChatOpenAI, model_record)
- `get_admin_chat_model()`                     → (ChatOpenAI, model_name)  系统默认

优先级与改造前的 `get_llm_client_for_user` 完全一致:
入参 model_id > 用户激活模型 > 系统默认 > 环境变量。

## 灰度开关

`LLM_BACKEND=langchain`(默认)返回 ChatOpenAI;
`LLM_BACKEND=openai` 时 `agent` 层会退回到裸 OpenAI 客户端(见 utils/llm_factory.py)。
一条环境变量即可回滚。

## 三个端点坑的处理(见 agent改造方案.md 3.5)

| 坑 | 处理 |
|---|---|
| 流式 tool_calls delta 不完整 | Agent 的工具轮**不流式**,只有最终回答流式(与改造前行为等价) |
| `response_format` 被静默忽略 | 不用 `with_structured_output()`,结构化输出继续走 prompt + 正则 |
| 默认重试 + 低配额(429) | `max_retries=0`,重试交给业务层 |
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from core.config import settings
from repositories import llm_repo

log = logging.getLogger("agent.chat_model")

# connect 10s:海外端点没开代理时 TCP 握手会长时间挂着
# read 120s:流式输出两块 chunk 之间的最长间隔
LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

PLACEHOLDER_KEYS = {"", "MIGRATION_PLACEHOLDER", "sk-your-openai-api-key"}


def _resolve_api_key(model: dict) -> str:
    key = (model.get("api_key") or "").strip()
    if key in PLACEHOLDER_KEYS:
        return settings.OPENAI_API_KEY
    return key


def to_chat_model(model: dict, temperature: float = 0.3, streaming: bool = False):
    """把 llm_models 的一行变成 ChatOpenAI"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model["model_name"],
        base_url=model.get("base_url") or settings.OPENAI_BASE_URL,
        api_key=_resolve_api_key(model),
        timeout=LLM_TIMEOUT,
        max_retries=0,
        temperature=temperature,
        streaming=streaming,
    )


def _env_fallback_record() -> dict:
    return {
        "id": None, "name": "环境变量默认", "model_name": settings.CHAT_MODEL,
        "base_url": settings.OPENAI_BASE_URL, "api_key": settings.OPENAI_API_KEY,
        "is_system_default": False, "is_active": True, "owner_user_id": None,
    }


def _check_ownership(model: dict, user_id: int) -> None:
    owner = model.get("owner_user_id")
    if owner is not None and owner != user_id:
        raise ValueError("无权使用该模型")


# ============================================================
# 同步入口
# ============================================================
def get_chat_model_by_id(model_id: int, temperature: float = 0.3, streaming: bool = False):
    model = llm_repo.model_by_id_sync(model_id)
    if not model:
        raise ValueError(f"模型 {model_id} 不存在")
    if not model["is_active"]:
        raise ValueError(f"模型 {model_id} 已停用")
    return to_chat_model(model, temperature, streaming), model


def get_chat_model_for_user(
    user_id: int,
    model_id: Optional[int] = None,
    temperature: float = 0.3,
    streaming: bool = False,
):
    """优先级:入参 model_id > 用户激活模型 > 系统默认 > 环境变量"""
    model: Optional[dict] = None

    if model_id:
        model = llm_repo.model_by_id_sync(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        if not model["is_active"]:
            raise ValueError(f"模型 {model_id} 已停用")
        _check_ownership(model, user_id)
    else:
        active_id = llm_repo.active_model_id_sync(user_id)
        if active_id:
            candidate = llm_repo.model_by_id_sync(active_id)
            if candidate and candidate["is_active"]:
                try:
                    _check_ownership(candidate, user_id)
                    model = candidate
                except ValueError:
                    model = None

    if model is None:
        model = llm_repo.default_model_sync()

    if model is None:
        record = _env_fallback_record()
        return to_chat_model(record, temperature, streaming), record

    return to_chat_model(model, temperature, streaming), model


def get_admin_chat_model(temperature: float = 0.6):
    """系统默认模型(管理端 / 周报 / 洞察用)"""
    model = llm_repo.default_model_sync()
    if not model:
        raise RuntimeError("系统未配置任何可用的 LLM 模型,请先在管理后台添加")
    return to_chat_model(model, temperature), model


# ============================================================
# 异步入口(给 async 路由用,模型查询走异步池)
# ============================================================
async def aget_chat_model_for_user(
    user_id: int,
    model_id: Optional[int] = None,
    temperature: float = 0.3,
    streaming: bool = False,
):
    model: Optional[dict] = None

    if model_id:
        model = await llm_repo.model_by_id(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        if not model["is_active"]:
            raise ValueError(f"模型 {model_id} 已停用")
        _check_ownership(model, user_id)
    else:
        active_id = await llm_repo.active_model_id(user_id)
        if active_id:
            candidate = await llm_repo.model_by_id(active_id)
            if candidate and candidate["is_active"]:
                try:
                    _check_ownership(candidate, user_id)
                    model = candidate
                except ValueError:
                    model = None

    if model is None:
        model = await llm_repo.default_model()

    if model is None:
        record = _env_fallback_record()
        return to_chat_model(record, temperature, streaming), record

    return to_chat_model(model, temperature, streaming), model


async def aget_admin_chat_model(temperature: float = 0.6):
    model = await llm_repo.default_model()
    if not model:
        raise RuntimeError("系统未配置任何可用的 LLM 模型,请先在管理后台添加")
    return to_chat_model(model, temperature), model
