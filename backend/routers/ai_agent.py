"""
AI Agent 端点:支持增删改查 + 聚合查询的统一入口
- POST /api/ai/agent:接收用户消息,运行 Function Calling 主循环
- POST /api/ai/agent/confirm:执行已确认的破坏性动作
- POST /api/ai/agent/reset:清空会话历史
"""
import json
import time
from datetime import date, datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI, OpenAIError

from config import settings
from utils.deps import get_current_user
from utils.ai_crud_tools import (
    TOOLS, DESTRUCTIVE_TOOLS, execute_tool, summarize_action_for_user
)
from utils import ai_crud_session as ai_session

router = APIRouter(prefix="/api/ai/agent", tags=["ai-agent"])


SYSTEM_PROMPT = """你是"习惯管家"的智能助手,帮用户管理待办、目标、收支、饮食。

【核心规则】
1. 严格按用户输入的意图执行,不要自作主张加东西或加品类
2. 数量、类型必须精确匹配用户说的;用户说"一个"就是 1 个,说"待办"就只生成待办
3. 涉及"删/改/完成"等破坏性操作前,必须先用对应的 list_* 工具查询目标
4. 查询返回多个匹配项时:如果能根据上下文确定唯一目标(最新/唯一/完全匹配),自动选它;否则用文字回复问用户
5. "刚才那个" / "那个" / "它" 等指代表达,要从前面的对话历史中找最近提过的那一个
6. 日期理解:今天={today},昨天={yesterday},明天={tomorrow};"最近"指 7 天内
7. 调用工具后,用一句话中文总结结果,不要堆砌细节

【已开放的工具】共 17 个:增(add_todo/goal/transaction/meal)+查(list_*)+改(update_*)+删(delete_*)+聚合(aggregate_*)

【回复风格】
- 简洁自然,1-3 句中文
- 数字用阿拉伯数字
- 不要复述工具调用结果原文,自己组织语言
"""


# ============================================================
# 请求/响应模型
# ============================================================

class AgentRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model_id: Optional[int] = None  # 可选:用哪个 LLM 模型


class ConfirmRequest(BaseModel):
    session_id: str
    message: Optional[str] = "确认"  # 用户的确认词


class ResetRequest(BaseModel):
    session_id: str


# ============================================================
# 工具函数
# ============================================================

