"""应用 Phase 1 性能索引(幂等)

用法:
    cd backend
    ./.venv/Scripts/python.exe scripts/apply_perf_indexes.py           # 应用
    ./.venv/Scripts/python.exe scripts/apply_perf_indexes.py --dry-run # 只看要做什么
    ./.venv/Scripts/python.exe scripts/apply_perf_indexes.py --explain # 应用后对比执行计划

为什么用脚本而不是直接跑 SQL:
MySQL 不支持 "ADD INDEX IF NOT EXISTS",重复执行会报 1061。
这里先查 information_schema,只在索引缺失时才 ALTER。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_sync_connection

# (表, 索引名, 列定义)
INDEXES = [
    ("todos", "idx_user_done_due", "(user_id, done, due_date)"),
    ("todos", "idx_user_done_created", "(user_id, done, created_at)"),
    ("transactions", "idx_user_time", "(user_id, time)"),
    ("transactions", "idx_user_type_time", "(user_id, type, time)"),
    ("goals", "idx_user_done", "(user_id, done)"),
    ("reminders", "idx_user_enabled_time", "(user_id, enabled, time)"),
]

EXPLAINS = [
    ("transactions 按时间范围聚合",
     "EXPLAIN SELECT type, COUNT(*), SUM(ABS(amount)) FROM transactions "
     "WHERE user_id = 1 AND time >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) GROUP BY type"),
    ("todos 当天待办(done=false)",
     "EXPLAIN SELECT id, text, done, due_date FROM todos WHERE user_id = 1 AND done = 0 AND due_date = '2026-01-01'"),
    ("todos 当天待办(due_date 为空)",
     "EXPLAIN SELECT id, text, done, due_date FROM todos WHERE user_id = 1 AND done = 0 AND due_date IS NULL"),
]


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone()["c"] > 0


def index_exists(cur, table: str, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
        (table, name),
    )
    return cur.fetchone()["c"] > 0


def apply_indexes(dry_run: bool = False) -> tuple[int, int]:
    applied = skipped = 0
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for table, name, cols in INDEXES:
                if not table_exists(cur, table):
                    print(f"  [SKIP] {table}: 表不存在")
                    skipped += 1
                    continue
                if index_exists(cur, table, name):
                    print(f"  [OK]   {table}.{name} 已存在")
                    skipped += 1
                    continue
                ddl = f"ALTER TABLE {table} ADD INDEX {name} {cols}"
                print(f"  [ADD]  {ddl}")
                if not dry_run:
                    cur.execute(ddl)
                    applied += 1
            if not dry_run:
                conn.commit()
    finally:
        conn.close()
    return applied, skipped


def show_explain(label: str) -> None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for title, sql in EXPLAINS:
                print(f"\n--- {title} ---")
                cur.execute(sql)
                for row in cur.fetchall():
                    print("    table={t} type={ty} key={k} rows={r} extra={e}".format(
                        t=row.get("table"), ty=row.get("type"), k=row.get("key"),
                        r=row.get("rows"), e=row.get("Extra")))
    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print("=" * 60)
    print("Phase 1 性能索引" + ("(dry-run)" if dry else ""))
    print("=" * 60)
    applied, skipped = apply_indexes(dry_run=dry)
    print(f"\n完成:新增 {applied} 个,跳过 {skipped} 个")
    if "--explain" in sys.argv and not dry:
        print("\n" + "=" * 60)
        print("执行计划")
        print("=" * 60)
        show_explain("")
