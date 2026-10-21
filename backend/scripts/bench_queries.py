"""Phase 1 改造前后查询基准(严谨版)

上一版对比的是"OR vs UNION ALL",但两者都已经在复合索引上跑,
所以看不出索引本身的收益。这一版用 `IGNORE INDEX` **强制不走新索引**,
把「索引」和「查询改写」两个变量分开测:

  组 A: 原查询 + 无新索引      ← 改造前的真实状态
  组 B: 原查询 + 新索引
  组 C: 改写后的查询 + 新索引

⚠️ 会写入约 6 万行合成数据,跑完自动清理。
用法: cd backend && python scripts/bench_queries.py [--rows 30000] [--keep]
"""
import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_sync_connection

BENCH_OPENID = "__perf_bench_user__"
NEW_IDX = "idx_user_done_due, idx_user_done_created"
NEW_TX_IDX = "idx_user_time, idx_user_type_time"

TODO_COLS = "id, text, done, due_date, created_at, updated_at"


def timed(fn, repeat=7):
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return samples[len(samples) // 2]


def ensure_user(cur):
    cur.execute("SELECT id FROM users WHERE openid = %s", (BENCH_OPENID,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute("INSERT INTO users (openid, nickname) VALUES (%s, %s)", (BENCH_OPENID, "基准测试"))
    return cur.lastrowid


def seed(cur, uid, rows):
    print(f"  造数据: todos {rows} 行, transactions {rows} 行 ...")
    today = date.today()
    cur.executemany(
        "INSERT INTO todos (user_id, text, done, due_date) VALUES (%s, %s, %s, %s)",
        [(uid, f"基准待办 {i}", 1 if i % 3 == 0 else 0, str(today - timedelta(days=i % 120)))
         for i in range(rows)],
    )
    base = datetime.now()
    cur.executemany(
        "INSERT INTO transactions (user_id, category, description, amount, type, time) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [(uid, "餐饮", f"基准 {i}", 10 + (i % 90), "expense" if i % 4 else "income",
          base - timedelta(days=i % 180, minutes=i % 1440)) for i in range(rows)],
    )


def cleanup(cur, uid):
    for table in ("todos", "transactions", "checkins", "achievements",
                  "goals", "meals", "reminders", "user_settings"):
        try:
            cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (uid,))
        except Exception:
            pass
    cur.execute("DELETE FROM users WHERE id = %s", (uid,))


def row(label, ms, base=None):
    rel = f"  ({base / ms:5.2f}x)" if base and ms else ""
    print(f"    {label:<34}: {ms:8.2f} ms{rel}")


