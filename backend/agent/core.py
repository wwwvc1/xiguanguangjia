"""统一的 LangChain 工具调用循环

## 为什么要这个文件

改造前后端有**两套并行**的 agent 实现:

| | 工具数 | 轮数 | 实现 | 缺什么 |
|---|---|---|---|---|
| `/api/ai/chat/professional` | 25 | 5 | LangChain `bind_tools` | — |
| `/api/ai/agent`(ai-create 页) | 18 | 3 | 裸 SDK 手拼 dict | token 记账、友好错误、消息对象 |

后者的三个缺口都在这:没有 `usage_metadata` 落库、错误直接抛英文原文、
history 是手拼的 OpenAI dict 而不是 `AIMessage/ToolMessage`。

## 做法

**一个循环,两种消费方式**:

- `astream(messages)` → 异步事件流(SSE 端点用)
- `aloop(messages)`   → 跑完拿结构化结果(JSON 端点用)

两者走的是同一份代码,差别只是 `emit_deltas`(要不要 4 字切片"假流式")
和 `require_confirmation`(破坏性操作要不要挂起等用户确认)。

工具执行的同步函数统一丢 `asyncio.to_thread`,不阻塞事件循环。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional, Sequence

from langchain_core.messages import AIMessage, ToolMessage

log = logging.getLogger("agent.core")

_UPSTREAM_DOWN_HINTS = (
    "temporarily unavailable", "get_channel_failed", "channel_failed",
    "service unavailable", "bad gateway", "gateway timeout",
    "upstream", "overloaded",
)


def friendly_error(e: Exception) -> str:
    """把 SDK 原始异常翻译成用户能看懂、且能据此行动的话。

    这是唯一实现 —— 之前 executor 和 ai_general 各写了一份。
    """
    text = str(e)
    name = type(e).__name__
    low = text.lower()

    if "Authentication" in name or "401" in text:
        return "AI API 配置错误,请联系管理员"
    if "Timeout" in name or "timeout" in low:
        return "请求超时,请检查网络后重试"
    if "RateLimit" in name or "429" in text:
        return "请求太频繁,请稍后再试"
    if ("InternalServerError" in name or "502" in text or "503" in text or "504" in text
            or any(h in low for h in _UPSTREAM_DOWN_HINTS)):
        log.warning("上游模型不可用: %s: %s", name, text[:300])
        return "上游模型通道暂时不可用(不是你的 key 问题),请稍后重试或在「AI 模型」里换一个模型"
    log.warning("agent 执行异常: %s: %s", name, text[:300])
    return f"出错了: {text[:200]}"


def as_text(content: Any) -> str:
    """LangChain 的 content 可能是 str,也可能是 [{'type':'text','text':...}] 片段列表"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                out.append(str(part.get("text") or part.get("content") or ""))
        return "".join(out)
    return str(content)


def serialize_tool_result(result: dict, limit: int = 3000) -> str:
    """工具结果 → 给模型看的字符串(过长截断,避免撑爆上下文)"""
    if not result.get("ok", False):
        return f"错误:{result.get('error', '未知错误')}"
    try:
        s = json.dumps(result.get("data"), ensure_ascii=False, default=str)
    except Exception:
        return str(result.get("data"))[:limit]
    return s[:limit] + "...(已截断)" if len(s) > limit else s


# 工具返回值 → 统一形状 {ok, data, error}
# ai_tools 那套本来就是 {"ok","data","error"};ai_crud_tools 那套是「有 error 键即失败」。
def identity_result(r: dict) -> dict:
    return r


def crud_result(r: dict) -> dict:
    if not isinstance(r, dict):
        return {"ok": True, "data": r, "error": None}
    bad = r.get("error")
    return {"ok": not bad, "data": r, "error": bad}


class AgentError(Exception):
    """已经翻译成"人话"的错误。

    为什么要单独一个类型:aloop 会把 core 内部的 error 事件转成异常抛给 router,
    如果 router 再调一次 friendly_error,就会变成
    `出错了: 请求太频繁,请稍后再试` 这种双层包裹。带上这个类型,router 直接用原文。
    """


