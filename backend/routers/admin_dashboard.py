"""管理后台 - Dashboard 增强端点 (Phase 1.2)

提供:
  GET /api/admin/dashboard/retention?days=30  → DAU/WAU/MAU 数组
  GET /api/admin/dashboard/llm-usage?days=7    → 每日 LLM 调用数
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from database import get_connection
from utils.admin_auth import get_current_admin


router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


# ============================ Schemas ============================
class RetentionBucket(BaseModel):
    """某一天的 DAU/WAU/MAU 三指标"""
    date: str           # YYYY-MM-DD
    dau: int            # 当日活跃用户数
    wau: int            # 当日往前 7 天窗口的活跃用户数
    mau: int            # 当日往前 30 天窗口的活跃用户数


class RetentionResponse(BaseModel):
    days: int
    buckets: list[RetentionBucket]
    totals: dict        # 区间内 DAU 平均 / WAU 平均 / MAU 平均


class LLMUsageBucket(BaseModel):
    date: str           # YYYY-MM-DD
    call_count: int     # 当日 AI 调用总数
    user_count: int     # 当日独立用户数


class LLMUsageResponse(BaseModel):
    days: int
    total_calls: int
    total_users: int
    daily: list[LLMUsageBucket]


# ============================ Retention (DAU/WAU/MAU) ============================
@router.get("/retention", response_model=RetentionResponse)
def get_retention(
    days: int = Query(30, ge=1, le=180),
    admin: dict = Depends(get_current_admin)
):
    """返回最近 N 天每天的 DAU / WAU(7d 滑窗) / MAU(30d 滑窗)

    实现:
      - 对每个日期 D,统计 last_login_at 在 [D-29d, D+1d) 的去重 user 数作为 MAU(D)
      - WAU(D) 同理但窗口 7 天
      - DAU(D) 即 last_login_at 在 [D, D+1d) 的去重用户数

    为效率,先按天聚合 user_id 集合(用 GROUP_CONCAT + DISTINCT),
    再在 Python 里算 WAU/MAU 滑窗。
    """
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 拉 (date, user_id) 去重对:每个用户每天最后活跃一次
            cursor.execute(
                """SELECT DATE(last_login_at) AS d, id AS user_id
                   FROM users
                   WHERE last_login_at >= %s
                     AND last_login_at IS NOT NULL
                   GROUP BY DATE(last_login_at), id""",
                (start.strftime("%Y-%m-%d 00:00:00"),)
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    # 按日期聚合 user_id set
    by_date: dict[str, set[int]] = {}
    for r in rows:
        d = r["d"]
        if isinstance(d, datetime):
            d = d.date()
        key = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
        by_date.setdefault(key, set()).add(r["user_id"])

    buckets: list[RetentionBucket] = []
    dau_sum = 0
    wau_sum = 0
    mau_sum = 0

    # 倒序枚举每一天
    sorted_dates = sorted(by_date.keys())
    for i in range(days):
        d = start + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")

        # DAU: 当天集合大小
        dau = len(by_date.get(d_str, set()))

        # WAU: 当天 + 前 6 天 的并集
        wau_set: set[int] = set()
        for k in range(7):
            wk = d - timedelta(days=k)
            wk_str = wk.strftime("%Y-%m-%d")
            wau_set |= by_date.get(wk_str, set())
        wau = len(wau_set)

        # MAU: 当天 + 前 29 天 的并集
        mau_set: set[int] = set()
        for k in range(30):
            mk = d - timedelta(days=k)
            mk_str = mk.strftime("%Y-%m-%d")
            mau_set |= by_date.get(mk_str, set())
        mau = len(mau_set)

        buckets.append(RetentionBucket(date=d_str, dau=dau, wau=wau, mau=mau))
        dau_sum += dau
        wau_sum += wau
        mau_sum += mau

    totals = {
        "dau_avg": round(dau_sum / days, 1) if days else 0,
        "wau_avg": round(wau_sum / days, 1) if days else 0,
        "mau_avg": round(mau_sum / days, 1) if days else 0,
        "peak_dau": max((b.dau for b in buckets), default=0),
    }

    return RetentionResponse(days=days, buckets=buckets, totals=totals)


# ============================ LLM Usage (每日 AI 调用数) ============================
@router.get("/llm-usage", response_model=LLMUsageResponse)
def get_llm_usage(
    days: int = Query(7, ge=1, le=90),
    admin: dict = Depends(get_current_admin)
):
    """最近 N 天每日 AI 调用数(取自 ai_chat_logs.created_at)

    返回:
      - days: 入参
      - total_calls: 区间总和
      - total_users: 区间内不重复用户数
      - daily: [{date, call_count, user_count}, ...] 按日期正序
    """
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 按日聚合
            cursor.execute(
                """SELECT DATE(created_at) AS d,
                          COUNT(*) AS call_count,
                          COUNT(DISTINCT user_id) AS user_count
                   FROM ai_chat_logs
                   WHERE created_at >= %s
                   GROUP BY DATE(created_at)""",
                (start.strftime("%Y-%m-%d 00:00:00"),)
            )
            daily_rows = cursor.fetchall()

            # 区间总和
            cursor.execute(
                """SELECT COUNT(*) AS total_calls,
                          COUNT(DISTINCT user_id) AS total_users
                   FROM ai_chat_logs
                   WHERE created_at >= %s""",
                (start.strftime("%Y-%m-%d 00:00:00"),)
            )
            totals_row = cursor.fetchone()
    finally:
        conn.close()

    daily_dict: dict[str, dict] = {}
    for r in daily_rows:
        d = r["d"]
        if isinstance(d, datetime):
            d = d.date()
        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
        daily_dict[d_str] = {
            "call_count": int(r["call_count"]),
            "user_count": int(r["user_count"]),
        }

    daily: list[LLMUsageBucket] = []
    for i in range(days):
        d = start + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        item = daily_dict.get(d_str, {"call_count": 0, "user_count": 0})
        daily.append(LLMUsageBucket(date=d_str, **item))

    return LLMUsageResponse(
        days=days,
        total_calls=int(totals_row["total_calls"]) if totals_row else 0,
        total_users=int(totals_row["total_users"]) if totals_row else 0,
        daily=daily
    )
