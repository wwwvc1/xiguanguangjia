"""数据洞察 API

- GET  /api/stats/patterns      习惯模式识别(缓存 300s)
- GET  /api/stats/correlation   跨维度关联(缓存 300s)
- POST /api/ai/insights         AI 智能建议(缓存 1800s)

改造点:全部从同步 `def` + 每次新建连接,改成 async + 连接池 + 缓存。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends

from core import cache
from core.config import settings
from repositories import transaction_repo
from services import stats_service
from utils.deps import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])
insights_router = APIRouter(prefix="/api/ai", tags=["ai_insights"])


@router.get("/patterns")
async def get_patterns(current_user: int = Depends(get_current_user)):
    return await stats_service.patterns(current_user)


@router.get("/correlation")
async def get_correlation(current_user: int = Depends(get_current_user)):
    return await stats_service.correlation(current_user)


# ============================================================
# AI 智能建议
# ============================================================
@insights_router.post("/insights")
async def get_ai_insights(current_user: int = Depends(get_current_user)):
    """基于 stats 摘要调 LLM 给 3 条建议。

    结果缓存 30 分钟 —— 输入(完成率 / 收支 / streak)本来就不会秒级变化,
    而 LLM 调用是整个首页最贵的一步。
    """
    key = cache.cache_key("insights", current_user)
    cached = await cache.aget_cached(key, await cache.asnapshot(current_user, "todo", "tx", "checkin"))
    if cached is not None:
        return cached

    patterns = await stats_service.patterns(current_user)
    summary = patterns.get("summary", {})
    weekday_stats = patterns.get("todo_weekday_stats", [])
    best_day = max(weekday_stats, key=lambda x: x.get("completion_rate", 0)) if weekday_stats else None
    worst_day = min(weekday_stats, key=lambda x: x.get("completion_rate", 0)) if weekday_stats else None

    tx_summary = await transaction_repo.sum_by_type(current_user, 7)

    best_text = f"{best_day['weekday']} {best_day['completion_rate']}%" if best_day else "暂无"
    worst_text = f"{worst_day['weekday']} {worst_day['completion_rate']}%" if worst_day else "暂无"
    tx_text = (
        f"本周收入 ¥{tx_summary.get('income', {}).get('total', 0)},"
        f"支出 ¥{tx_summary.get('expense', {}).get('total', 0)}"
    )

    prompt = f"""你是习惯管家 AI 助手。根据用户数据给出 3 条具体、可执行的中文建议(每条 ≤30 字,友好语气):

用户概况:
- 整体完成率: {summary.get('overall_completion_rate', 0)}%
- 连续打卡: {summary.get('streak_days', 0)} 天
- 最佳完成日: {best_text}
- 最差完成日: {worst_text}
- 本周收支: {tx_text}

只返回 3 条建议,每条一行,前面用数字编号。不要其他内容。"""

    suggestions: list[str] = []
    try:
        from utils.llm_admin import admin_chat_async, ADMIN_SESSION
        text = await admin_chat_async(
            system_prompt="你是习惯管家 AI 助手。回答必须用中文,简洁、具体、可执行。",
            user_message=prompt,
            session_id=f"{ADMIN_SESSION}_insights_{current_user}",
        )
        for line in (text or "").split("\n"):
            line = line.strip().lstrip("0123456789.、) ").strip()
            if line and len(line) > 4:
                suggestions.append(line)
        suggestions = suggestions[:3]
    except Exception as e:
        print(f"[insights] LLM 调用失败,使用降级建议: {e}")

    if not suggestions:
        suggestions = [
            f"你近 30 天完成率 {summary.get('overall_completion_rate', 0)}%,继续保持!",
            f"已连续打卡 {summary.get('streak_days', 0)} 天,别断了",
            "试试在完成度较低的日子设 1-2 个小目标",
        ]

    result = {
        "suggestions": suggestions,
        "summary": summary,
        "generated_at": datetime.now().isoformat(),
    }
    versions = await cache.asnapshot(current_user, "todo", "tx", "checkin")
    await cache.aset_cached(key, result, settings.CACHE_TTL_INSIGHTS, versions)
    return result
