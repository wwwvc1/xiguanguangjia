"""通用聊天 API —— LangChain 真流式

改造点:
1. 裸 `OpenAI().chat.completions.create(stream=True)` → `ChatOpenAI.astream()`
2. 对话上下文从**进程内 dict**(重启丢、多 worker 不共享、永不清理)
   迁到 Redis LIST(24h TTL,最多 10 轮),见 services/chat_session_service.py
3. 顺手修好一个老 bug:原代码只读历史从不写,历史永远是空的
4. token 用量落库(原来只 print)
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.chat_model import aget_chat_model_for_user
from models.ai_chat import ChatRequest
from services import chat_session_service
from utils.ai_logging import log_assistant_message, log_user_message
from utils.deps import get_current_user

log = logging.getLogger("routers.ai_general")
router = APIRouter(prefix="/api/ai/chat", tags=["AI"])

SYSTEM_PROMPT = "你是一个友好的 AI 聊天助手。请用简洁、自然的语言回答用户的问题。用中文回答。"

# 上游"通道不可用"的各种措辞(不同中转站写法不同)
_UPSTREAM_DOWN_HINTS = (
    "temporarily unavailable", "get_channel_failed", "channel_failed",
    "service unavailable", "bad gateway", "gateway timeout",
    "upstream", "overloaded",
)


def _friendly_llm_error(e: Exception) -> str:
    """把 SDK 原始异常翻译成用户能看懂、且能据此行动的话"""
    text = str(e)
    name = type(e).__name__
    low = text.lower()
    if "Authentication" in name or "401" in text:
        return "AI_API配置错误，请联系管理员"
    if "Timeout" in name or "timeout" in low:
        return "请求超时，请检查网络后重试"
    if "RateLimit" in name or "429" in text:
        return "请求太频繁，请稍后再试"
    if ("InternalServerError" in name or "502" in text or "503" in text or "504" in text
            or any(h in low for h in _UPSTREAM_DOWN_HINTS)):
        return "上游模型通道暂时不可用(不是你的 key 问题)，请稍后重试或在「AI 模型」里换一个模型"
    return f"AI 服务异常: {text[:160]}"


@router.post("/general")
async def general_chat(req: ChatRequest, current_user: int = Depends(get_current_user)):
    """通用聊天(SSE 真流式)"""
    session_key = str(current_user)

    try:
        llm, model_record = await aget_chat_model_for_user(
            current_user, req.model_id, temperature=0.8, streaming=True
        )
        model_name = model_record.get("model_name")
    except Exception as e:
        log.warning("llm 工厂失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 模型不可用: {e}")

    log_user_message(current_user, session_key, req.message, model=model_name)

    history = await chat_session_service.history_as_messages(current_user, session_key)
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
    for m in history:
        messages.append(HumanMessage(content=m["content"]) if m["role"] == "user"
                        else AIMessage(content=m["content"]))
    messages.append(HumanMessage(content=req.message))

    async def generate():
        full_reply = ""
        usage: dict = {}
        try:
            async for chunk in llm.astream(messages):
                content = chunk.content
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                if content:
                    full_reply += content
                    yield f"data: {json.dumps({'type': 'text_delta', 'content': content}, ensure_ascii=False)}\n\n"
                meta = getattr(chunk, "usage_metadata", None)
                if meta:
                    usage = meta

            log_assistant_message(
                current_user, session_key, full_reply, model=model_name,
                prompt_tokens=usage.get("input_tokens"),
                completion_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
            await chat_session_service.append_turn(current_user, session_key, req.message, full_reply)

            yield f"data: {json.dumps({'type': 'done', 'reply': full_reply, 'sources': []}, ensure_ascii=False)}\n\n"
        except Exception as e:
            log.warning("general 流式异常: %s: %s", type(e).__name__, str(e)[:300])
            yield f"data: {json.dumps({'type': 'error', 'message': _friendly_llm_error(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
