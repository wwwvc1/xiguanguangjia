"""
数据洞察 API
- GET /api/stats/patterns       习惯模式识别
- GET /api/stats/correlation    跨维度关联
- POST /api/ai/insights         AI 智能建议(从 stats 注入 prompt)
"""
from datetime import datetime, timedelta
import json
from fastapi import APIRouter, Depends
from database import get_connection
from utils.deps import get_current_user
from openai import OpenAI
from config import settings
from utils.ai_logging import log_user_message, log_assistant_message
from utils.llm_admin import get_admin_llm_client, admin_chat, ADMIN_SESSION

router = APIRouter(prefix="/api/stats", tags=["stats"])
insights_router = APIRouter(prefix="/api/ai", tags=["ai_insights"])


def _to_date_str(d):
    if isinstance(d, (datetime, )):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


@router.get("/patterns")
def get_patterns(current_user: int = Depends(get_current_user)):
    """
    习惯模式识别:
    - 最佳/最差完成日(按 weekday 聚合 todos)
    - 完成率趋势(过去 30 天)
    - 类别偏好(收支分类统计)
    - 连续打卡天数(streak)
    """
    conn = get_connection()
    result = {
        "todo_weekday_stats": [],  # [{weekday, total, done, completion_rate}]
        "completion_trend": [],    # [{date, total, done, rate}]
        "tx_category_stats": [],   # [{category, type, total}]
        "streak_days": 0,
        "summary": {}
    }
    try:
        with conn.cursor() as cursor:
            # 1. 周末/工作日完成率(过去 60 天)
            cursor.execute(
                """SELECT DAYOFWEEK(due_date) AS dow, COUNT(*) AS total,
                          SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count
                   FROM todos
                   WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
                     AND due_date IS NOT NULL
                   GROUP BY DAYOFWEEK(due_date)
                   ORDER BY dow""",
                (current_user,)
            )
            rows = cursor.fetchall()
            # DAYOFWEEK: 1=Sunday ... 7=Saturday
            dow_map = {1: "周日", 2: "周一", 3: "周二", 4: "周三", 5: "周四", 6: "周五", 7: "周六"}
            for r in rows:
                total = int(r["total"])
                done = int(r["done_count"] or 0)
                rate = round((done / total) * 100, 1) if total > 0 else 0
                result["todo_weekday_stats"].append({
                    "weekday": dow_map.get(r["dow"], str(r["dow"])),
                    "dow": r["dow"],
                    "total": total,
                    "done": done,
                    "completion_rate": rate
                })

            # 2. 30 天完成率趋势
            cursor.execute(
                """SELECT due_date AS dt, COUNT(*) AS total,
                          SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count
                   FROM todos
                   WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                     AND due_date IS NOT NULL
                   GROUP BY due_date
                   ORDER BY due_date""",
                (current_user,)
            )
            for r in cursor.fetchall():
                total = int(r["total"])
                done = int(r["done_count"] or 0)
                rate = round((done / total) * 100, 1) if total > 0 else 0
                result["completion_trend"].append({
                    "date": _to_date_str(r["dt"]),
                    "total": total,
                    "done": done,
                    "rate": rate
                })

            # 3. 收支分类统计(过去 30 天)
            cursor.execute(
                """SELECT category, type, COUNT(*) AS cnt, SUM(ABS(amount)) AS total
                   FROM transactions
                   WHERE user_id = %s AND time >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                   GROUP BY category, type
                   ORDER BY total DESC""",
                (current_user,)
            )
            for r in cursor.fetchall():
                result["tx_category_stats"].append({
                    "category": r["category"],
                    "type": r["type"],
                    "count": int(r["cnt"]),
                    "total": float(r["total"])
                })

            # 4. 连续打卡天数(与 /api/checkins/streak 算法一致:读 checkins 表)
            cursor.execute(
                """SELECT DISTINCT checkin_date AS dt
                   FROM checkins
                   WHERE user_id = %s AND checkin_date <= CURDATE()
                   ORDER BY dt DESC""",
                (current_user,)
            )
            dates = [r["dt"] for r in cursor.fetchall() if r.get("dt")]
            streak = 0
            today = datetime.now().date()
            expected = today
            # 允许今天没打卡(从昨天开始算)
            if dates and dates[0] != today and dates[0] != today - timedelta(days=1):
                streak = 0
            else:
                for d in dates:
                    if d == expected:
                        streak += 1
                        expected = expected - timedelta(days=1)
                    elif d < expected:
                        break
            result["streak_days"] = streak

            # 5. 汇总
            total_done = sum(int(s["done"]) for s in result["todo_weekday_stats"])
            total_todos = sum(int(s["total"]) for s in result["todo_weekday_stats"])
            overall_rate = round((total_done / total_todos) * 100, 1) if total_todos > 0 else 0
            result["summary"] = {
                "overall_completion_rate": overall_rate,
                "total_todos_60d": total_todos,
                "streak_days": streak,
                "tx_count_30d": sum(int(s["count"]) for s in result["tx_category_stats"])
            }
    finally:
        conn.close()
    return result


