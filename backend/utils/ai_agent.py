"""
ReAct 多步 Agent
- 维护消息历史(用户 / 助手 / tool)
- 调 LLM (OpenAI 兼容) 支持 function calling
- 若有 tool_calls:执行每个工具,把结果以 role=tool 加回 messages,继续
- 若无 tool_calls:流式输出最终回复
- 最多 max_iterations 轮
"""
import json
import time
from datetime import datetime
from typing import List, Dict, Any, AsyncIterator, Optional

from openai import OpenAI, AuthenticationError, APITimeoutError, RateLimitError, OpenAIError
from config import settings
from utils.llm_factory import get_llm_client_for_user

# 延迟导入 RAG(它依赖 langchain,在某些环境可能没装)
try:
    from utils.ai_rag import search_knowledge
    _RAG_AVAILABLE = True
except Exception as _rag_err:
    print(f"[Agent] RAG 不可用,跳过知识检索: {_rag_err}")
    _RAG_AVAILABLE = False
    def search_knowledge(q, top_k=3):
        return []

from utils.ai_tools import TOOLS
from utils.ai_tool_executor import ToolExecutor


SYSTEM_PROMPT = """你是「习惯管家」AI 助手,可以帮用户管理待办、目标、收支、饮食、提醒。
- 你的工具可执行真实的增删查改(数据库直接写入),所以调用前请先想清楚用户意图。
- 简洁、温暖、具体;不要重复工具结果原文,用自然语言总结给用户。
- 用户问"我有多少待办"先调 list_todos,不要凭记忆猜。
- 涉及修改/删除/添加时,如果参数不明确(比如不知道 ID),先 list 一下再操作。
- 用中文回答。"""


