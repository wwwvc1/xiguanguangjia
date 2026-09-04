"""
专业 AI 助手 - ReAct Agent 版
- 流式 SSE,事件类型:text_delta / tool_call / tool_result / done / error
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from models.ai_chat import ChatRequest
from utils.deps import get_current_user
from utils.ai_agent import AgentExecutor


router = APIRouter(prefix="/api/ai/chat", tags=["ai"])


@router.post("/professional")
async def professional_chat(req: ChatRequest, current_user: int = Depends(get_current_user)):
    """专业 AI 助手(Agent 版,带工具调用)"""

    agent = AgentExecutor(user_id=current_user, model_id=req.model_id)

    async def generate():
        try:
            async for event in agent.run(req.message, req.history):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            err_evt = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err_evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
