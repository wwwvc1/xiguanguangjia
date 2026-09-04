"""
AI Agent 工具集
为 OpenAI Function Calling 提供 17 个工具(增删改查 + 聚合)
所有工具强制按 user_id 隔离,不允许跨用户访问
"""
from datetime import datetime, date, timedelta
from database import get_connection

# ============================================================
# 工具 Schema(OpenAI Function Calling 格式)
# ============================================================

TOOLS = [
    # ---------- 添加 ----------
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "添加一个待办事项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待办内容,如'买菜'、'晨跑3公里'"},
                    "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD,可省略"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_goal",
            "description": "添加一个长期目标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "目标名,如'今年读完50本书'"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_transaction",
            "description": "添加一笔收支记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "金额(正数)"},
                    "type": {"type": "string", "enum": ["income", "expense"], "description": "收入或支出"},
                    "category": {"type": "string", "description": "分类,如'餐饮'、'交通'、'工资'"},
                    "description": {"type": "string", "description": "备注/描述"},
                    "time": {"type": "string", "description": "时间 YYYY-MM-DD HH:MM:SS,可省略(默认现在)"}
                },
                "required": ["amount", "type", "category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_meal",
            "description": "记录一餐,包含多个食物项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner"], "description": "餐次类型"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD,默认今天"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "portion": {"type": "string", "description": "份量,如'1碗'、'200g',可省"},
                                "calories": {"type": "number", "description": "卡路里"}
                            },
                            "required": ["name", "calories"]
                        }
                    }
                },
                "required": ["meal_type", "items"]
            }
        }
    },
    # ---------- 查询 ----------
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "查询待办列表。可按完成状态、日期、关键词筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "done": {"type": "boolean", "description": "true=已完成,false=未完成"},
                    "date": {"type": "string", "description": "YYYY-MM-DD 查指定日期"},
                    "keyword": {"type": "string", "description": "在 text 里模糊搜索"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_goals",
            "description": "查询目标列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "done": {"type": "boolean", "description": "true=已完成,false=未完成"},
                    "keyword": {"type": "string", "description": "在 name 里模糊搜索"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "查询收支记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["income", "expense"]},
                    "date_from": {"type": "string", "description": "YYYY-MM-DD 起始日期"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD 结束日期"},
                    "keyword": {"type": "string", "description": "在 description 里模糊搜索"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_meals",
            "description": "查询饮食记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"}
                }
            }
        }
    },
    # ---------- 修改(破坏性,需二次确认) ----------
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "修改一个待办(text/done/due_date)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "待办 ID"},
                    "text": {"type": "string"},
                    "done": {"type": "boolean"},
                    "due_date": {"type": "string"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal",
            "description": "修改一个目标。progress 达 100 自动标记完成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "progress": {"type": "integer", "description": "0-100"},
                    "done": {"type": "boolean"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction",
            "description": "修改一笔交易。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "amount": {"type": "number"},
                    "type": {"type": "string", "enum": ["income", "expense"]},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "time": {"type": "string"}
                },
                "required": ["id"]
            }
        }
    },
    # ---------- 删除(破坏性,需二次确认) ----------
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "删除一个待办。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "待办 ID,如已知"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_goal",
            "description": "删除一个目标。",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "删除一笔交易。",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "删除一餐(连带食物项)。",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"]
            }
        }
    },
    # ---------- 聚合查询 ----------
    {
        "type": "function",
        "function": {
            "name": "aggregate_transactions",
            "description": "统计指定时间范围内的收支总额,可按分类聚合。",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "this_month", "last_month", "custom"],
                        "description": "统计周期"
                    },
                    "date_from": {"type": "string", "description": "period=custom 时必填 YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "period=custom 时必填 YYYY-MM-DD"},
                    "group_by_category": {"type": "boolean", "description": "是否按分类拆分,默认 false"}
                },
                "required": ["period"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_todos",
            "description": "统计待办:总数 / 已完成 / 未完成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD,默认今天"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_goals",
            "description": "统计目标进度:总数 / 已完成 / 进行中 / 平均完成率。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# 破坏性工具集合(需要用户二次确认)
DESTRUCTIVE_TOOLS = {
    "update_todo", "update_goal", "update_transaction",
    "delete_todo", "delete_goal", "delete_transaction", "delete_meal"
}


# ============================================================
# 工具执行函数
# ============================================================

def _format_date(d):
    """统一日期格式"""
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d") if not isinstance(d, datetime) else d.strftime("%Y-%m-%d %H:%M:%S")
    return d


def _today_str():
    return date.today().strftime("%Y-%m-%d")


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----- 添加 -----

def _add_todo(args, user_id):
    text = args.get("text")
    if not text:
        return {"error": "text 不能为空"}
    due = args.get("due_date") or None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO todos (user_id, text, due_date) VALUES (%s, %s, %s)",
                (user_id, text, due)
            )
            todo_id = cur.lastrowid
            conn.commit()
            cur.execute(
                "SELECT id, text, done, due_date, created_at FROM todos WHERE id = %s",
                (todo_id,)
            )
            row = cur.fetchone()
        return {"created": {"id": row["id"], "text": row["text"], "due_date": _format_date(row.get("due_date"))}}
    finally:
        conn.close()