class AgentExecutor:
    def __init__(self, user_id: int, model: Optional[str] = None, model_id: Optional[int] = None):
        self.user_id = user_id
        # 通过 llm_factory 拿 client(支持用户自定义模型 / 系统默认)
        try:
            self.client, model_record = get_llm_client_for_user(user_id, model_id)
            self.model = model or model_record.get("model_name") or settings.CHAT_MODEL
            self.model_record = model_record
        except ValueError as e:
            # 用户没权限 / 模型不可用,fallback 到 .env
            print(f"[Agent] llm_factory 取模型失败,回退环境变量: {e}")
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
            self.model = model or settings.CHAT_MODEL
            self.model_record = {"id": None, "name": "环境变量默认", "model_name": self.model}
        self.executor = ToolExecutor()
        self.max_iterations = 5

    def _build_initial_messages(self, user_input: str, history: Optional[List[Dict]] = None) -> List[Dict]:
        """构建消息:系统提示 + 历史 + RAG 知识 + 用户输入"""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 历史消息(限 10 条,防止 token 爆炸)
        if history:
            for m in history[-10:]:
                role = m.get("role")
                content = m.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        # RAG 检索
        if _RAG_AVAILABLE:
            try:
                chunks = search_knowledge(user_input, top_k=3)
                if chunks:
                    knowledge_text = "\n\n".join(chunks)
                    messages.append({
                        "role": "system",
                        "content": f"=== 专业知识(仅作参考) ===\n{knowledge_text}"
                    })
            except Exception as e:
                print(f"[Agent] RAG 检索失败: {e}")

        messages.append({"role": "user", "content": user_input})
        return messages

    def _serialize_tool_result(self, result: dict) -> str:
        """把工具结果序列化为字符串(给 LLM 看)"""
        ok = result.get("ok", False)
        if not ok:
            return f"错误:{result.get('error', '未知错误')}"
        data = result.get("data")
        # 列表太长时截断
        try:
            s = json.dumps(data, ensure_ascii=False, default=str)
            if len(s) > 3000:
                s = s[:3000] + "...(已截断)"
            return s
        except Exception:
            return str(data)[:3000]

    def _serialize_for_client(self, messages: List[Dict]) -> List[Dict]:
        """保证消息格式能被 openai SDK 接受"""
        out = []
        for m in messages:
            msg = {"role": m["role"], "content": m.get("content", "")}
            if m.get("role") == "assistant" and m.get("tool_calls"):
                msg["tool_calls"] = m["tool_calls"]
            if m.get("role") == "tool" and "tool_call_id" in m:
                msg["tool_call_id"] = m["tool_call_id"]
            if m.get("role") == "tool" and m.get("name"):
                msg["name"] = m["name"]
            out.append(msg)
        return out

    async def run(
        self,
        user_input: str,
        history: Optional[List[Dict]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        生成器:yield 事件 dict
        事件类型:
          - {"type": "tool_call", "name": ..., "args": ...}
          - {"type": "tool_result", "name": ..., "result": ..., "ok": bool}
          - {"type": "text_delta", "content": "..."}
          - {"type": "done", "reply": "...", "sources": [...], "tool_calls": [...]}
          - {"type": "error", "message": "..."}
        """
        messages = self._build_initial_messages(user_input, history)
        all_tool_calls = []  # 用于最终 done 事件
        sources = []
        # 收集 RAG chunks 作为 sources
        if _RAG_AVAILABLE:
            try:
                sources = search_knowledge(user_input, top_k=3)
            except Exception:
                pass

        try:
            for iteration in range(self.max_iterations):
                # 调用 LLM(非流式,因为要拿 tool_calls)
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=self._serialize_for_client(messages),
                    tools=TOOLS,
                    temperature=0.6,
                    max_tokens=1024,
                )
                choice = resp.choices[0]
                msg = choice.message

                # 记录 assistant 消息
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or ""
                }
                if msg.tool_calls:
                    # OpenAI SDK 0.27+ 用 .model_dump() 才不会丢字段
                    try:
                        assistant_msg["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in msg.tool_calls
                        ]
                    except Exception:
                        pass
                messages.append(assistant_msg)

                # 没有 tool_calls → 进入最终流式输出
                if not msg.tool_calls:
                    # 直接复用上一次的 content 一次性发出(简单可靠)
                    if msg.content:
                        # 模拟流式:每 4 字一段
                        text = msg.content
                        chunk_size = 4
                        for i in range(0, len(text), chunk_size):
                            yield {"type": "text_delta", "content": text[i:i+chunk_size]}
                            await _sleep_small()
                    yield {
                        "type": "done",
                        "reply": msg.content or "",
                        "sources": sources,
                        "tool_calls": all_tool_calls
                    }
                    return

                # 有 tool_calls → 执行每个
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}

                    # 推给前端:正在调工具
                    yield {"type": "tool_call", "name": name, "args": args}

                    # 实际执行
                    t0 = time.time()
                    result = self.executor.execute(self.user_id, name, args)
                    elapsed_ms = int((time.time() - t0) * 1000)
                    ok = result.get("ok", False)

                    record = {
                        "name": name,
                        "args": args,
                        "result": result,
                        "ok": ok,
                        "elapsed_ms": elapsed_ms
                    }
                    all_tool_calls.append(record)

                    # 推给前端:工具结果
                    yield {
                        "type": "tool_result",
                        "name": name,
                        "result": result.get("data"),
                        "ok": ok,
                        "error": result.get("error") if not ok else None,
                        "elapsed_ms": elapsed_ms
                    }

                    # 加回 messages(role=tool),让 LLM 看到结果
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": self._serialize_tool_result(result)
                    })

                # 进入下一轮迭代

            # 超过 max_iterations,强制收尾
            yield {
                "type": "text_delta",
                "content": "\n\n(已达到最大推理步数,直接给出建议)"
            }
            yield {
                "type": "done",
                "reply": "(已达到最大推理步数)",
                "sources": sources,
                "tool_calls": all_tool_calls
            }

        except AuthenticationError:
            yield {"type": "error", "message": "AI API 配置错误,请联系管理员"}
        except APITimeoutError:
            yield {"type": "error", "message": "请求超时,请检查网络后重试"}
        except RateLimitError:
            yield {"type": "error", "message": "请求太频繁,请稍后再试"}
        except OpenAIError as e:
            yield {"type": "error", "message": f"AI 服务异常: {str(e)}"}
        except Exception as e:
            print(f"[Agent] 未知错误: {e}")
            yield {"type": "error", "message": f"出错了: {str(e)}"}


async def _sleep_small():
    """小延时,模拟流式效果"""
    import asyncio
    await asyncio.sleep(0.02)
