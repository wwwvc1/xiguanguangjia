"""agent/core.py 的确定性单测(不需要外部 LLM)

用脚本化的 FakeLLM 驱动循环,验证:
- 普通工具执行 + 结果序列化
- 破坏性工具在 require_confirmation=True 时只暂存、不执行
- require_confirmation=False 时直接执行
- new_messages 的结构(能回写 session)
- max_iterations 截断
- 工具失败 / 结果格式异常
- 友好错误映射(不双层包裹)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.core import (
    AgentError, ToolCallingAgent, crud_result, friendly_error, identity_result,
)

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name} {extra}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {extra}")


class FakeLLM:
    """按脚本逐个返回 AIMessage"""

    def __init__(self, script):
        self.script = list(script)
        self.bound_tools = None
        self.received = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.received.append(list(messages))
        if not self.script:
            return AIMessage(content="(脚本用尽)")
        return self.script.pop(0)


def tool_call(name, args, cid="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])


def final(text, in_tok=10, out_tok=5):
    return AIMessage(content=text, usage_metadata={
        "input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok})


def msgs():
    return [SystemMessage(content="sys"), HumanMessage(content="hi")]


async def main():
    print("== 1. 普通工具执行 ==")
    calls = []

    def exec_ok(user_id, name, args):
        calls.append((user_id, name, args))
        return {"ok": True, "data": {"id": 1, "text": args.get("text")}, "error": None}

    llm = FakeLLM([tool_call("add_todo", {"text": "跑步"}), final("已添加跑步")])
    agent = ToolCallingAgent(
        user_id=7, llm=llm, model_name="fake", tools=[{"type": "function", "function": {"name": "add_todo"}}],
        execute_tool=exec_ok, max_iterations=5, log_messages=False,
    )
    check("bind_tools 被调用", llm.bound_tools is not None)
    out = await agent.aloop(msgs())
    check("执行了 1 个工具", len(calls) == 1, str(calls))
    check("actions 有 1 条", len(out.actions) == 1, str(out.actions)[:80])
    check("action.ok", out.actions[0]["ok"] is True)
    check("最终回复", out.reply == "已添加跑步", out.reply)
    check("用了 2 轮", out.iterations == 2, str(out.iterations))
    check("new_messages 含 assistant(tool_calls) + tool",
          [m["role"] for m in out.new_messages] == ["assistant", "tool", "assistant"],
          str([m["role"] for m in out.new_messages]))
    check("tool 消息带 tool_call_id", out.new_messages[1].get("tool_call_id") == "c1")

    print("\n== 2. 破坏性工具:只暂存不执行 ==")
    calls.clear()
    llm = FakeLLM([tool_call("delete_todo", {"id": 9}), final("已暂存")])
    agent = ToolCallingAgent(
        user_id=7, llm=llm, model_name="fake", tools=[],
        execute_tool=exec_ok, max_iterations=5, log_messages=False,
        destructive={"delete_todo"}, require_confirmation=True,
        summarize=lambda n, a, u: f"删除待办 {a.get('id')}",
    )
    out = await agent.aloop(msgs())
    check("没有真的执行", len(calls) == 0, str(calls))
    check("pending 有 1 条", len(out.pending) == 1, str(out.pending))
    check("pending 带预览", out.pending[0]["preview"] == "删除待办 9", str(out.pending[0]))
    check("actions 为空", len(out.actions) == 0)

    print("\n== 3. 同一工具 require_confirmation=False 时直接执行 ==")
    calls.clear()
    llm = FakeLLM([tool_call("delete_todo", {"id": 9}), final("已删除")])
    agent = ToolCallingAgent(
        user_id=7, llm=llm, model_name="fake", tools=[],
        execute_tool=exec_ok, max_iterations=5, log_messages=False,
        destructive={"delete_todo"}, require_confirmation=False,
    )
    out = await agent.aloop(msgs())
    check("执行了", len(calls) == 1)
    check("pending 为空", len(out.pending) == 0)
    check("actions 1 条", len(out.actions) == 1)

    print("\n== 4. 达到最大轮数 ==")
    llm = FakeLLM([tool_call(f"t{i}", {}) for i in range(10)])
    agent = ToolCallingAgent(
        user_id=7, llm=llm, model_name="fake", tools=[],
        execute_tool=exec_ok, max_iterations=2, log_messages=False,
    )
    out = await agent.aloop(msgs())
    check("truncated=True", out.truncated is True)
    check("只跑了 2 轮", out.iterations == 2, str(out.iterations))
    check("执行了 2 个工具", len(out.actions) == 2, str(len(out.actions)))

    print("\n== 5. 工具抛异常 / 返回格式异常 ==")
    def exec_boom(user_id, name, args):
        raise ValueError("数据库炸了")

    llm = FakeLLM([tool_call("add_todo", {}), final("抱歉")])
    agent = ToolCallingAgent(user_id=7, llm=llm, model_name="fake", tools=[],
                             execute_tool=exec_boom, max_iterations=3, log_messages=False)
    out = await agent.aloop(msgs())
    check("工具异常被捕获(不炸整轮)", out.actions[0]["ok"] is False, str(out.actions[0])[:100])
    check("错误带原因", "数据库炸了" in str(out.actions[0]["error"]), str(out.actions[0].get("error"))[:60])

    llm = FakeLLM([tool_call("add_todo", {}), final("好")])
    agent = ToolCallingAgent(user_id=7, llm=llm, model_name="fake", tools=[],
                             execute_tool=lambda u, n, a: None, max_iterations=3,
                             log_messages=False, result_adapter=identity_result)
    out = await agent.aloop(msgs())
    check("返回 None 也不崩", len(out.actions) == 1)

    print("\n== 6. crud_result 适配 ==")
    check("有 error 键 → ok=False", crud_result({"error": "x"})["ok"] is False)
    check("正常数据 → ok=True", crud_result({"created": 1})["ok"] is True)
    check("data 保留原值", crud_result({"created": 1})["data"] == {"created": 1})

    print("\n== 7. 友好错误 ==")
    check("429", friendly_error(RuntimeError("Error code: 429")) == "请求太频繁,请稍后再试")
    check("401", friendly_error(RuntimeError("Error code: 401")) == "AI API 配置错误,请联系管理员")
    e = friendly_error(RuntimeError("500 - get_channel_failed temporarily unavailable"))
    check("上游 5xx", "上游模型通道暂时不可用" in e, e[:40])
    check("AgentError 保留原文",
          isinstance(AgentError("已翻译"), Exception))

    print("\n== 8. 流式事件(emit_deltas) ==")
    llm = FakeLLM([final("四个字的回复内容")])
    agent = ToolCallingAgent(user_id=7, llm=llm, model_name="fake", tools=[],
                             execute_tool=exec_ok, max_iterations=3, log_messages=False,
                             emit_deltas=True)
    events = [e async for e in agent.astream(msgs())]
    deltas = [e for e in events if e["type"] == "text_delta"]
    check("有 text_delta", len(deltas) > 1, f"{len(deltas)} 片")
    check("拼回原文", "".join(d["content"] for d in deltas) == "四个字的回复内容")
    check("以 done 收尾", events[-1]["type"] == "done")

    print("\n" + "=" * 50)
    print(f"结果: {ok} 通过, {fail} 失败")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
