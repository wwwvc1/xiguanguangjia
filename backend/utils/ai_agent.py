"""Agent 入口(按 LLM_BACKEND 分发)

- `LLM_BACKEND=langchain`(默认)→ `agent.executor.AgentExecutor`(ChatOpenAI + bind_tools)
- `LLM_BACKEND=openai`         → `utils.ai_agent_legacy.AgentExecutor`(改造前的裸 SDK 版本)

保留这个模块名,是为了让 `routers/ai_professional.py` 等调用方零改动即可切换。
回滚只需改一行环境变量,不用 revert 代码。
"""
from core.config import settings

if (settings.LLM_BACKEND or "").lower() == "openai":
    from utils.ai_agent_legacy import AgentExecutor, SYSTEM_PROMPT  # noqa: F401
else:
    from agent.executor import AgentExecutor, SYSTEM_PROMPT  # noqa: F401

__all__ = ["AgentExecutor", "SYSTEM_PROMPT"]
