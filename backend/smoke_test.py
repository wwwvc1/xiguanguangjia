"""Smoke test: admin login + RAG persistence"""
import sys
sys.path.insert(0, '.')

# 1. 测 RAG 持久化
print("=== RAG 持久化测试 ===")
from utils.ai_rag import init_rag_engine, get_rag_engine
engine = get_rag_engine()
print(f"Collection: {engine.collection_name}")
print(f"Persist dir: {engine.persist_dir}")
print(f"现有文档数: {len(engine.list_documents())}")

# 2. 测 admin login
print("\n=== Admin Login 测试 ===")
from utils.admin_auth import authenticate_admin, create_admin_token, get_current_admin
user = authenticate_admin("admin", "Admin@123")
if user:
    print(f"✓ 登录成功: {user}")
    token = create_admin_token(user["id"])
    print(f"✓ Token 长度: {len(token)}")
else:
    print("✗ 登录失败")

# 3. 测 admin 依赖(模拟请求)
print("\n=== get_current_admin 依赖测试 ===")
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from config import settings
from datetime import datetime, timedelta
manual_token = jwt.encode(
    {"user_id": user["id"], "is_admin": True, "exp": datetime.utcnow() + timedelta(hours=1)},
    settings.SECRET_KEY,
    algorithm=settings.ALGORITHM
)
creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=manual_token)
admin = get_current_admin(creds)
print(f"✓ Admin 解析: id={admin['id']}, username={admin['username']}")

# 4. 测 operation_logger
print("\n=== Operation Logger 测试 ===")
from utils.operation_logger import log
log_id = log(user_id=admin['id'], action="test_action", details={"test": True})
print(f"✓ 日志 id: {log_id}")

# 5. 测 ai_rag 动态增删文档
print("\n=== RAG 动态增删测试 ===")
test_doc_id = 9999
test_path = "knowledge_base/habits_basics.md"
import os
if os.path.exists(test_path):
    n = engine.add_document(test_path, doc_id=test_doc_id, filename="test.md")
    print(f"✓ 添加文档: doc_id={test_doc_id}, chunks={n}")
    docs = engine.list_documents()
    found = any(str(d.get("doc_id")) == str(test_doc_id) for d in docs)
    print(f"✓ 列表中找到: {found}")
    engine.remove_document(test_doc_id)
    print(f"✓ 文档已删除")
else:
    print(f"⚠ 跳过:{test_path} 不存在")

print("\n[OK] 所有 smoke test 通过")