def run(rows: int, keep: bool):
    conn = get_sync_connection()
    cur = conn.cursor()
    uid = ensure_user(cur)
    conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s", (uid,))
    if cur.fetchone()["c"] < rows:
        seed(cur, uid, rows)
        conn.commit()

    today = date.today().strftime("%Y-%m-%d")
    y, m = date.today().year, date.today().month

    # ================= 1. todos 按天过滤 =================
    print("\n[1] todos 按天过滤 (user_id + done + due_date)")

    def a_todo():
        cur.execute(
            f"SELECT {TODO_COLS} FROM todos IGNORE INDEX ({NEW_IDX}) "
            f"WHERE user_id = %s AND done = %s AND (due_date = %s OR due_date IS NULL) "
            f"ORDER BY created_at DESC", (uid, 0, today))
        cur.fetchall()

    def b_todo():
        cur.execute(
            f"SELECT {TODO_COLS} FROM todos "
            f"WHERE user_id = %s AND done = %s AND (due_date = %s OR due_date IS NULL) "
            f"ORDER BY created_at DESC", (uid, 0, today))
        cur.fetchall()

    def c_todo():
        cur.execute(
            f"SELECT {TODO_COLS} FROM todos WHERE user_id = %s AND done = %s AND due_date = %s "
            f"UNION ALL "
            f"SELECT {TODO_COLS} FROM todos WHERE user_id = %s AND done = %s AND due_date IS NULL "
            f"ORDER BY created_at DESC", (uid, 0, today, uid, 0))
        cur.fetchall()

    a = timed(a_todo)
    b = timed(b_todo)
    c = timed(c_todo)
    row("A 原查询 + 无新索引", a)
    row("B 原查询 + 新索引", b, a)
    row("C UNION ALL + 新索引", c, a)

    # ================= 2. transactions 按月 =================
    print("\n[2] transactions 按月聚合")

    start = f"{y:04d}-{m:02d}-01 00:00:00"
    end = (f"{y + 1:04d}-01-01 00:00:00" if m == 12
           else f"{y:04d}-{m + 1:02d}-01 00:00:00")

    def a_tx():
        cur.execute(
            f"SELECT type, COUNT(*) c, SUM(ABS(amount)) s FROM transactions IGNORE INDEX ({NEW_TX_IDX}) "
            "WHERE user_id = %s AND YEAR(time) = %s AND MONTH(time) = %s GROUP BY type",
            (uid, y, m))
        cur.fetchall()

    def b_tx():
        cur.execute(
            "SELECT type, COUNT(*) c, SUM(ABS(amount)) s FROM transactions "
            "WHERE user_id = %s AND YEAR(time) = %s AND MONTH(time) = %s GROUP BY type",
            (uid, y, m))
        cur.fetchall()

    def c_tx():
        cur.execute(
            "SELECT type, COUNT(*) c, SUM(ABS(amount)) s FROM transactions "
            "WHERE user_id = %s AND time >= %s AND time < %s GROUP BY type",
            (uid, start, end))
        cur.fetchall()

    a = timed(a_tx)
    b = timed(b_tx)
    c = timed(c_tx)
    row("A YEAR()/MONTH() + 无新索引", a)
    row("B YEAR()/MONTH() + 新索引", b, a)
    row("C 时间区间 + 新索引", c, a)

    # ================= 3. 全量 COUNT(成就 metric) =================
    print("\n[3] 成就 metric 单条 COUNT(*)")
    row("COUNT(*) done_todo", timed(lambda: (cur.execute(
        "SELECT COUNT(*) c FROM todos WHERE user_id = %s AND done = 1", (uid,)), cur.fetchall())))

    # ================= 4. 成就评估整体 =================
    print("\n[4] 成就评估(12 条定义)")
    cur.execute("SELECT code, metric_type FROM achievement_definitions WHERE is_active = 1")
    defs = cur.fetchall()

    METRIC_SQL = {
        "todo_count": "SELECT COUNT(*) c FROM todos WHERE user_id = %s",
        "done_todo": "SELECT COUNT(*) c FROM todos WHERE user_id = %s AND done = 1",
        "goal_count": "SELECT COUNT(*) c FROM goals WHERE user_id = %s",
        "done_goal": "SELECT COUNT(*) c FROM goals WHERE user_id = %s AND done = 1",
        "tx_count": "SELECT COUNT(*) c FROM transactions WHERE user_id = %s",
        "tx_income_total": "SELECT COALESCE(SUM(amount),0) c FROM transactions WHERE user_id=%s AND type='income'",
        "tx_expense_total": "SELECT COALESCE(SUM(ABS(amount)),0) c FROM transactions WHERE user_id=%s AND type='expense'",
        "meal_count": "SELECT COUNT(*) c FROM meals WHERE user_id = %s",
        "early_reminder": "SELECT COUNT(*) c FROM reminders WHERE user_id=%s AND enabled=1",
    }

    def old_ach():
        for d in defs:
            cur.execute("SELECT id FROM achievements WHERE user_id = %s AND type = %s", (uid, d["code"]))
            cur.fetchone()
            sql = METRIC_SQL.get(d["metric_type"])
            if sql:
                cur.execute(sql, (uid,))
                cur.fetchone()

    def new_ach_no_cache():
        cur.execute("SELECT type FROM achievements WHERE user_id = %s", (uid,))
        unlocked = {r["type"] for r in cur.fetchall()}
        needed = {d["metric_type"] for d in defs
                  if d["code"] not in unlocked and d["metric_type"] in METRIC_SQL}
        for metric in needed:
            cur.execute(METRIC_SQL[metric], (uid,))
            cur.fetchone()

    a = timed(old_ach, repeat=5)
    b = timed(new_ach_no_cache, repeat=5)
    row("A 改造前(每条 2 条 SQL)", a)
    row("B 去重后(无跨请求缓存)", b, a)
    print("    (B 之上再加 Redis metric 缓存,命中时趋近 0)")

    if keep:
        print("\n(--keep) 保留合成数据,user_id =", uid)
    else:
        print("\n清理合成数据 ...")
        cleanup(cur, uid)
        conn.commit()
    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=30000)
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()
    print("=" * 64)
    print(f"Phase 1 查询基准 (rows={args.rows})")
    print("=" * 64)
    run(args.rows, args.keep)
