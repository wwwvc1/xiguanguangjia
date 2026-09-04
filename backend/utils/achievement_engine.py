"""
成就引擎(读 DB 定义)
- achievement_definitions 表存管理员配置的定义
- metric_type 通用分发器评估当前数据
- check_and_unlock(user_id):对每条定义评估,新解锁写入 achievements 表
"""
from datetime import datetime
from typing import List, Dict, Optional
from database import get_connection


# ============================================================
# metric 评估器
# 返回: (current_value, target_reached)
# ============================================================

def _eval_metric(cursor, user_id: int, metric_type: str) -> int:
    """
    评估某个 metric_type 的当前值
    metric_type 列表见 backend/sql/achievement_definitions.sql
    """
    if metric_type == "todo_count":
        cursor.execute("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "done_todo":
        cursor.execute("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s AND done = 1", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "goal_count":
        cursor.execute("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "done_goal":
        cursor.execute("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s AND done = 1", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "tx_count":
        cursor.execute("SELECT COUNT(*) AS c FROM transactions WHERE user_id = %s", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "tx_income_total":
        cursor.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM transactions WHERE user_id = %s AND type='income'",
            (user_id,)
        )
        return int(cursor.fetchone()["s"] or 0)

    if metric_type == "tx_expense_total":
        cursor.execute(
            "SELECT COALESCE(SUM(ABS(amount)),0) AS s FROM transactions WHERE user_id = %s AND type='expense'",
            (user_id,)
        )
        return int(cursor.fetchone()["s"] or 0)

    if metric_type == "meal_count":
        cursor.execute("SELECT COUNT(*) AS c FROM meals WHERE user_id = %s", (user_id,))
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "early_reminder":
        cursor.execute(
            "SELECT COUNT(*) AS c FROM reminders WHERE user_id = %s AND enabled = 1 AND TIME(time) < '07:00:00'",
            (user_id,)
        )
        return int(cursor.fetchone()["c"] or 0)

    if metric_type == "consecutive_checkin":
        # 连续打卡天数(基于 todos 完成日期)
        cursor.execute(
            "SELECT DISTINCT DATE(updated_at) AS d FROM todos "
            "WHERE user_id = %s AND done = 1 AND updated_at IS NOT NULL ORDER BY d DESC",
            (user_id,)
        )
        dates = [r["d"] for r in cursor.fetchall() if r.get("d")]
        if not dates:
            return 0
        from datetime import date, timedelta
        streak = 1
        for i in range(1, len(dates)):
            if (dates[i-1] - dates[i]).days == 1:
                streak += 1
            else:
                break
        return streak

    # 未知 metric,返回 0
    return 0


# ============================================================
# 定义读取
# ============================================================

def list_metric_types() -> set:
    """返回支持的 metric_type 集合(给外部校验用)"""
    return {
        "todo_count", "done_todo", "goal_count", "done_goal",
        "tx_count", "tx_income_total", "tx_expense_total",
        "meal_count", "early_reminder", "consecutive_checkin"
    }


def list_definitions(active_only: bool = False) -> List[Dict]:
    """列出所有成就定义"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, code, name, description, icon, metric_type, target_value, is_active, sort_order, created_at FROM achievement_definitions"
            if active_only:
                sql += " WHERE is_active = 1"
            sql += " ORDER BY sort_order ASC, id ASC"
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def get_definition_by_id(ach_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, code, name, description, icon, metric_type, target_value, is_active, sort_order FROM achievement_definitions WHERE id = %s",
                (ach_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()


# ============================================================
# 解锁流程
# ============================================================

def _already_unlocked(cursor, user_id: int, code: str) -> bool:
    cursor.execute(
        "SELECT id FROM achievements WHERE user_id = %s AND type = %s",
        (user_id, code)
    )
    return cursor.fetchone() is not None


def _unlock(cursor, conn, user_id: int, defn: Dict) -> Optional[Dict]:
    """写入解锁记录,返回刚解锁的成就信息"""
    try:
        cursor.execute(
            "INSERT INTO achievements (user_id, type, name, description) VALUES (%s, %s, %s, %s)",
            (user_id, defn["code"], defn["name"], defn.get("description") or "")
        )
        conn.commit()
        return {
            "type": defn["code"],
            "name": defn["name"],
            "description": defn.get("description") or "",
            "icon": defn.get("icon") or "🏅",
            "just_unlocked": True
        }
    except Exception:
        return None


def check_and_unlock(user_id: int) -> List[Dict]:
    """
    评估所有 is_active=1 的定义,新解锁的写入并返回
    """
    newly: List[Dict] = []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, code, name, description, icon, metric_type, target_value "
                "FROM achievement_definitions WHERE is_active = 1"
            )
            defs = cur.fetchall()
            for d in defs:
                if _already_unlocked(cur, user_id, d["code"]):
                    continue
                try:
                    current = _eval_metric(cur, user_id, d["metric_type"])
                except Exception:
                    continue
                if current >= int(d["target_value"]):
                    r = _unlock(cur, conn, user_id, d)
                    if r:
                        # 顺便带上当前值,前端可展示进度
                        r["current_value"] = current
                        r["target_value"] = int(d["target_value"])
                        r["metric_type"] = d["metric_type"]
                        newly.append(r)
    finally:
        conn.close()
    return newly


# ============================================================
# 给前端用:列出 / 已解锁
# ============================================================

def list_unlocked(user_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, type, name, description, unlocked_at FROM achievements "
                "WHERE user_id = %s ORDER BY unlocked_at DESC",
                (user_id,)
            )
            rows = cur.fetchall()
            for r in rows:
                if r.get("unlocked_at"):
                    r["unlocked_at"] = str(r["unlocked_at"])
                # 反查 icon
                cur.execute("SELECT icon FROM achievement_definitions WHERE code = %s", (r["type"],))
                row2 = cur.fetchone()
                r["icon"] = row2["icon"] if row2 else "🏅"
            return rows
    finally:
        conn.close()


def list_available(user_id: int) -> List[Dict]:
    """列出所有定义 + 解锁状态 + 当前进度"""
    unlocked = list_unlocked(user_id)
    unlocked_map = {a["type"]: a for a in unlocked}
    defs = list_definitions(active_only=False)
    result = []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for d in defs:
                item = {
                    "id": d["id"],
                    "code": d["code"],
                    "name": d["name"],
                    "description": d.get("description"),
                    "icon": d.get("icon", "🏅"),
                    "metric_type": d["metric_type"],
                    "target_value": int(d["target_value"]),
                    "is_active": bool(d.get("is_active", 1)),
                    "unlocked": d["code"] in unlocked_map
                }
                if item["unlocked"]:
                    item["unlocked_at"] = unlocked_map[d["code"]].get("unlocked_at")
                # 计算当前进度(无论锁定/解锁都给)
                if item["is_active"]:
                    try:
                        cur_val = _eval_metric(cur, user_id, d["metric_type"])
                        item["current_value"] = cur_val
                        item["progress"] = min(1.0, cur_val / max(1, int(d["target_value"])))
                    except Exception:
                        item["current_value"] = 0
                        item["progress"] = 0
                result.append(item)
    finally:
        conn.close()
    return result