def _add_goal(args, user_id):
    name = args.get("name")
    if not name:
        return {"error": "name 不能为空"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO goals (user_id, name, progress) VALUES (%s, %s, 0)",
                (user_id, name)
            )
            goal_id = cur.lastrowid
            conn.commit()
            cur.execute(
                "SELECT id, name, progress, done FROM goals WHERE id = %s",
                (goal_id,)
            )
            row = cur.fetchone()
        return {"created": {"id": row["id"], "name": row["name"]}}
    finally:
        conn.close()


def _add_transaction(args, user_id):
    amount = args.get("amount")
    tx_type = args.get("type")
    category = args.get("category")
    if amount is None or tx_type not in ("income", "expense") or not category:
        return {"error": "amount/type/category 必填且 type 必须是 income/expense"}
    description = args.get("description") or ""
    time = args.get("time") or _now_str()
    # 存储:支出存负数,收入存正数
    signed = -abs(float(amount)) if tx_type == "expense" else abs(float(amount))
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions (user_id, category, description, amount, type, time) VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, category, description, signed, tx_type, time)
            )
            tx_id = cur.lastrowid
            conn.commit()
        return {"created": {"id": tx_id, "amount": abs(signed), "type": tx_type, "category": category}}
    finally:
        conn.close()


def _add_meal(args, user_id):
    meal_type = args.get("meal_type")
    items = args.get("items") or []
    if meal_type not in ("breakfast", "lunch", "dinner"):
        return {"error": "meal_type 必须是 breakfast/lunch/dinner"}
    if not items:
        return {"error": "items 至少 1 项"}
    meal_date = args.get("date") or _today_str()
    total = sum(int(i.get("calories") or 0) for i in items)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO meals (user_id, meal_type, date, total_calories) VALUES (%s,%s,%s,%s)",
                (user_id, meal_type, meal_date, total)
            )
            meal_id = cur.lastrowid
            for it in items:
                cur.execute(
                    "INSERT INTO meal_items (meal_id, name, portion, calories) VALUES (%s,%s,%s,%s)",
                    (meal_id, it.get("name"), it.get("portion"), it.get("calories"))
                )
            conn.commit()
        return {"created": {"id": meal_id, "meal_type": meal_type, "date": meal_date, "items": len(items), "total_calories": total}}
    finally:
        conn.close()


# ----- 查询 -----