@dataclass
class AgentOutcome:
    """非流式消费的结果"""
    reply: str = ""
    actions: list = field(default_factory=list)      # 已执行的工具记录
    pending: list = field(default_factory=list)      # 待确认的破坏性操作
    iterations: int = 0
    truncated: bool = False
    new_messages: list = field(default_factory=list)  # 本轮新增的消息(OpenAI dict 格式,供 session 落库)


class ToolCallingAgent:
    """一套 LangChain 工具调用循环。

    参数
    ----
    llm                 : ChatOpenAI(已构造好,含 model/base_url/key)
    tools               : OpenAI 格式的 tool schema 列表(直接喂 bind_tools)
    execute_tool        : 同步函数 (user_id, name, args) -> dict
    result_adapter      : 把工具返回值归一成 {ok, data, error}
    destructive         : 需要二次确认的工具名集合
    require_confirmation: True 时破坏性操作只暂存不执行
    summarize           : (name, args, user_id) -> str,生成"人话"预览
    emit_deltas         : True 时把最终回答按 4 字切片模拟流式
    """

    def __init__(
        self,
        *,
        user_id: int,
        llm: Any,
        model_name: str,
        tools: Sequence[dict],
        execute_tool: Callable[[int, str, dict], dict],
        max_iterations: int = 5,
        temperature: Optional[float] = None,
        destructive: frozenset | set = frozenset(),
        require_confirmation: bool = False,
        summarize: Optional[Callable[[str, dict, int], str]] = None,
        emit_deltas: bool = False,
        session_id: Optional[str] = None,
        log_messages: bool = True,
        sources: Optional[list] = None,
        result_adapter: Callable[[Any], dict] = identity_result,
    ):
        self.user_id = user_id
        self.llm = llm
        self.model_name = model_name
        self.tools = list(tools)
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm
        self.execute_tool = execute_tool
        self.max_iterations = max(1, int(max_iterations))
        self.destructive = frozenset(destructive or ())
        self.require_confirmation = bool(require_confirmation)
        self.summarize = summarize
        self.emit_deltas = bool(emit_deltas)
        self.session_id = session_id or f"agent_{user_id}"
        self.log_messages = bool(log_messages)
        self.sources = sources or []
        self.result_adapter = result_adapter

        # 每轮重置
        self.actions: list = []
        self.pending: list = []
        self.new_messages: list = []
        self._reply = ""
        self._iterations = 0
        self._truncated = False

    # ---------------- 内部 ----------------
    def _log_assistant(self, text: str, tool_calls: list | None) -> None:
        if not self.log_messages:
            return
        try:
            from utils.ai_logging import log_assistant_message
            log_assistant_message(
                self.user_id, self.session_id, text, model=self.model_name,
                tool_calls=tool_calls,
                prompt_tokens=getattr(self, "_usage", {}).get("input_tokens"),
                completion_tokens=getattr(self, "_usage", {}).get("output_tokens"),
                total_tokens=getattr(self, "_usage", {}).get("total_tokens"),
            )
        except Exception as e:
            log.warning("落库 assistant 消息失败: %s", e)

    def _log_tool(self, content: str, tool_call_id: str) -> None:
        if not self.log_messages:
            return
        try:
            from utils.ai_logging import log_tool_message
            log_tool_message(self.user_id, self.session_id, content, tool_call_id, model=self.model_name)
        except Exception as e:
            log.warning("落库 tool 消息失败: %s", e)

    # ---------------- 主循环(事件流) ----------------
    async def astream(self, messages: list) -> AsyncIterator[dict]:
        self.actions = []
        self.pending = []
        self.new_messages = []
        self._reply = ""

        try:
            for iteration in range(1, self.max_iterations + 1):
                self._iterations = iteration
                resp: AIMessage = await self.llm_with_tools.ainvoke(messages)
                text = as_text(resp.content)
                tool_calls = resp.tool_calls or []

                self._usage = getattr(resp, "usage_metadata", None) or {}
                self._log_assistant(
                    text,
                    [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                        for tc in tool_calls
                    ] or None,
                )

                # 没有工具调用 → 最终回答
                if not tool_calls:
                    self._reply = text
                    self.new_messages.append({"role": "assistant", "content": text})
                    if self.emit_deltas:
                        for i in range(0, len(text), 4):
                            yield {"type": "text_delta", "content": text[i:i + 4]}
                            await asyncio.sleep(0.02)
                    yield {
                        "type": "done",
                        "reply": text,
                        "sources": self.sources,
                        "tool_calls": self.actions,
                        "pending_actions": self.pending,
                        "iterations": iteration,
                    }
                    return

                # 有工具调用
                messages.append(resp)
                self.new_messages.append({
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                        for tc in tool_calls
                    ],
                })

                for tc in tool_calls:
                    name = tc["name"]
                    args = tc["args"] or {}
                    yield {"type": "tool_call", "name": name, "args": args}

                    # 破坏性操作:只暂存,不执行
                    if self.require_confirmation and name in self.destructive:
                        preview = ""
                        if self.summarize:
                            try:
                                preview = self.summarize(name, args, self.user_id)
                            except Exception as e:
                                log.warning("生成操作预览失败: %s", e)
                        self.pending.append({"tool": name, "args": args, "preview": preview})
                        payload = {"status": "pending_confirmation",
                                   "message": f"动作『{preview or name}』已暂存,等待用户确认"}
                        yield {"type": "tool_result", "name": name, "result": None,
                               "ok": True, "pending": True, "error": None}
                        content = json.dumps(payload, ensure_ascii=False)
                    else:
                        t0 = asyncio.get_running_loop().time()
                        try:
                            raw = await asyncio.to_thread(self.execute_tool, self.user_id, name, args)
                        except Exception as e:
                            raw = {"ok": False, "data": None,
                                   "error": f"执行 {name} 失败: {e}"}
                        elapsed_ms = int((asyncio.get_running_loop().time() - t0) * 1000)

                        result = self._adapt(raw)
                        self.actions.append({
                            "tool": name, "args": args, "result": result,
                            "ok": result.get("ok", False),
                            "error": result.get("error") if not result.get("ok") else None,
                            "elapsed_ms": elapsed_ms,
                        })
                        yield {
                            "type": "tool_result", "name": name,
                            "result": result.get("data"), "ok": result.get("ok", False),
                            "error": result.get("error") if not result.get("ok") else None,
                            "elapsed_ms": elapsed_ms,
                        }
                        content = serialize_tool_result(result)

                    self._log_tool(content, tc["id"])
                    messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))
                    self.new_messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": content})

            # 达到最大轮数
            self._truncated = True
            self._reply = "操作太复杂了,请简化后重试。"
            if self.emit_deltas:
                yield {"type": "text_delta", "content": "\n\n(已达到最大推理步数,直接给出建议)"}
            yield {
                "type": "done",
                "reply": self._reply,
                "sources": self.sources,
                "tool_calls": self.actions,
                "pending_actions": self.pending,
                "iterations": self.max_iterations,
                "truncated": True,
            }

        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield {"type": "error", "message": friendly_error(e)}

    def _adapt(self, raw: Any) -> dict:
        """把不同工具注册表的返回值统一成 {ok, data, error}

        必须保证返回 dict:工具写得不严谨(返回 None / 字符串 / 忘了 data 键)时
        不能让整个对话轮次崩掉。
        """
        try:
            out = self.result_adapter(raw)
        except Exception as e:
            log.warning("工具结果归一化失败(按失败处理): %s", e)
            return {"ok": False, "data": None, "error": str(e)}

        if not isinstance(out, dict):
            # 返回了裸值(None / str / list),当成成功数据包起来
            return {"ok": True, "data": out, "error": None}

        ok = out.get("ok")
        if ok is None:
            ok = "error" not in out
        return {
            "ok": bool(ok),
            "data": out.get("data", out),
            "error": out.get("error") if not ok else None,
        }

    # ---------------- 主循环(结构化) ----------------
    async def aloop(self, messages: list) -> AgentOutcome:
        """跑完拿结果;丢弃 text_delta 事件"""
        async for evt in self.astream(messages):
            if evt.get("type") == "error":
                raise AgentError(evt.get("message") or "agent 执行失败")
        return AgentOutcome(
            reply=self._reply,
            actions=self.actions,
            pending=self.pending,
            iterations=self._iterations,
            truncated=self._truncated,
            new_messages=self.new_messages,
        )