@router.get("/correlation")
def get_correlation(current_user: int = Depends(get_current_user)):
    """
    跨维度关联:
    - 运动量(todo 关键词) ↔ 当日热量(meals)
    - 支出 ↔ 完成率
    - 早起 ↔ 完成率
    """
    conn = get_connection()
    result = {
        "insights": []
    }
    try:
        with conn.cursor() as cursor:
            # 1. 运动日 vs 饮食热量
            # 标记每天是否做了"运动"类待办(关键词匹配)
            cursor.execute(
                """SELECT due_date AS dt, text, done
                   FROM todos
                   WHERE user_id = %s AND due_date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
                     AND due_date IS NOT NULL""",
                (current_user,)
            )
            todos_by_date = {}
            for r in cursor.fetchall():
                d = _to_date_str(r["dt"])
                todos_by_date.setdefault(d, []).append({
                    "text": r["text"] or "",
                    "done": bool(r["done"])
                })

            cursor.execute(
                """SELECT date, SUM(total_calories) AS cal
                   FROM meals
                   WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
                   GROUP BY date""",
                (current_user,)
            )
            cal_by_date = { _to_date_str(r["date"]): float(r["cal"] or 0) for r in cursor.fetchall() }

            exercise_keywords = ["运动", "跑", "健身", "瑜伽", "打球", "游泳", "锻炼", "步行", "走路"]
            exercise_days = []
            rest_days = []
            for d, items in todos_by_date.items():
                if d not in cal_by_date:
                    continue
                has_exercise = any(
                    item["done"] and any(kw in (item["text"] or "") for kw in exercise_keywords)
                    for item in items
                )
                if has_exercise:
                    exercise_days.append(cal_by_date[d])
                else:
                    rest_days.append(cal_by_date[d])

            if exercise_days and rest_days:
                avg_ex = sum(exercise_days) / len(exercise_days)
                avg_rest = sum(rest_days) / len(rest_days)
                diff = avg_ex - avg_rest
                if abs(diff) > 50:
                    result["insights"].append({
                        "title": "运动日 vs 休息日的饮食差异",
                        "detail": f"运动日平均摄入 {int(avg_ex)} kcal,休息日 {int(avg_rest)} kcal,差异 {int(abs(diff))} kcal",
                        "type": "exercise_calorie",
                        "direction": "up" if diff > 0 else "down"
                    })

            # 2. 支出日 vs 完成率
            cursor.execute(
                """SELECT DATE(time) AS dt, SUM(ABS(amount)) AS total
                   FROM transactions
                   WHERE user_id = %s AND type = 'expense'
                     AND time >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
                   GROUP BY DATE(time)""",
                (current_user,)
            )
            expense_by_date = { _to_date_str(r["dt"]): float(r["total"] or 0) for r in cursor.fetchall() }

            high_expense_done = []
            low_expense_done = []
            for d, items in todos_by_date.items():
                if not items:
                    continue
                exp = expense_by_date.get(d, 0)
                done_count = sum(1 for it in items if it["done"])
                rate = done_count / len(items) if items else 0
                if exp > 100:
                    high_expense_done.append(rate)
                else:
                    low_expense_done.append(rate)

            if high_expense_done and low_expense_done and len(high_expense_done) >= 3 and len(low_expense_done) >= 3:
                avg_high = sum(high_expense_done) / len(high_expense_done)
                avg_low = sum(low_expense_done) / len(low_expense_done)
                if abs(avg_high - avg_low) > 0.15:
                    result["insights"].append({
                        "title": "支出与待办完成率",
                        "detail": f"大额支出日(>¥100)完成率 {int(avg_high*100)}%,普通日 {int(avg_low*100)}%",
                        "type": "expense_completion",
                        "direction": "down" if avg_high < avg_low else "up"
                    })

            # 3. 早起的待办完成率(早于 8:00 创建的 todo 是否更易完成)
            # 用 created_at 简化处理
            cursor.execute(
                """SELECT HOUR(created_at) AS h, done FROM todos
                   WHERE user_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL 60 DAY)""",
                (current_user,)
            )
            morning_done = 0
            morning_total = 0
            for r in cursor.fetchall():
                if r["h"] < 8:
                    morning_total += 1
                    if r["done"]:
                        morning_done += 1

            if morning_total >= 5:
                rate = morning_done / morning_total
                result["insights"].append({
                    "title": "早起习惯",
                    "detail": f"早起(早 8 点前)创建待办共 {morning_total} 条,完成率 {int(rate*100)}%",
                    "type": "morning_habit",
                    "rate": rate
                })
    finally:
        conn.close()

    if not result["insights"]:
        result["insights"].append({
            "title": "数据积累中",
            "detail": "继续记录 2 周,这里会显示你的个性化关联分析",
            "type": "insufficient"
        })
    return result


