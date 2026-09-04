"""
AI Agent 工具执行器
- 接收 (user_id, tool_name, args) → 直接访问 DB 执行 CRUD
- 返回统一格式: {"ok": True, "data": ...} 或 {"ok": False, "error": "..."}
"""
import json
import re
from datetime import datetime, date
from database import get_connection


# ---------- 工具函数 ----------

def _to_iso_date(s):
    """接受 'YYYY-MM-DD' 或 datetime/date, 返回 'YYYY-MM-DD' 字符串"""
    if s is None:
        return None
    if isinstance(s, (date, datetime)):
        return s.strftime("%Y-%m-%d")
    return str(s)[:10]


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _now_dt():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- Tool 注册表(函数指针) ----------
# 每个函数签名: (user_id: int, **kwargs) -> dict

def _list_todos(user_id, done=None, limit=20):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE user_id = %s"
            params = [user_id]
            if done is not None:
                sql += " AND done = %s"
                params.append(done)
            sql += " ORDER BY created_at DESC LIMIT %s"
            params.append(min(int(limit or 20), 100))
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            for r in rows:
                if r.get("due_date"):
                    r["due_date"] = str(r["due_date"])
            return {"ok": True, "data": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_todo(user_id, text, due_date=None):
    if not text or not str(text).strip():
        return {"ok": False, "error": "text 不能为空"}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                (user_id, text.strip(), due_date)
            )
            todo_id = cursor.lastrowid
            conn.commit()
            cursor.execute(
                "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE id = %s",
                (todo_id,)
            )
            row = cursor.fetchone()
            if row.get("due_date"):
                row["due_date"] = str(row["due_date"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_todos_batch(user_id, text, start_date, end_date):
    if not text or not text.strip() or not start_date or not end_date:
        return {"ok": False, "error": "text / start_date / end_date 都必填"}
    try:
        start = datetime.strptime(_to_iso_date(start_date), "%Y-%m-%d").date()
        end = datetime.strptime(_to_iso_date(end_date), "%Y-%m-%d").date()
    except Exception as e:
        return {"ok": False, "error": f"日期格式错误: {e}"}
    if start > end:
        return {"ok": False, "error": "开始日期不能晚于结束日期"}

    from datetime import timedelta
    conn = get_connection()
    created = []
    try:
        cur = start
        while cur <= end:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                    (user_id, text.strip(), str(cur))
                )
                todo_id = cursor.lastrowid
            conn.commit()
            created.append({
                "id": todo_id,
                "text": text.strip(),
                "done": False,
                "due_date": str(cur)
            })
            cur += timedelta(days=1)
        return {"ok": True, "data": created, "count": len(created)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_todo(user_id, todo_id, text=None, done=None, due_date=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
            if not cursor.fetchone():
                return {"ok": False, "error": "待办不存在"}
            updates = {}
            if text is not None:
                updates["text"] = text
            if done is not None:
                updates["done"] = bool(done)
            if due_date is not None:
                updates["due_date"] = due_date
            if not updates:
                return {"ok": False, "error": "没有提供更新字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [todo_id]
            cursor.execute(f"UPDATE todos SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cursor.execute(
                "SELECT id, text, done, due_date, created_at, updated_at FROM todos WHERE id = %s",
                (todo_id,)
            )
            row = cursor.fetchone()
            if row.get("due_date"):
                row["due_date"] = str(row["due_date"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _delete_todo(user_id, todo_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
            if cursor.rowcount == 0:
                return {"ok": False, "error": "待办不存在"}
            conn.commit()
            return {"ok": True, "data": {"deleted_id": todo_id}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ----- goals -----
def _list_goals(user_id, done=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if done is not None:
                cursor.execute(
                    "SELECT id, name, progress, done, created_at, update_time FROM goals WHERE user_id = %s AND done = %s ORDER BY created_at DESC",
                    (user_id, done)
                )
            else:
                cursor.execute(
                    "SELECT id, name, progress, done, created_at, update_time FROM goals WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,)
                )
            return {"ok": True, "data": cursor.fetchall()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_goal(user_id, name, progress=0):
    if not name or not name.strip():
        return {"ok": False, "error": "name 不能为空"}
    progress = max(0, min(100, int(progress or 0)))
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO goals (user_id, name, progress, done) VALUES (%s, %s, %s, %s)",
                (user_id, name.strip(), progress, progress >= 100)
            )
            goal_id = cursor.lastrowid
            conn.commit()
            cursor.execute(
                "SELECT id, name, progress, done, created_at, update_time FROM goals WHERE id = %s",
                (goal_id,)
            )
            return {"ok": True, "data": cursor.fetchone()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_goal(user_id, goal_id, name=None, progress=None, done=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            if not cursor.fetchone():
                return {"ok": False, "error": "目标不存在"}
            updates = {}
            if name is not None:
                updates["name"] = name
            if progress is not None:
                p = max(0, min(100, int(progress)))
                updates["progress"] = p
                if p >= 100:
                    updates["done"] = True
            if done is not None:
                updates["done"] = bool(done)
            if not updates:
                return {"ok": False, "error": "没有提供更新字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [goal_id]
            cursor.execute(f"UPDATE goals SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cursor.execute(
                "SELECT id, name, progress, done, created_at, update_time FROM goals WHERE id = %s",
                (goal_id,)
            )
            return {"ok": True, "data": cursor.fetchone()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _delete_goal(user_id, goal_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            if cursor.rowcount == 0:
                return {"ok": False, "error": "目标不存在"}
            conn.commit()
            return {"ok": True, "data": {"deleted_id": goal_id}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ----- transactions -----
def _list_transactions(user_id, type=None, year=None, month=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id, category, description, amount, type, time, created_at FROM transactions WHERE user_id = %s"
            params = [user_id]
            if type is not None:
                sql += " AND type = %s"
                params.append(type)
            if year is not None and month is not None:
                sql += " AND YEAR(time) = %s AND MONTH(time) = %s"
                params.extend([int(year), int(month)])
            sql += " ORDER BY time DESC LIMIT 100"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            for r in rows:
                r["amount"] = float(r["amount"])
                if r.get("time"):
                    r["time"] = str(r["time"])
            return {"ok": True, "data": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_transaction(user_id, amount, type, category, description=None, time=None):
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "amount 必须是数字"}
    if type not in ("income", "expense"):
        return {"ok": False, "error": "type 必须是 income 或 expense"}
    if not category:
        return {"ok": False, "error": "category 必填"}
    # 后端约定:支出存负数,收入存正数
    signed = -abs(amount) if type == "expense" else abs(amount)
    time = time or _now_dt()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO transactions (user_id, category, description, amount, type, time) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, category, description or "", signed, type, time)
            )
            tx_id = cursor.lastrowid
            conn.commit()
            cursor.execute(
                "SELECT id, category, description, amount, type, time, created_at FROM transactions WHERE id = %s",
                (tx_id,)
            )
            row = cursor.fetchone()
            row["amount"] = float(row["amount"])
            if row.get("time"):
                row["time"] = str(row["time"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_transaction(user_id, tx_id, amount=None, type=None, category=None, description=None, time=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
            if not cursor.fetchone():
                return {"ok": False, "error": "交易不存在"}
            updates = {}
            if amount is not None:
                a = float(amount)
                updates["amount"] = a
            if type is not None:
                if type not in ("income", "expense"):
                    return {"ok": False, "error": "type 必须是 income 或 expense"}
                updates["type"] = type
            # 如果 amount 和 type 都给了,需要重新应用正负号规则
            if "amount" in updates and "type" in updates:
                updates["amount"] = -abs(updates["amount"]) if updates["type"] == "expense" else abs(updates["amount"])
            elif "amount" in updates:
                # 只改 amount,根据数据库当前 type 调整符号
                cursor.execute("SELECT type FROM transactions WHERE id = %s", (tx_id,))
                cur_type = cursor.fetchone()["type"]
                updates["amount"] = -abs(updates["amount"]) if cur_type == "expense" else abs(updates["amount"])
            if category is not None:
                updates["category"] = category
            if description is not None:
                updates["description"] = description
            if time is not None:
                updates["time"] = time
            if not updates:
                return {"ok": False, "error": "没有提供更新字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [tx_id]
            cursor.execute(f"UPDATE transactions SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cursor.execute(
                "SELECT id, category, description, amount, type, time, created_at FROM transactions WHERE id = %s",
                (tx_id,)
            )
            row = cursor.fetchone()
            row["amount"] = float(row["amount"])
            if row.get("time"):
                row["time"] = str(row["time"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _delete_transaction(user_id, tx_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
            if cursor.rowcount == 0:
                return {"ok": False, "error": "交易不存在"}
            conn.commit()
            return {"ok": True, "data": {"deleted_id": tx_id}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _get_monthly_summary(user_id, month):
    try:
        year, mon = str(month).split("-")
        date_start = f"{year}-{mon}-01 00:00:00"
        if int(mon) == 12:
            date_end = f"{int(year)+1}-01-01 00:00:00"
        else:
            date_end = f"{year}-{int(mon)+1:02d}-01 00:00:00"
    except Exception as e:
        return {"ok": False, "error": f"month 格式错误(应为 YYYY-MM): {e}"}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE user_id = %s AND type = 'income' AND time >= %s AND time < %s",
                (user_id, date_start, date_end)
            )
            income = float(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT COALESCE(SUM(ABS(amount)),0) AS total FROM transactions WHERE user_id = %s AND type = 'expense' AND time >= %s AND time < %s",
                (user_id, date_start, date_end)
            )
            expense = float(cursor.fetchone()["total"])
            return {
                "ok": True,
                "data": {
                    "month": month,
                    "income": income,
                    "expense": expense,
                    "net": income - expense
                }
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _get_daily_stats(user_id, date):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            d = _to_iso_date(date)
            cursor.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE user_id = %s AND type = 'income' AND DATE(time) = %s",
                (user_id, d)
            )
            income = float(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT COALESCE(SUM(ABS(amount)),0) AS total FROM transactions WHERE user_id = %s AND type = 'expense' AND DATE(time) = %s",
                (user_id, d)
            )
            expense = float(cursor.fetchone()["total"])
            return {
                "ok": True,
                "data": {"date": d, "income": income, "expense": expense, "net": income - expense}
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ----- meals -----
def _list_meals(user_id, date=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if date is not None:
                cursor.execute(
                    "SELECT id, meal_type, date, total_calories, created_at FROM meals WHERE user_id = %s AND date = %s ORDER BY created_at DESC",
                    (user_id, _to_iso_date(date))
                )
            else:
                cursor.execute(
                    "SELECT id, meal_type, date, total_calories, created_at FROM meals WHERE user_id = %s ORDER BY date DESC, id DESC LIMIT 50",
                    (user_id,)
                )
            meals = cursor.fetchall()
            for m in meals:
                if m.get("date"):
                    m["date"] = str(m["date"])
                cursor.execute(
                    "SELECT id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                    (m["id"],)
                )
                items = cursor.fetchall()
                for it in items:
                    it["calories"] = float(it["calories"])
                m["items"] = items
            return {"ok": True, "data": meals}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_meal(user_id, meal_type, items, date=None):
    if meal_type not in ("breakfast", "lunch", "dinner"):
        return {"ok": False, "error": "meal_type 必须是 breakfast / lunch / dinner"}
    if not items or not isinstance(items, list) or len(items) == 0:
        return {"ok": False, "error": "items 至少要有一项"}
    d = _to_iso_date(date) or _today()
    total = 0.0
    for it in items:
        try:
            total += float(it.get("calories") or 0)
        except Exception:
            return {"ok": False, "error": "items 里的 calories 必须是数字"}

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO meals (user_id, meal_type, date, total_calories) VALUES (%s, %s, %s, %s)",
                (user_id, meal_type, d, total)
            )
            meal_id = cursor.lastrowid
            for it in items:
                cursor.execute(
                    "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
                    (meal_id, it.get("name", ""), it.get("portion", ""), float(it.get("calories") or 0))
                )
            conn.commit()
            cursor.execute(
                "SELECT id, meal_type, date, total_calories, created_at FROM meals WHERE id = %s",
                (meal_id,)
            )
            meal = cursor.fetchone()
            meal["date"] = str(meal["date"])
            cursor.execute(
                "SELECT id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                (meal_id,)
            )
            meal["items"] = cursor.fetchall()
            for it in meal["items"]:
                it["calories"] = float(it["calories"])
            return {"ok": True, "data": meal}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_meal(user_id, meal_id, meal_type, items, date=None):
    if meal_type not in ("breakfast", "lunch", "dinner"):
        return {"ok": False, "error": "meal_type 必须是 breakfast / lunch / dinner"}
    if not items or not isinstance(items, list):
        return {"ok": False, "error": "items 必填"}
    d = _to_iso_date(date) or _today()
    total = 0.0
    for it in items:
        try:
            total += float(it.get("calories") or 0)
        except Exception:
            return {"ok": False, "error": "items 里的 calories 必须是数字"}

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM meals WHERE id = %s AND user_id = %s", (meal_id, user_id))
            if not cursor.fetchone():
                return {"ok": False, "error": "餐次不存在"}
            cursor.execute(
                "UPDATE meals SET meal_type = %s, date = %s, total_calories = %s WHERE id = %s",
                (meal_type, d, total, meal_id)
            )
            cursor.execute("DELETE FROM meal_items WHERE meal_id = %s", (meal_id,))
            for it in items:
                cursor.execute(
                    "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s, %s, %s, %s)",
                    (meal_id, it.get("name", ""), it.get("portion", ""), float(it.get("calories") or 0))
                )
            conn.commit()
            cursor.execute(
                "SELECT id, meal_type, date, total_calories, created_at FROM meals WHERE id = %s",
                (meal_id,)
            )
            meal = cursor.fetchone()
            meal["date"] = str(meal["date"])
            cursor.execute(
                "SELECT id, name, portion, calories FROM meal_items WHERE meal_id = %s",
                (meal_id,)
            )
            meal["items"] = cursor.fetchall()
            for it in meal["items"]:
                it["calories"] = float(it["calories"])
            return {"ok": True, "data": meal}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _delete_meal(user_id, meal_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM meals WHERE id = %s AND user_id = %s", (meal_id, user_id))
            if cursor.rowcount == 0:
                return {"ok": False, "error": "餐次不存在"}
            conn.commit()
            return {"ok": True, "data": {"deleted_id": meal_id}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ----- reminders -----
def _list_reminders(user_id, enabled=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if enabled is not None:
                cursor.execute(
                    "SELECT id, type, time, enabled, created_at FROM reminders WHERE user_id = %s AND enabled = %s ORDER BY created_at DESC",
                    (user_id, enabled)
                )
            else:
                cursor.execute(
                    "SELECT id, type, time, enabled, created_at FROM reminders WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,)
                )
            rows = cursor.fetchall()
            for r in rows:
                if r.get("time"):
                    r["time"] = str(r["time"])
            return {"ok": True, "data": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _add_reminder(user_id, type, time, enabled=True):
    if type not in ("finance", "diet", "todo", "goal", "other"):
        return {"ok": False, "error": "type 必须是 finance / diet / todo / goal / other"}
    if not time:
        return {"ok": False, "error": "time 必填(HH:MM:SS)"}
    if len(str(time)) == 5:
        time = f"{time}:00"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reminders (user_id, type, time, enabled) VALUES (%s, %s, %s, %s)",
                (user_id, type, time, bool(enabled))
            )
            rid = cursor.lastrowid
            conn.commit()
            cursor.execute(
                "SELECT id, type, time, enabled, created_at FROM reminders WHERE id = %s",
                (rid,)
            )
            row = cursor.fetchone()
            row["time"] = str(row["time"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_reminder(user_id, reminder_id, type=None, time=None, enabled=None):
    if type is not None and type not in ("finance", "diet", "todo", "goal", "other"):
        return {"ok": False, "error": "type 必须是 finance / diet / todo / goal / other"}
    if time is not None and len(str(time)) == 5:
        time = f"{time}:00"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM reminders WHERE id = %s AND user_id = %s", (reminder_id, user_id))
            if not cursor.fetchone():
                return {"ok": False, "error": "提醒不存在"}
            updates = {}
            if type is not None:
                updates["type"] = type
            if time is not None:
                updates["time"] = time
            if enabled is not None:
                updates["enabled"] = bool(enabled)
            if not updates:
                return {"ok": False, "error": "没有提供更新字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [reminder_id]
            cursor.execute(f"UPDATE reminders SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cursor.execute(
                "SELECT id, type, time, enabled, created_at FROM reminders WHERE id = %s",
                (reminder_id,)
            )
            row = cursor.fetchone()
            row["time"] = str(row["time"])
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _delete_reminder(user_id, reminder_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM reminders WHERE id = %s AND user_id = %s", (reminder_id, user_id))
            if cursor.rowcount == 0:
                return {"ok": False, "error": "提醒不存在"}
            conn.commit()
            return {"ok": True, "data": {"deleted_id": reminder_id}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ----- user settings -----
def _get_user_settings(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO user_settings (user_id, target_calories) VALUES (%s, %s)",
                    (user_id, 1800)
                )
                conn.commit()
            cursor.execute(
                "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row.get("home_layout") and isinstance(row["home_layout"], str):
                try:
                    row["home_layout"] = json.loads(row["home_layout"])
                except Exception:
                    row["home_layout"] = None
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _update_user_settings(user_id, target_calories=None):
    if target_calories is not None:
        if not (500 <= int(target_calories) <= 10000):
            return {"ok": False, "error": "target_calories 必须在 500-10000 之间"}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO user_settings (user_id, target_calories) VALUES (%s, %s)",
                    (user_id, 1800)
                )
                conn.commit()
            if target_calories is not None:
                cursor.execute(
                    "UPDATE user_settings SET target_calories = %s WHERE user_id = %s",
                    (int(target_calories), user_id)
                )
                conn.commit()
            cursor.execute(
                "SELECT user_id, target_calories, home_layout, updated_at FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row.get("home_layout") and isinstance(row["home_layout"], str):
                try:
                    row["home_layout"] = json.loads(row["home_layout"])
                except Exception:
                    row["home_layout"] = None
            return {"ok": True, "data": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# 工具注册表
TOOL_REGISTRY = {
    "list_todos": _list_todos,
    "add_todo": _add_todo,
    "add_todos_batch": _add_todos_batch,
    "update_todo": _update_todo,
    "delete_todo": _delete_todo,
    "list_goals": _list_goals,
    "add_goal": _add_goal,
    "update_goal": _update_goal,
    "delete_goal": _delete_goal,
    "list_transactions": _list_transactions,
    "add_transaction": _add_transaction,
    "update_transaction": _update_transaction,
    "delete_transaction": _delete_transaction,
    "get_monthly_summary": _get_monthly_summary,
    "get_daily_stats": _get_daily_stats,
    "list_meals": _list_meals,
    "add_meal": _add_meal,
    "update_meal": _update_meal,
    "delete_meal": _delete_meal,
    "list_reminders": _list_reminders,
    "add_reminder": _add_reminder,
    "update_reminder": _update_reminder,
    "delete_reminder": _delete_reminder,
    "get_user_settings": _get_user_settings,
    "update_user_settings": _update_user_settings,
}


class ToolExecutor:
    """对外接口:执行 tool_call,返回 dict"""

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> dict:
        func = TOOL_REGISTRY.get(tool_name)
        if not func:
            return {"ok": False, "error": f"未知工具: {tool_name}"}
        try:
            return func(user_id=user_id, **(arguments or {}))
        except TypeError as e:
            return {"ok": False, "error": f"参数错误: {e}"}
        except Exception as e:
            return {"ok": False, "error": f"执行失败: {e}"}
