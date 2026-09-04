from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import OpenAI, AuthenticationError, APITimeoutError, RateLimitError, OpenAIError
from config import settings
from utils.deps import get_current_user
from utils.llm_factory import get_llm_client_for_user
from models.ai_chat import ChatRequest, ChatResponse
import json

router = APIRouter(prefix="/api/ai/chat", tags=["AI"])

_chat_history: dict[str, list[dict]] = {}

@router.post("/general", response_model=ChatResponse)
def general_chat(req: ChatRequest, current_user: int = Depends(get_current_user)):
    """通用聊天接口（流式响应,支持自定义 model_id）"""
    session_key = str(current_user)
    if session_key not in _chat_history:
        _chat_history[session_key] = []

    history = _chat_history[session_key][-10:]
    messages = [
        {"role": "system", "content": "你是一个友好的 AI 聊天助手。请用简洁、自然的语言回答用户的问题。用中文回答。"}
    ]
    for msg in history:
        messages.append({"role": "user", "content": msg["user"]})
        messages.append({"role": "assistant", "content": msg["assistant"]})
    messages.append({"role": "user", "content": req.message})

    # 按 model_id / 用户激活 / 系统默认 选 client
    try:
        client, model_record = get_llm_client_for_user(current_user, req.model_id)
        model_name = model_record.get("model_name") or settings.CHAT_MODEL
    except Exception as e:
        print(f"[AI-General] llm_factory 失败,回退环境变量: {e}")
        client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
        model_name = settings.CHAT_MODEL

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.8,
            max_tokens=500,
            stream=True,
        )

        def generate():
            full_reply = ""
            last_chunk = None
            for chunk in stream:
                last_chunk = chunk
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    # 事件格式与 /ai/chat/professional 一致:必须有 type 字段
                    yield f"data: {json.dumps({'type': 'text_delta', 'content': content}, ensure_ascii=False)}\n\n"
            # 从最后一个 chunk 获取 token 使用量
            usage = getattr(last_chunk, 'usage', None)
            if usage:
                print(f"[AI-General] Token消耗: 输入={usage.prompt_tokens}, 输出={usage.completion_tokens}, 总计={usage.total_tokens}")
            yield f"data: {json.dumps({'type': 'done', 'reply': full_reply, 'sources': []}, ensure_ascii=False)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    except AuthenticationError:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="AI_API配置错误，请联系管理员")
    except APITimeoutError:
        from fastapi import HTTPException
        raise HTTPException(status_code=504, detail="请求超时，请检查网络后重试")
    except RateLimitError:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试")
    except OpenAIError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"AI服务异常: {str(e)}")