# ============== AI 智能建议 ==============
@insights_router.post("/insights")
def get_ai_insights(current_user: int = Depends(get_current_user)):
    """
    AI 智能建议:取 stats + 用户数据,调 LLM 返 3 条建议
    (无 Redis 缓存层,简单直接)
    """
    # 复用 patterns 数据
    patterns = get_patterns(current_user)
    summary = patterns.get("summary", {})
    weekday_stats = patterns.get("todo_weekday_stats", [])
    best_day = max(weekday_stats, key=lambda x: x.get("completion_rate", 0)) if weekday_stats else None
    worst_day = min(weekday_stats, key=lambda x: x.get("completion_rate", 0)) if weekday_stats else None

    # 抓最近 7 天 tx 摘要
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT type, COUNT(*) AS cnt, SUM(ABS(amount)) AS total
                   FROM transactions
                   WHERE user_id = %s AND time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                   GROUP BY type""",
                (current_user,)
            )
            tx_summary = {r["type"]: {"count": int(r["cnt"]), "total": float(r["total"] or 0)} for r in cursor.fetchall()}
    finally:
        conn.close()

    # 拼 prompt
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

    # 调 LLM(系统默认模型,自动写 ai_chat_logs)
    try:
        text = admin_chat(
            system_prompt="你是习惯管家 AI 助手。回答必须用中文,简洁、具体、可执行。",
            user_message=prompt,
            session_id=f"{ADMIN_SESSION}_insights_{current_user}",
        )
        suggestions = []
        for line in text.split("\n"):
            line = line.strip().lstrip("0123456789.、) ").strip()
            if line and len(line) > 4:
                suggestions.append(line)
        suggestions = suggestions[:3]
    except Exception as e:
        # 失败时也用降级建议(不算成功调用,但 UI 还能用)
        suggestions = [
            f"你近 30 天完成率 {summary.get('overall_completion_rate', 0)}%,继续保持!",
            f"已连续打卡 {summary.get('streak_days', 0)} 天,别断了",
            "试试在完成度较低的日子设 1-2 个小目标"
        ]

    return {
        "suggestions": suggestions,
        "summary": summary,
        "generated_at": datetime.now().isoformat()
    }
