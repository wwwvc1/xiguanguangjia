"""Apply phase 3 migration to MySQL (支持 DELIMITER)"""
import re
import pymysql
from config import settings

conn = pymysql.connect(
    host=settings.DB_HOST, port=settings.DB_PORT,
    user=settings.DB_USER, password=settings.DB_PASSWORD,
    database=settings.DB_NAME, charset='utf8mb4'
)
cur = conn.cursor()

with open('sql/migration_phase3.sql', 'r', encoding='utf-8') as f:
    raw = f.read()


def split_sql(text: str) -> list[str]:
    """按 DELIMITER 切分 SQL 语句,支持 DELIMITER // 风格"""
    stmts = []
    delim = ';'
    buf = []
    for line in text.split('\n'):
        stripped = line.strip()
        # 处理 DELIMITER 指令
        m = re.match(r'^DELIMITER\s+(\S+)\s*$', stripped, re.IGNORECASE)
        if m:
            if buf:
                stmts.append(('\n'.join(buf)).strip())
                buf = []
            delim = m.group(1)
            continue
        # 跳过空行和注释
        if not stripped or stripped.startswith('--'):
            continue
        buf.append(line)
        # 用当前 delimiter 切分
        if stripped.endswith(delim):
            stmt = '\n'.join(buf).strip()
            # 去掉末尾 delimiter
            if stmt.endswith(delim):
                stmt = stmt[:-len(delim)].rstrip()
            stmts.append(stmt)
            buf = []
    if buf:
        last = '\n'.join(buf).strip()
        if last:
            stmts.append(last)
    return stmts


stmts = split_sql(raw)
print(f'Total statements: {len(stmts)}')

for i, stmt in enumerate(stmts, 1):
    if not stmt:
        continue
    try:
        cur.execute(stmt)
        preview = stmt[:80].replace('\n', ' ').strip()
        print(f'OK [{i}/{len(stmts)}]: {preview}...')
    except Exception as e:
        print(f'FAIL [{i}]: {e}')
        print(f'  SQL: {stmt[:300]}')

conn.commit()

# 验证
cur.execute('SHOW TABLES')
tables = sorted([r[0] for r in cur.fetchall()])
print(f'\n--- Tables ({len(tables)}): {tables}')

cur.execute('DESCRIBE users')
user_cols = [r[0] for r in cur.fetchall()]
print(f'\n--- users columns: {user_cols}')

cur.execute('DESCRIBE user_settings')
us_cols = [r[0] for r in cur.fetchall()]
print(f'\n--- user_settings columns: {us_cols}')

cur.execute('DESCRIBE llm_models')
llm_cols = [r[0] for r in cur.fetchall()]
print(f'\n--- llm_models columns: {llm_cols}')

cur.execute('SELECT COUNT(*) FROM llm_models')
print(f'\n--- llm_models rows: {cur.fetchone()[0]}')

cur.close()
conn.close()
print('\n[OK] Migration done.')
