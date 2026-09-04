"""
报告生成器
- generate_weekly_report(user_id, period):生成周报并入库
- generate_monthly_report(user_id, period):生成月报并入库
- get_user_reports / get_report
"""
import json
from datetime import datetime, timedelta
from database import get_connection
from openai import OpenAI
from config import settings


def _week_bounds(period: str):
    """period = '2026-W34' → (start_date, end_date)"""
    year, week = period.split("-W")
    year = int(year)
    week = int(week)
    # ISO 周:第 1 周是包含 1 月 4 日的那一周
    jan4 = datetime(year, 1, 4)
    start = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week - 1)
    end = start + timedelta(days=6)
    return start.date(), end.date()


def _month_bounds(period: str):
    """period = '2026-08' → (start_date, end_date)"""
    year, mon = period.split("-")
    year = int(year)
    mon = int(mon)
    start = datetime(year, mon, 1).date()
    if mon == 12:
        end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end = datetime(year, mon + 1, 1).date() - timedelta(days=1)
    return start, end


def _fmt_range(start, end) -> str:
    """把 (date, date) 格式化为 '8月25日-8月31日'"""
    if start.year == end.year and start.month == end.month:
        return f"{start.month}月{start.day}日-{end.day}日"
    if start.year == end.year:
        return f"{start.month}月{start.day}日-{end.month}月{end.day}日"
    return f"{start.year}年{start.month}月{start.day}日-{end.year}年{end.month}月{end.day}日"


def _aggregate(user_id: int, start_date, end_date) -> dict:
    """聚合某段时间的 stats"""
    conn = get_connection()
    stats = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "todos_total": 0,
        "todos_done": 0,
        "completion_rate": 0.0,
        "tx_income": 0.0,
        "tx_expense": 0.0,
        "tx_net": 0.0,
        "meals_count": 0,
        "meals_calories": 0,
        "goals_progress": []
    }
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) AS total, SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) AS done_count
                   FROM todos WHERE user_id = %s AND (due_date BETWEEN %s AND %s OR (due_date IS NULL AND created_at BETWEEN %s AND %s))""",
                (user_id, start_date, end_date, start_date, end_date)
            )
            row = cursor.fetchone()
            stats["todos_total"] = int(row["total"] or 0)
            stats["todos_done"] = int(row["done_count"] or 0)
            stats["completion_rate"] = round((stats["todos_done"] / stats["todos_total"]) * 100, 1) if stats["todos_total"] > 0 else 0

            cursor.execute(
                """SELECT type, COUNT(*) AS cnt, SUM(ABS(amount)) AS total
                   FROM transactions
                   WHERE user_id = %s AND DATE(time) BETWEEN %s AND %s
                   GROUP BY type""",
                (user_id, start_date, end_date)
            )
            for r in cursor.fetchall():
                if r["type"] == "income":
                    stats["tx_income"] = float(r["total"] or 0)
                else:
                    stats["tx_expense"] = float(r["total"] or 0)
            stats["tx_net"] = stats["tx_income"] - stats["tx_expense"]

            cursor.execute(
                """SELECT COUNT(*) AS cnt, SUM(total_calories) AS cal
                   FROM meals WHERE user_id = %s AND date BETWEEN %s AND %s""",
                (user_id, start_date, end_date)
            )
            row = cursor.fetchone()
            stats["meals_count"] = int(row["cnt"] or 0)
            stats["meals_calories"] = float(row["cal"] or 0)

            cursor.execute(
                """SELECT name, progress, done FROM goals
                   WHERE user_id = %s ORDER BY created_at DESC LIMIT 5""",
                (user_id,)
            )
            stats["goals_progress"] = [
                {"name": r["name"], "progress": r["progress"], "done": bool(r["done"])}
                for r in cursor.fetchall()
            ]
    finally:
        conn.close()
    return stats


def _build_content(stats: dict, period_type: str) -> str:
    """用 LLM 生成报告内容(Markdown 格式)"""
    prompt = f"""你是习惯管家 AI,根据用户数据写一份简洁的{('周报' if period_type == 'weekly' else '月报')},用 Markdown,≤300 字,鼓励但不夸张:

