import sys, os
sys.path.insert(0, os.path.abspath("."))
from core.database import get_sync_connection

conn = get_sync_connection()
try:
    with conn.cursor() as cur:
        for t in ("checkins", "achievements", "todos", "transactions", "meals", "user_settings", "achievement_definitions"):
            print("=" * 50)
            cur.execute("SELECT COUNT(*) AS c FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (t,))
            if not cur.fetchone()["c"]:
                print(t, "-> TABLE MISSING"); continue
            cur.execute("SHOW INDEX FROM " + t)
            idx = {}
            for r in cur.fetchall():
                idx.setdefault(r["Key_name"], []).append((r["Seq_in_index"], r["Column_name"], r["Non_unique"]))
            print(t, "indexes:")
            for name, cols in idx.items():
                cols.sort()
                print("   ", name, "->", [c[1] for c in cols], "(unique)" if cols[0][2] == 0 else "")
            cur.execute("SELECT COUNT(*) AS c FROM " + t)
            print("    rows:", cur.fetchone()["c"])
finally:
    conn.close()
