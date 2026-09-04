"""
创建管理员账号
用法: python -m scripts.create_admin <username> <password> [nickname]
示例: python -m scripts.create_admin admin Admin@123 超级管理员
"""
import sys
import pymysql
from config import settings
from utils.auth import hash_password


def main():
    if len(sys.argv) < 3:
        print("用法: python -m scripts.create_admin <username> <password> [nickname]")
        print("示例: python -m scripts.create_admin admin Admin@123 超级管理员")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    nickname = sys.argv[3] if len(sys.argv) > 3 else username

    if len(password) < 6:
        print("错误: 密码至少 6 位")
        sys.exit(1)

    pwd_hash = hash_password(password)

    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn.cursor() as cur:
            # 检查是否已存在
            cur.execute("SELECT id, is_admin FROM users WHERE username = %s", (username,))
            existing = cur.fetchone()
            if existing:
                # 升级为管理员 + 设置密码
                cur.execute(
                    """UPDATE users
                       SET is_admin = 1, is_active = 1, password_hash = %s, nickname = %s
                       WHERE id = %s""",
                    (pwd_hash, nickname, existing["id"])
                )
                print(f"[OK] 已将用户 {username} (id={existing['id']}) 升级为管理员")
            else:
                # 新建一个 WeChat 登录用占位 openid(避免 NOT NULL 报错)
                placeholder_openid = f"admin_{username}_{int.from_bytes(username.encode(), 'little') & 0xFFFFFFFF:x}"
                cur.execute(
                    """INSERT INTO users (openid, username, password_hash, nickname, is_admin, is_active, last_login_at)
                       VALUES (%s, %s, %s, %s, 1, 1, NOW())""",
                    (placeholder_openid, username, pwd_hash, nickname)
                )
                print(f"[OK] 管理员 {username} 创建成功,密码已哈希存储")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
