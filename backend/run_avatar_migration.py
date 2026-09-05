"""把 users.avatar 扩成 MEDIUMTEXT(允许 base64 头像)
直接 python run_avatar_migration.py 即可
"""
import pymysql
from config import settings

conn = pymysql.connect(
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME,
    charset="utf8mb4",
)
cur = conn.cursor()
cur.execute("ALTER TABLE users MODIFY COLUMN avatar MEDIUMTEXT")
conn.commit()

cur.execute("DESCRIBE users")
print("--- users columns ---")
for row in cur.fetchall():
    print(row)

cur.close()
conn.close()
print("\n[OK] users.avatar -> MEDIUMTEXT")
