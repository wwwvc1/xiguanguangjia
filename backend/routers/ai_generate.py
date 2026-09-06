from fastapi import APIRouter, Depends, HTTPException
from database import get_connection
from utils.deps import get_current_user
from utils.ai_rag import search_knowledge
from config import settings
import json

router = APIRouter(prefix="/api/ai", tags=["ai"])

TASK_GENERATE_PROMPT = """\
你是一个习惯管家 AI 助手。用户描述了他们想养成的习惯或目标。

请根据用户的描述，生成 3-6 项具体的、可执行的任务建议。
任务类型可以是：待办(todo)、目标(goal)、饮食(diet)、收支(finance)。

请严格按照以下 JSON 格式返回，不要有其他文字：
[
  {
    "icon": "emoji图标",
    "name": "任务名称",
    "meta": "类型 · 频率 · 时间/备注",
    "type": "todo|goal|diet|finance",
    "typeLabel": "待办|目标|饮食|收支"
  }
]

用户描述：{user_input}
"""

@router.post("/generate-tasks")
def generate_tasks(req: dict, current_user: int = Depends(get_current_user)):
    """AI 智能生成任务"""
    user_input = req.get("message", "")
    if not user_input:
        raise HTTPException(status_code=400, detail="请输入描述")

    prompt = TASK_GENERATE_PROMPT.replace("{user_input}", user_input)

    # 系统默认模型 + 自动写 ai_chat_logs
    from utils.llm_admin import get_admin_llm_client, admin_chat
    try:
        content = admin_chat(
            system_prompt="你是一个JSON生成器。只返回JSON数组,不要有其他文字。",
            user_message=prompt,
            session_id=f"admin_ai_generate_{current_user}",
        )

        # 清理 markdown 代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        # 从响应中提取 JSON
        try:
            tasks = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                tasks = json.loads(match.group())
            else:
                tasks = []

        # 验证返回格式
        if not isinstance(tasks, list):
            tasks = []

        return {"tasks": tasks}

    except Exception as e:
        from openai import OpenAIError
        if isinstance(e, OpenAIError):
            raise HTTPException(status_code=500, detail=f"AI服务异常: {str(e)}")
        raise