数据({stats['start_date']} ~ {stats['end_date']}):
- 待办完成: {stats['todos_done']}/{stats['todos_total']} ({stats['completion_rate']}%)
- 收支: 收入 ¥{stats['tx_income']}, 支出 ¥{stats['tx_expense']}, 结余 ¥{stats['tx_net']}
- 饮食: 记录 {stats['meals_count']} 餐, 共 {int(stats['meals_calories'])} kcal
- 目标进度: {stats['goals_progress']}

请生成 3-5 段,每段一个小标题 + 1-2 句点评。"""

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
        resp = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=600
        )
        return resp.choices[0].message.content or "暂无内容"
    except Exception as e:
        print(f"[Report] LLM 失败,使用降级内容: {e}")
        return (
            f"## {period_type} 报告\n\n"
            f"- 待办完成: {stats['todos_done']}/{stats['todos_total']} ({stats['completion_rate']}%)\n"
            f"- 收支结余: ¥{stats['tx_net']}\n"
            f"- 饮食记录: {stats['meals_count']} 餐\n"
        )


def _save_report(user_id: int, period_type: str, period: str, title: str, content: str, stats: dict):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO reports (user_id, type, period, title, content, stats)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE title=VALUES(title), content=VALUES(content), stats=VALUES(stats), generated_at=NOW()""",
                (user_id, period_type, period, title, content, json.dumps(stats, ensure_ascii=False, default=str))
            )
            conn.commit()
    finally:
        conn.close()


def generate_weekly_report(user_id: int, period: str = None) -> dict:
    """period = '2026-W34' 或 None 表示本周"""
    if not period:
        now = datetime.now()
        iso = now.isocalendar()
        period = f"{iso[0]}-W{iso[1]:02d}"
    start, end = _week_bounds(period)
    stats = _aggregate(user_id, start, end)
    content = _build_content(stats, "weekly")
    date_range = _fmt_range(start, end)
    title = f"{period} 周报({date_range})"
    _save_report(user_id, "weekly", period, title, content, stats)
    return {"period": period, "title": title, "content": content, "stats": stats}


def generate_monthly_report(user_id: int, period: str = None) -> dict:
    if not period:
        now = datetime.now()
        period = f"{now.year}-{now.month:02d}"
    start, end = _month_bounds(period)
    stats = _aggregate(user_id, start, end)
    content = _build_content(stats, "monthly")
    date_range = _fmt_range(start, end)
    title = f"{period} 月报({date_range})"
    _save_report(user_id, "monthly", period, title, content, stats)
    return {"period": period, "title": title, "content": content, "stats": stats}


def list_reports(user_id: int, period_type: str = None) -> list:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if period_type:
                cursor.execute(
                    "SELECT id, type, period, title, generated_at FROM reports WHERE user_id = %s AND type = %s ORDER BY generated_at DESC",
                    (user_id, period_type)
                )
            else:
                cursor.execute(
                    "SELECT id, type, period, title, generated_at FROM reports WHERE user_id = %s ORDER BY generated_at DESC",
                    (user_id,)
                )
            rows = cursor.fetchall()
            for r in rows:
                if r.get("generated_at"):
                    r["generated_at"] = str(r["generated_at"])
            return rows
    finally:
        conn.close()


def get_report(user_id: int, report_id: int) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, type, period, title, content, stats, generated_at FROM reports WHERE user_id = %s AND id = %s",
                (user_id, report_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row.get("generated_at"):
                row["generated_at"] = str(row["generated_at"])
            if row.get("stats") and isinstance(row["stats"], str):
                try:
                    row["stats"] = json.loads(row["stats"])
                except Exception:
                    pass
            return row
    finally:
        conn.close()
