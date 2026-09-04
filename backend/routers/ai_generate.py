from fastapi import APIRouter, Depends, HTTPException
from database import get_connection
from utils.deps import get_current_user
from utils.ai_rag import search_knowledge
from openai import OpenAI, OpenAIError
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

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个JSON生成器。只返回JSON数组，不要有其他文字。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=800,
        )

        content = response.choices[0].message.content.strip()

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

        # Token 记录
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            print(f"[AI-Generate] Token消耗: 输入={usage.prompt_tokens}, 输出={usage.completion_tokens}, 总计={usage.total_tokens}")

        return {"tasks": tasks}

    except OpenAIError as e:
        raise HTTPException(status_code=500, detail=f"AI服务异常: {str(e)}")