def _list_todos(args, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, text, done, due_date, created_at FROM todos WHERE user_id = %s"
            params = [user_id]
            if "done" in args and args["done"] is not None:
                sql += " AND done = %s"
                params.append(1 if args["done"] else 0)
            if args.get("date"):
                sql += " AND (due_date = %s OR due_date IS NULL)"
                params.append(args["date"])
            if args.get("keyword"):
                sql += " AND text LIKE %s"
                params.append(f"%{args['keyword']}%")
            sql += " ORDER BY created_at DESC LIMIT 100"
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                r["due_date"] = _format_date(r.get("due_date"))
                r["done"] = bool(r["done"])
            return {"items": rows, "count": len(rows)}
    finally:
        conn.close()


def _list_goals(args, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, name, progress, done, created_at FROM goals WHERE user_id = %s"
            params = [user_id]
            if "done" in args and args["done"] is not None:
                sql += " AND done = %s"
                params.append(1 if args["done"] else 0)
            if args.get("keyword"):
                sql += " AND name LIKE %s"
                params.append(f"%{args['keyword']}%")
            sql += " ORDER BY created_at DESC LIMIT 100"
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                r["done"] = bool(r["done"])
            return {"items": rows, "count": len(rows)}
    finally:
        conn.close()


def _list_transactions(args, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, category, description, amount, type, time FROM transactions WHERE user_id = %s"
            params = [user_id]
            if args.get("type") in ("income", "expense"):
                sql += " AND type = %s"
                params.append(args["type"])
            if args.get("date_from"):
                sql += " AND time >= %s"
                params.append(args["date_from"] + " 00:00:00")
            if args.get("date_to"):
                sql += " AND time <= %s"
                params.append(args["date_to"] + " 23:59:59")
            if args.get("keyword"):
                sql += " AND description LIKE %s"
                params.append(f"%{args['keyword']}%")
            sql += " ORDER BY time DESC LIMIT 200"
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                r["amount"] = float(r["amount"])
                r["time"] = _format_date(r["time"])
            return {"items": rows, "count": len(rows)}
    finally:
        conn.close()


def _list_meals(args, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, meal_type, date, total_calories FROM meals WHERE user_id = %s"
            params = [user_id]
            if args.get("date"):
                sql += " AND date = %s"
                params.append(args["date"])
            elif args.get("date_from") and args.get("date_to"):
                sql += " AND date BETWEEN %s AND %s"
                params.extend([args["date_from"], args["date_to"]])
            sql += " ORDER BY date DESC, id DESC LIMIT 100"
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            for r in rows:
                r["total_calories"] = int(r["total_calories"])
            return {"items": rows, "count": len(rows)}
    finally:
        conn.close()


# ----- 修改 -----

def _update_todo(args, user_id):
    todo_id = args.get("id")
    if not todo_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
            if not cur.fetchone():
                return {"error": f"待办 #{todo_id} 不存在或不属于你"}
            updates = {}
            if "text" in args and args["text"] is not None:
                updates["text"] = args["text"]
            if "done" in args and args["done"] is not None:
                updates["done"] = 1 if args["done"] else 0
            if "due_date" in args and args["due_date"] is not None:
                updates["due_date"] = args["due_date"]
            if not updates:
                return {"error": "至少提供一个修改字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [todo_id]
            cur.execute(f"UPDATE todos SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cur.execute("SELECT id, text, done, due_date FROM todos WHERE id = %s", (todo_id,))
            row = cur.fetchone()
            row["done"] = bool(row["done"])
        return {"updated": {"id": row["id"], "text": row["text"], "done": row["done"]}}
    finally:
        conn.close()


def _update_goal(args, user_id):
    goal_id = args.get("id")
    if not goal_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            if not cur.fetchone():
                return {"error": f"目标 #{goal_id} 不存在或不属于你"}
            updates = {}
            if "name" in args and args["name"] is not None:
                updates["name"] = args["name"]
            if "progress" in args and args["progress"] is not None:
                updates["progress"] = int(args["progress"])
                if updates["progress"] >= 100:
                    updates["done"] = 1
            if "done" in args and args["done"] is not None:
                updates["done"] = 1 if args["done"] else 0
            if not updates:
                return {"error": "至少提供一个修改字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [goal_id]
            cur.execute(f"UPDATE goals SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cur.execute("SELECT id, name, progress, done FROM goals WHERE id = %s", (goal_id,))
            row = cur.fetchone()
            row["done"] = bool(row["done"])
        return {"updated": {"id": row["id"], "name": row["name"], "progress": row["progress"], "done": row["done"]}}
    finally:
        conn.close()


def _update_transaction(args, user_id):
    tx_id = args.get("id")
    if not tx_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, type, amount FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
            row = cur.fetchone()
            if not row:
                return {"error": f"交易 #{tx_id} 不存在或不属于你"}
            updates = {}
            if "amount" in args and args["amount"] is not None:
                # 重新应用符号
                tx_type = args.get("type") or row["type"]
                amt = abs(float(args["amount"]))
                updates["amount"] = -amt if tx_type == "expense" else amt
            if "type" in args and args["type"] is not None:
                updates["type"] = args["type"]
                # 如果只改 type,要按现有 amount 的绝对值重设符号
                if "amount" not in updates:
                    cur_amt = float(row["amount"])
                    updates["amount"] = -abs(cur_amt) if args["type"] == "expense" else abs(cur_amt)
            if "category" in args and args["category"] is not None:
                updates["category"] = args["category"]
            if "description" in args and args["description"] is not None:
                updates["description"] = args["description"]
            if "time" in args and args["time"] is not None:
                updates["time"] = args["time"]
            if not updates:
                return {"error": "至少提供一个修改字段"}
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [tx_id]
            cur.execute(f"UPDATE transactions SET {set_clause} WHERE id = %s", values)
            conn.commit()
        return {"updated": {"id": tx_id, "fields": list(updates.keys())}}
    finally:
        conn.close()


# ----- 删除 -----

def _delete_todo(args, user_id):
    todo_id = args.get("id")
    if not todo_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT text FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
            row = cur.fetchone()
            if not row:
                return {"error": f"待办 #{todo_id} 不存在或不属于你"}
            text = row["text"]
            cur.execute("DELETE FROM todos WHERE id = %s AND user_id = %s", (todo_id, user_id))
            conn.commit()
        return {"deleted": {"id": todo_id, "text": text}}
    finally:
        conn.close()


def _delete_goal(args, user_id):
    goal_id = args.get("id")
    if not goal_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            row = cur.fetchone()
            if not row:
                return {"error": f"目标 #{goal_id} 不存在或不属于你"}
            name = row["name"]
            cur.execute("DELETE FROM goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            conn.commit()
        return {"deleted": {"id": goal_id, "name": name}}
    finally:
        conn.close()


def _delete_transaction(args, user_id):
    tx_id = args.get("id")
    if not tx_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT category, amount FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
            row = cur.fetchone()
            if not row:
                return {"error": f"交易 #{tx_id} 不存在或不属于你"}
            cur.execute("DELETE FROM transactions WHERE id = %s AND user_id = %s", (tx_id, user_id))
            conn.commit()
        return {"deleted": {"id": tx_id, "category": row["category"], "amount": float(row["amount"])}}
    finally:
        conn.close()


def _delete_meal(args, user_id):
    meal_id = args.get("id")
    if not meal_id:
        return {"error": "id 必填"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT meal_type, date FROM meals WHERE id = %s AND user_id = %s", (meal_id, user_id))
            row = cur.fetchone()
            if not row:
                return {"error": f"餐次 #{meal_id} 不存在或不属于你"}
            cur.execute("DELETE FROM meals WHERE id = %s AND user_id = %s", (meal_id, user_id))
            conn.commit()
        return {"deleted": {"id": meal_id, "meal_type": row["meal_type"], "date": _format_date(row["date"])}}
    finally:
        conn.close()


# ----- 聚合 -----

def _period_range(period, custom_from=None, custom_to=None):
    """返回 (date_from, date_to) 字符串元组"""
    today = date.today()
    if period == "today":
        return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if period == "this_month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - timedelta(days=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if period == "last_month":
        first_this = today.replace(day=1)
        last_of_prev = first_this - timedelta(days=1)
        start = last_of_prev.replace(day=1)
        return start.strftime("%Y-%m-%d"), last_of_prev.strftime("%Y-%m-%d")
    if period == "custom":
        return custom_from, custom_to
    return None, None


def _aggregate_transactions(args, user_id):
    period = args.get("period", "this_month")
    df, dt = _period_range(period, args.get("date_from"), args.get("date_to"))
    if not df or not dt:
        return {"error": "周期或日期范围无效"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = "WHERE user_id = %s AND time >= %s AND time <= %s"
            params = (user_id, df + " 00:00:00", dt + " 23:59:59")
            cur.execute(f"SELECT COALESCE(SUM(amount),0) AS t FROM transactions {where} AND type='income'", params)
            income = float(cur.fetchone()["t"] or 0)
            cur.execute(f"SELECT COALESCE(SUM(ABS(amount)),0) AS t FROM transactions {where} AND type='expense'", params)
            expense = float(cur.fetchone()["t"] or 0)
            result = {
                "period": period,
                "date_from": df,
                "date_to": dt,
                "income": income,
                "expense": expense,
                "net": income - expense
            }
            if args.get("group_by_category"):
                cur.execute(
                    f"SELECT category, type, COALESCE(SUM(ABS(amount)),0) AS total "
                    f"FROM transactions {where} GROUP BY category, type ORDER BY total DESC",
                    params
                )
                result["by_category"] = [
                    {"category": r["category"], "type": r["type"], "total": float(r["total"])}
                    for r in cur.fetchall()
                ]
            return result
    finally:
        conn.close()


def _aggregate_todos(args, user_id):
    target_date = args.get("date") or _today_str()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM todos WHERE user_id = %s AND (due_date = %s OR due_date IS NULL)",
                (user_id, target_date)
            )
            total = int(cur.fetchone()["c"] or 0)
            cur.execute(
                "SELECT COUNT(*) AS c FROM todos WHERE user_id = %s AND done = 1 AND (due_date = %s OR due_date IS NULL)",
                (user_id, target_date)
            )
            done = int(cur.fetchone()["c"] or 0)
            return {"date": target_date, "total": total, "done": done, "pending": total - done}
    finally:
        conn.close()


def _aggregate_goals(args, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s", (user_id,))
            total = int(cur.fetchone()["c"] or 0)
            cur.execute("SELECT COUNT(*) AS c FROM goals WHERE user_id = %s AND done = 1", (user_id,))
            done = int(cur.fetchone()["c"] or 0)
            cur.execute("SELECT COALESCE(AVG(progress),0) AS p FROM goals WHERE user_id = %s", (user_id,))
            avg_progress = float(cur.fetchone()["p"] or 0)
            return {
                "total": total,
                "done": done,
                "in_progress": total - done,
                "avg_progress": round(avg_progress, 1)
            }
    finally:
        conn.close()


# ============================================================
# 统一入口
# ============================================================

EXECUTORS = {
    "add_todo": _add_todo,
    "add_goal": _add_goal,
    "add_transaction": _add_transaction,
    "add_meal": _add_meal,
    "list_todos": _list_todos,
    "list_goals": _list_goals,
    "list_transactions": _list_transactions,
    "list_meals": _list_meals,
    "update_todo": _update_todo,
    "update_goal": _update_goal,
    "update_transaction": _update_transaction,
    "delete_todo": _delete_todo,
    "delete_goal": _delete_goal,
    "delete_transaction": _delete_transaction,
    "delete_meal": _delete_meal,
    "aggregate_transactions": _aggregate_transactions,
    "aggregate_todos": _aggregate_todos,
    "aggregate_goals": _aggregate_goals,
}


def execute_tool(name: str, args: dict, user_id: int) -> dict:
    """
    执行单个工具。所有执行都强制 user_id 隔离(在 SQL WHERE 里已硬编码)。
    """
    fn = EXECUTORS.get(name)
    if not fn:
        return {"error": f"未知工具: {name}"}
    try:
        return fn(args or {}, user_id)
    except Exception as e:
        return {"error": f"执行 {name} 失败: {str(e)}"}


def summarize_action_for_user(tool: str, args: dict, user_id: int) -> str:
    """
    给人看的动作预览(用于确认弹窗)。
    对 list 类无意义,对 mutate 类返回"将删除/修改 XXX"。
    """
    if tool == "delete_todo":
        return f"删除待办 #{args.get('id')}"
    if tool == "delete_goal":
        return f"删除目标 #{args.get('id')}"
    if tool == "delete_transaction":
        return f"删除交易 #{args.get('id')}"
    if tool == "delete_meal":
        return f"删除餐次 #{args.get('id')}"
    if tool == "update_todo":
        fields = [k for k in ("text", "done", "due_date") if k in args and args[k] is not None]
        fmap = {"text": "内容", "done": "完成状态", "due_date": "截止日期"}
        fields_cn = "、".join(fmap.get(f, f) for f in fields)
        return f"修改待办 #{args.get('id')} 的 {fields_cn}"
    if tool == "update_goal":
        fields = [k for k in ("name", "progress", "done") if k in args and args[k] is not None]
        fmap = {"name": "名称", "progress": "进度", "done": "完成状态"}
        fields_cn = "、".join(fmap.get(f, f) for f in fields)
        return f"修改目标 #{args.get('id')} 的 {fields_cn}"
    if tool == "update_transaction":
        return f"修改交易 #{args.get('id')}"
    return f"{tool}({args})"
