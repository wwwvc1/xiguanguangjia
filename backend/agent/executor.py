"""`/api/ai/chat/professional` 用的 Agent 执行器

现在只是 `agent/core.py` 的**薄封装**:负责取模型、检索 RAG、拼初始消息,
真正的工具循环在 core 里 —— 和 `/api/ai/agent`(ai-create 页)共用同一份实现。

对外 API 与改造前完全一致:`AgentExecutor.run(user_input, history)` 是异步生成器,
yield 的仍是 `text_delta / tool_call / tool_result / done / error`。
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.chat_model import get_chat_model_for_user
from agent.core import ToolCallingAgent, as_text, identity_result
from core.config import settings
from utils.ai_logging import log_user_message

log = logging.getLogger("agent.executor")

SYSTEM_PROMPT = """你是「习惯管家」AI 助手,可以帮用户管理待办、目标、收支、饮食、提醒。
- 你的工具可执行真实的增删查改(数据库直接写入),所以调用前请先想清楚用户意图。
- 简洁、温暖、具体;不要重复工具结果原文,用自然语言总结给用户。
- 用户问"我有多少待办"先调 list_todos,不要凭记忆猜。
- 涉及修改/删除/添加时,如果参数不明确(比如不知道 ID),先 list 一下再操作。
- 用中文回答。"""


def _rag_search(query: str, top_k: int = 3) -> list:
    """RAG 是同步且首调用可能加载模型,单独包一层便于丢线程池"""
    try:
        from utils.ai_rag import search_knowledge
        return search_knowledge(query, top_k=top_k) or []
    except Exception as e:
        log.warning("RAG 检索失败: %s", e)
        return []


class AgentExecutor:
    def __init__(
        self,
        user_id: int,
        model: Optional[str] = None,
        model_id: Optional[int] = None,
        session_id: Optional[str] = None,
        max_iterations: int = 5,
        temperature: float = 0.6,
    ):
        self.user_id = user_id
        self.session_id = session_id or f"agent_{user_id}"
        self.temperature = temperature
        self.max_iterations = max_iterations

        try:
            self.llm, model_record = get_chat_model_for_user(
                user_id, model_id, temperature=temperature
            )
            self.model_record = model_record
            self.model = model or model_record.get("model_name") or settings.CHAT_MODEL
        except Exception as e:
            log.warning("llm_factory 取模型失败,回退环境变量: %s", e)
            from agent.chat_model import _env_fallback_record, to_chat_model
            self.model_record = _env_fallback_record()
            self.llm = to_chat_model(self.model_record, temperature)
            self.model = model or settings.CHAT_MODEL

        from utils.ai_tool_executor import ToolExecutor
        from utils.ai_tools import TOOLS

        self._tool_runtime = ToolExecutor()
        self.tools = TOOLS
        self._rag_available = self._check_rag()

    @staticmethod
    def _check_rag() -> bool:
        try:
            import utils.ai_rag  # noqa: F401
            return True
        except Exception:
            return False

    async def _build_messages(self, user_input: str, history: Optional[List[Dict]] = None):
        messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

        if history:
            for m in history[-10:]:
                role, content = m.get("role"), m.get("content", "")
                if not content:
                    continue
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        sources: list = []
        if self._rag_available:
            chunks = await asyncio.to_thread(_rag_search, user_input, settings.RAG_TOP_K)
            if chunks:
                sources = chunks
                messages.append(SystemMessage(
                    content="=== 专业知识(仅作参考) ===\n" + "\n\n".join(chunks)
                ))

        messages.append(HumanMessage(content=user_input))
        return messages, sources

    async def run(
        self,
        user_input: str,
        history: Optional[List[Dict]] = None,
    ) -> AsyncIterator[Dict]:
        messages, sources = await self._build_messages(user_input, history)
        log_user_message(self.user_id, self.session_id, user_input, model=self.model)

        agent = ToolCallingAgent(
            user_id=self.user_id,
            llm=self.llm,
            model_name=self.model,
            tools=self.tools,
            execute_tool=self._tool_runtime.execute,
            max_iterations=self.max_iterations,
            require_confirmation=False,      # 这条链路不做二次确认
            emit_deltas=True,                # 保持前端习惯的 4 字切片"假流式"
            result_adapter=identity_result,  # ToolExecutor 已经是 {ok,data,error}
            session_id=self.session_id,
            sources=sources,
        )

        async for evt in agent.astream(messages):
            yield evt
