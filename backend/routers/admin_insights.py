"""管理后台 / 运营端专用接口
- 真实数据洞察(Web 数据洞察页用)
- 数据资产下钻(7 张卡片)
- AI 解读 / AI 运营建议 / AI 系统日志总结
- 全部用系统默认模型 + 自动留痕
"""
import json
import math
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from database import get_connection
from utils.admin_auth import get_current_admin
from utils.llm_admin import admin_chat, ADMIN_SESSION, get_admin_llm_client

router = APIRouter(prefix="/api/admin/insights", tags=["admin-insights"])


def _safe_num(x, default=0):
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _bucket_date(s):
    return str(s)[:10] if s else None


# ============== 1. 总览:用户活跃 / 数据增长 ==============

@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=180), admin: dict = Depends(get_current_admin)):
    """平台总览:用户数、DAU、活跃率、数据增长"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 总用户数
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            total_users = int(cursor.fetchone()["c"])
            # 7 日活跃(有 checkin 或 todo 或 tx)
            cursor.execute(
                """SELECT COUNT(DISTINCT user_id) AS c FROM checkins
                   WHERE checkin_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"""
            )
            dau7 = int(cursor.fetchone()["c"])
            # 30 日新增用户(基于 last_login_at / created_at)
            cursor.execute(
                "SELECT COUNT(*) AS c FROM users WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)",
                (days,)
            )
            new_users = int(cursor.fetchone()["c"])
            # 各业务表总量
            cursor.execute(
                """SELECT
                    (SELECT COUNT(*) FROM todos) AS todos,
                    (SELECT COUNT(*) FROM goals) AS goals,
                    (SELECT COUNT(*) FROM transactions) AS transactions,
                    (SELECT COUNT(*) FROM meals) AS meals,
                    (SELECT COUNT(*) FROM reminders) AS reminders,
                    (SELECT COUNT(*) FROM achievements) AS achievements,
                    (SELECT COUNT(*) FROM reports) AS reports,
                    (SELECT COUNT(*) FROM ai_chat_logs) AS ai_calls,
                    (SELECT COUNT(*) FROM operation_logs) AS op_logs"""
            )
            data = cursor.fetchone()
            return {
                "total_users": total_users,
                "dau_7d": dau7,
                "active_rate_7d": round(dau7 / total_users * 100, 1) if total_users else 0,
                f"new_users_{days}d": new_users,
                "data_totals": {
                    k: int(v or 0) for k, v in data.items()
                }
            }
    finally:
        conn.close()


# ============== 2. 散点图:用户活跃天数 vs 完成率 ==============

@router.get("/scatter")
def scatter(
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(220, ge=10, le=2000),
    admin: dict = Depends(get_current_admin)
):
    """每个用户:近 N 天有数据的活跃天数 vs 完成率(基于 todos)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""SELECT u.id AS user_id, u.username, u.nickname,
                          COALESCE(SUM(t.done), 0) AS done_count,
                          COALESCE(COUNT(t.id), 0) AS total_count,
                          COALESCE(COUNT(DISTINCT DATE(COALESCE(t.due_date, t.created_at))), 0) AS active_days
                   FROM users u
                   LEFT JOIN todos t ON t.user_id = u.id
                     AND COALESCE(t.due_date, t.created_at) >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                   GROUP BY u.id, u.username, u.nickname
                   HAVING total_count > 0
                   ORDER BY active_days DESC
                   LIMIT %s""",
                (days, limit)
            )
            points = []
            for r in cursor.fetchall():
                total = int(r["total_count"])
                done = int(r["done_count"])
                rate = round(done / total * 100, 1) if total else 0
                points.append({
                    "user_id": r["user_id"],
                    "username": r["username"] or r["nickname"] or f"#{r['user_id']}",
                    "days": int(r["active_days"]),
                    "completion": rate,
                    "total": total,
                    "done": done,
                })
            return {"points": points, "days": days}
    finally:
        conn.close()


# ============== 3. 折线图:30 日活跃用户 + 趋势 ==============

@router.get("/trend")
def trend(days: int = Query(30, ge=7, le=90), admin: dict = Depends(get_current_admin)):
    """每日活跃用户数(checkins)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""SELECT checkin_date AS dt, COUNT(DISTINCT user_id) AS cnt
                   FROM checkins
                   WHERE checkin_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                   GROUP BY checkin_date ORDER BY checkin_date""",
                (days,)
            )
            rows = cursor.fetchall()
            series = [{"date": str(r["dt"]), "value": int(r["cnt"])} for r in rows]
            return {"series": series, "days": days}
    finally:
        conn.close()


# ============== 4. 柱状图:24 时段打卡分布 ==============

@router.get("/hourly")
def hourly(admin: dict = Depends(get_current_admin)):
    """过去 30 天,24 个小时段中打卡(checkins)的用户数"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT HOUR(created_at) AS h, COUNT(*) AS cnt
                   FROM checkins
                   WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                   GROUP BY h ORDER BY h"""
            )
            rows = cursor.fetchall()
            by_hour = {int(r["h"]): int(r["cnt"]) for r in rows}
            buckets = [{"hour": h, "value": by_hour.get(h, 0)} for h in range(24)]
            return {"buckets": buckets}
    finally:
        conn.close()


# ============== 5. 热力图:周×小时 ==============

@router.get("/heatmap")
def heatmap(admin: dict = Depends(get_current_admin)):
    """过去 30 天,周几(0-6) × 小时(0-23) 的活跃度(基于 checkins)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT DAYOFWEEK(created_at) AS dow, HOUR(created_at) AS h, COUNT(*) AS cnt
                   FROM checkins
                   WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                   GROUP BY dow, h"""
            )
            rows = cursor.fetchall()
            grid = {}
            for r in rows:
                d = (int(r["dow"]) - 1) % 7  # 0=Sun
                h = int(r["h"])
                grid[f"{d}-{h}"] = int(r["cnt"])
            cells = [
                {"dow": d, "hour": h, "value": grid.get(f"{d}-{h}", 0)}
                for d in range(7) for h in range(24)
            ]
            return {"cells": cells}
    finally:
        conn.close()


# ============== 6. 数据资产下钻 ==============

# 每个表独有的"展示列",动态拼 SELECT,避免 Unknown column 500
DATA_TABLES = {
    # type: (table, id_col, time_col, extra_columns)
    "todos":        ("todos",        "id", "created_at", ["text", "done", "due_date"]),
    "goals":        ("goals",        "id", "created_at", ["name", "progress", "done"]),
    "transactions": ("transactions", "id", "time",       ["category", "amount", "type", "description"]),
    "meals":        ("meals",        "id", "date",       ["meal_type", "total_calories"]),
    "reminders":    ("reminders",    "id", "created_at", ["type", "time", "enabled"]),
    "achievements": ("achievements", "id", "created_at", ["code", "status", "unlocked_at"]),
    "reports":      ("reports",      "id", "generated_at", ["title", "type", "period"]),
}


@router.get("/data-asset/{type}")
def data_asset(
    type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    admin: dict = Depends(get_current_admin)
):
    """下钻某张表的真实数据 + 用户名(动态 SELECT,只取本表存在的列)"""
    if type not in DATA_TABLES:
        return {"rows": [], "total": 0, "type": type, "error": f"unknown type: {type}"}
    table, id_col, time_col, extra_cols = DATA_TABLES[type]

    # 动态 SELECT — 每个表只取存在的列
    select_cols = ["t." + id_col + " AS id", "t." + time_col + " AS t", "t.user_id", "u.username", "u.nickname"]
    for c in extra_cols:
        select_cols.append(f"t.{c}")

    where = ["1=1"]
    params = []
    if user_id is not None:
        where.append("t.user_id = %s")
        params.append(user_id)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS c FROM {table} t WHERE " + " AND ".join(where),
                tuple(params)
            )
            total = int(cursor.fetchone()["c"])

            offset = (page - 1) * page_size
            cursor.execute(
                f"SELECT {', '.join(select_cols)} FROM {table} t "
                f"LEFT JOIN users u ON u.id = t.user_id "
                f"WHERE " + " AND ".join(where) + " "
                f"ORDER BY t.{time_col} DESC LIMIT %s OFFSET %s",
                tuple(params) + (page_size, offset)
            )
            rows = cursor.fetchall()
            # 时间/枚举字段转字符串
            for r in rows:
                if r.get("t"):
                    r["t"] = str(r["t"])
                for k, v in list(r.items()):
                    if hasattr(v, "isoformat"):  # datetime/date
                        r[k] = v.isoformat()
                    elif isinstance(v, (bytes,)):
                        r[k] = v.decode("utf-8", errors="ignore")
            return {
                "type": type,
                "page": page,
                "page_size": page_size,
                "total": total,
                "rows": rows,
            }
    except Exception as e:
        print(f"[data-asset/{type}] SQL 错误: {e}")
        return {"type": type, "page": page, "page_size": page_size, "total": 0, "rows": [], "error": str(e)}
    finally:
        conn.close()


# ============== 7. AI 解读:全平台运营建议 ==============

@router.post("/ai-summary")
def ai_insights_summary(admin: dict = Depends(get_current_admin)):
    """AI 运营建议:基于全平台数据,生成 3-5 条管理者视角的建议。
    用系统默认模型 + 自动留痕(走 utils/llm_admin)。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 拉全平台关键数据
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            total_users = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(DISTINCT user_id) AS c FROM checkins WHERE checkin_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
            dau7 = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM checkins")
            total_checkins = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM todos")
            total_todos = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM transactions")
            total_tx = int(cursor.fetchone()["c"])
            cursor.execute(
                """SELECT user_id, COUNT(*) AS cnt
                   FROM operation_logs
                   WHERE action LIKE 'edit_knowledge_doc' OR action LIKE 'delete_knowledge_doc'
                   GROUP BY user_id ORDER BY cnt DESC LIMIT 5"""
            )
            top_admin = cursor.fetchall()
            # AI 用量 7 天
            cursor.execute("SELECT COUNT(*) AS c FROM ai_chat_logs WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
            ai_calls_7d = int(cursor.fetchone()["c"])
            return {
                "summary": {
                    "total_users": total_users,
                    "dau_7d": dau7,
                    "active_rate_7d": round(dau7 / total_users * 100, 1) if total_users else 0,
                    "total_checkins": total_checkins,
                    "total_todos": total_todos,
                    "total_transactions": total_tx,
                    "ai_calls_7d": ai_calls_7d,
                    "top_kb_admins": [{"user_id": r["user_id"], "edits": int(r["cnt"])} for r in top_admin],
                }
            }
    finally:
        conn.close()


@router.post("/ai-summary/run")
def ai_insights_summary_run(admin: dict = Depends(get_current_admin)):
    """真正调 LLM 跑运营建议(summary 已准备好,这里跑)"""
    base = ai_insights_summary(admin=admin)
    s = base["summary"]
    prompt = f"""你是「习惯管家」运营顾问,根据平台数据给 3-5 条**可执行**的中文建议(每条 ≤ 60 字):

平台总览:
- 注册用户: {s['total_users']},近 7 日活跃: {s['dau_7d']}(活跃率 {s['active_rate_7d']}%)
- 累计打卡: {s['total_checkins']} 次,累计待办: {s['total_todos']} 条,累计收支: {s['total_transactions']} 笔
- 近 7 日 AI 调用: {s['ai_calls_7d']} 次
- 知识库高频编辑者 Top5: {s['top_kb_admins']}

按"用户增长 / 活跃度 / 内容运营 / 风险" 4 个角度分别给建议。每条单独一行,前面用 `## 类别 -` 开头。
"""
    try:
        text = admin_chat(
            system_prompt="你是习惯管家平台的 AI 运营顾问。回答必须用中文,简洁、具体、可执行。",
            user_message=prompt,
            session_id=f"{ADMIN_SESSION}_insights_summary",
        )
        return {**base, "ai_advice": text}
    except Exception as e:
        return {**base, "ai_advice": f"(AI 解读失败: {type(e).__name__}: {e})"}


# ============== 8. AI 解读:数据资产分析 ==============

@router.post("/data-asset/{type}/ai-analyze")
def data_asset_ai(type: str, admin: dict = Depends(get_current_admin)):
    """对某张业务表(7 个 type 之一)做 AI 总结"""
    if type not in DATA_TABLES:
        return {"error": f"unknown type: {type}"}
    # 拉样本 + 统计
    base = data_asset(type=type, page=1, page_size=20, user_id=None, admin=admin)
    rows = base.get("rows", [])

    # 聚合
    if rows:
        if type == "transactions":
            agg = {}
            for r in rows:
                t = r.get("type") or "?"
                agg.setdefault(t, {"count": 0, "amount": 0})
                agg[t]["count"] += 1
                agg[t]["amount"] += _safe_num(r.get("amount"))
            agg_text = str(agg)
        else:
            user_counts = {}
            for r in rows:
                uid = r.get("user_id")
                if uid:
                    user_counts[uid] = user_counts.get(uid, 0) + 1
            top_users = sorted(user_counts.items(), key=lambda x: -x[1])[:3]
            agg_text = f"样本 {len(rows)} 条,涉及 {len(user_counts)} 个用户,Top3 用户: {top_users}"
    else:
        agg_text = "暂无样本"

    prompt = f"""你是「习惯管家」数据分析助手。基于以下「{type}」业务表的真实数据,给 3 条**简洁、具体**的中文建议(每条 ≤ 40 字):

总数据: {base.get('total', 0)} 条
样本: {agg_text}

每条单独一行,前面用数字编号。"""
    try:
        text = admin_chat(
            system_prompt="你是数据分析助手。回答必须用中文、简洁、具体。",
            user_message=prompt,
            session_id=f"{ADMIN_SESSION}_dataasset_{type}",
        )
        return {"type": type, "total": base.get("total", 0), "sample_size": len(rows), "ai_advice": text}
    except Exception as e:
        return {"type": type, "total": base.get("total", 0), "sample_size": len(rows), "ai_advice": f"(AI 失败: {type(e).__name__})"}