def _json_safe(obj):
    """递归把 datetime/date/Decimal 等不可 JSON 序列化的值转成字符串"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
    except Exception:
        pass
    return obj


def _get_client_and_model(model_id: Optional[int]):
    """
    拿到 LLM client + model_name。
    model_id 提供则查 user/system 模型;否则用默认 .env 配置。
    """
    if model_id:
        try:
            from utils.llm_factory import get_llm_client_by_id
            client, model_name = get_llm_client_by_id(model_id)
            return client, model_name
        except Exception as e:
            print(f"[ai_agent] model_id={model_id} 加载失败,使用默认: {e}")

    return (
        OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL),
        settings.CHAT_MODEL
    )


def _date_context():
    today = date.today()
    yesterday = today.toordinal() - 1
    y_date = date.fromordinal(yesterday)
    tomorrow = today.toordinal() + 1
    t_date = date.fromordinal(tomorrow)
    return today.strftime("%Y-%m-%d"), y_date.strftime("%Y-%m-%d"), t_date.strftime("%Y-%m-%d")


def _infer_intent(actions: list) -> str:
    """从执行的工具列表反推用户意图"""
    if not actions:
        return "chat"
    tool_to_intent = {
        "add_todo": "create", "add_goal": "create", "add_transaction": "create", "add_meal": "create",
        "update_todo": "update", "update_goal": "update", "update_transaction": "update",
        "delete_todo": "delete", "delete_goal": "delete", "delete_transaction": "delete", "delete_meal": "delete",
        "list_todos": "read", "list_goals": "read", "list_transactions": "read", "list_meals": "read",
        "aggregate_transactions": "aggregate", "aggregate_todos": "aggregate", "aggregate_goals": "aggregate",
    }
    intents = [tool_to_intent.get(a["tool"], "chat") for a in actions]
    # 优先返回破坏性(更值得提示)
    for prio in ("delete", "update", "create", "aggregate", "read", "chat"):
        if prio in intents:
            return prio
    return "chat"


# ============================================================
# 主端点
# ============================================================

@router.post("/")
def agent(req: AgentRequest, current_user: int = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(400, "请输入消息")

    try:
        session_id, session = ai_session.get_or_create(req.session_id, current_user)
    except ai_session.SessionPermissionDenied as e:
        raise HTTPException(403, str(e))

    history: list = session["history"]

    # 1) 把用户消息加入历史
    ai_session.append_history(session_id, current_user, {"role": "user", "content": req.message})

    # 2) 调用 LLM 主循环
    client, model_name = _get_client_and_model(req.model_id)
    today, yesterday, tomorrow = _date_context()
    system = SYSTEM_PROMPT.format(
        today=today, yesterday=yesterday, tomorrow=tomorrow
    )

    actions_taken = []      # 已实际执行的(读/增/聚合一类)
    pending_destructive = []  # 待确认的(改/删)
    last_assistant_text = ""
    iterations = 0
    max_iterations = 5

    try:
        while iterations < max_iterations:
            iterations += 1

            messages = [{"role": "system", "content": system}] + history
            response = client.chat.completions.create(
                model=model_name,
                tools=TOOLS,
                messages=messages,
                temperature=0.3,
            )
            msg = response.choices[0].message
            last_assistant_text = msg.content or ""

            # 没有 tool_calls:模型给出最终回答
            if not msg.tool_calls:
                ai_session.append_history(session_id, current_user, {
                    "role": "assistant", "content": last_assistant_text
                })
                break

            # 有 tool_calls:执行每一个
            history.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in msg.tool_calls
                ]
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                if tool_name in DESTRUCTIVE_TOOLS:
                    # 破坏性:暂存,不执行
                    preview = summarize_action_for_user(tool_name, args, current_user)
                    pending_destructive.append({
                        "tool": tool_name,
                        "args": args,
                        "preview": preview
                    })
                    result_for_llm = {
                        "status": "pending_confirmation",
                        "message": f"动作『{preview}』已暂存,等待用户确认"
                    }
                else:
                    # 安全:直接执行
                    r = execute_tool(tool_name, args, current_user)
                    actions_taken.append({
                        "tool": tool_name,
                        "args": args,
                        "result": r
                    })
                    result_for_llm = r

                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result_for_llm, ensure_ascii=False, default=str)
                })
        else:
            # 达到 max_iterations
            last_assistant_text = "操作太复杂了,请简化后重试。"

    except OpenAIError as e:
        raise HTTPException(500, f"AI 服务异常: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"处理失败: {str(e)}")

    # 3) 决定响应:有待确认动作 → 要求确认;否则返回结果
    # 去重:同样的 (tool, args) 重复出现只保留一次(LLM 多轮调用常见)
    seen = set()
    deduped = []
    for a in pending_destructive:
        key = (a["tool"], json.dumps(a["args"], sort_keys=True, ensure_ascii=False))
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    pending_destructive = deduped

    if pending_destructive:
        # 暂存待确认动作(不立即执行)
        ai_session.set_pending(session_id, current_user, pending_destructive, req.message, last_assistant_text)
        # 构造人话确认提示
        preview_lines = [f"{i+1}. {a['preview']}" for i, a in enumerate(pending_destructive)]
        if len(pending_destructive) == 1:
            confirm_msg = f"即将{pending_destructive[0]['preview']},是否继续?\n\n{preview_lines[0]}"
        else:
            confirm_msg = f"将执行以下 {len(pending_destructive)} 项操作:\n" + "\n".join(preview_lines) + "\n\n是否继续?"

        return {
            "intent": _infer_intent([{"tool": a["tool"]} for a in pending_destructive]),
            "summary": last_assistant_text or confirm_msg,
            "confirmation_request": confirm_msg,
            "actions": _json_safe(actions_taken),
            "pending_actions": pending_destructive,
            "needs_confirmation": True,
            "session_id": session_id,
        }

    # 全部执行完毕
    return {
        "intent": _infer_intent(actions_taken),
        "summary": last_assistant_text or "已处理",
        "actions": _json_safe(actions_taken),
        "needs_confirmation": False,
        "session_id": session_id,
    }


# ============================================================
# 确认端点
# ============================================================

@router.post("/confirm")
def confirm(req: ConfirmRequest, current_user: int = Depends(get_current_user)):
    """执行已暂存的破坏性动作"""
    try:
        pending = ai_session.get_pending(req.session_id, current_user)
    except ai_session.SessionNotFound:
        raise HTTPException(404, "会话不存在或已过期,请重新发送消息")
    except ai_session.SessionPermissionDenied:
        raise HTTPException(403, "无权访问该会话")

    if not pending:
        raise HTTPException(400, "没有待确认的操作,可能已过期或已执行")

    results = []
    for action in pending:
        r = execute_tool(action["tool"], action["args"], current_user)
        results.append({
            "tool": action["tool"],
            "args": action["args"],
            "preview": action.get("preview"),
            "result": r
        })

    ai_session.clear_pending(req.session_id, current_user)
    ai_session.append_history(req.session_id, current_user, {
        "role": "user", "content": req.message or "确认"
    })

    # 总结结果
    success = [r for r in results if "error" not in r["result"]]
    failed = [r for r in results if "error" in r["result"]]
    parts = []
    for r in success:
        p = r["preview"] or r["tool"]
        parts.append(f"{p} ✓")
    if failed:
        for r in failed:
            parts.append(f"{r['preview']} ✗ ({r['result'].get('error')})")

    summary = "; ".join(parts) if parts else "已完成"

    ai_session.append_history(req.session_id, current_user, {
        "role": "assistant", "content": summary
    })

    return {
        "intent": _infer_intent(results),
        "summary": summary,
        "actions": _json_safe(results),
        "needs_confirmation": False,
        "session_id": req.session_id,
    }


# ============================================================
# 重置端点
# ============================================================

@router.post("/reset")
def reset(req: ResetRequest, current_user: int = Depends(get_current_user)):
    """清空会话历史(用户主动清空对话)"""
    try:
        ai_session.reset_session(req.session_id, current_user)
    except ai_session.SessionNotFound:
        pass  # 已经不存在,无所谓
    except ai_session.SessionPermissionDenied:
        raise HTTPException(403, "无权访问该会话")
    return {"ok": True, "session_id": req.session_id}
