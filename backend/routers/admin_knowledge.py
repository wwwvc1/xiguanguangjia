"""管理员 RAG 知识库管理"""
import os
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from database import get_connection
from utils.admin_auth import get_current_admin
from utils.operation_logger import log_admin_action
from utils.ai_rag import get_rag_engine

router = APIRouter(prefix="/api/admin/knowledge", tags=["admin-knowledge"])

# 文档存储根目录
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {".md", ".txt"}


def _to_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "storage_path": row["storage_path"],
        "chunk_count": row.get("chunk_count", 0),
        "status": row["status"],
        "error_msg": row.get("error_msg"),
        "uploaded_by": row["uploaded_by"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


@router.get("/documents")
def list_documents(
    is_active: Optional[bool] = None,
    admin: dict = Depends(get_current_admin)
):
    """文档列表(来自 DB + 引擎实际 chunks)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            where = ["1=1"]
            params: list = []
            if is_active is not None:
                where.append("status = %s")
                params.append("indexed" if is_active else "pending")
            sql = "SELECT * FROM knowledge_documents WHERE " + " AND ".join(where) + " ORDER BY id DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return {"documents": [_to_response(r) for r in rows]}
    finally:
        conn.close()


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin)
):
    """上传 .md/.txt 文档,自动切分并入库"""
    # 1. 校验扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"只支持 {', '.join(ALLOWED_EXT)} 格式")

    # 2. 保存到磁盘
    safe_name = f"{uuid.uuid4().hex}{ext}"
    disk_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码必须是 UTF-8")
    with open(disk_path, "w", encoding="utf-8") as f:
        f.write(text)

    # 3. 写 DB(初始状态 pending)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_documents (filename, storage_path, chunk_count, status, uploaded_by)
                   VALUES (%s, %s, 0, 'pending', %s)""",
                (file.filename, disk_path, admin["id"])
            )
            doc_id = cursor.lastrowid
            conn.commit()
    finally:
        conn.close()

    # 4. 入向量库
    try:
        engine = get_rag_engine()
        chunk_count = engine.add_document(
            file_path=disk_path,
            doc_id=doc_id,
            filename=file.filename
        )
    except Exception as e:
        # 入库失败 → 标 failed
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE knowledge_documents SET status = 'failed', error_msg = %s WHERE id = %s",
                    (str(e)[:500], doc_id)
                )
                conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=f"向量化失败: {e}")

    # 5. 更新 DB 为 indexed
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_documents SET status = 'indexed', chunk_count = %s WHERE id = %s",
                (chunk_count, doc_id)
            )
            conn.commit()
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (doc_id,))
            row = cursor.fetchone()
            log_admin_action(request, admin, "upload_knowledge_doc", "knowledge_document", doc_id,
                             {"filename": file.filename, "chunk_count": chunk_count})
            return _to_response(row)
    finally:
        conn.close()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    """删除文档(同时删 DB 行 + 磁盘文件 + 向量库)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (doc_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="文档不存在")
            storage_path = row["storage_path"]

            # 从向量库删
            try:
                engine = get_rag_engine()
                engine.remove_document(doc_id)
            except Exception as e:
                print(f"[Knowledge] 向量库删除失败(非致命): {e}")

            # 删 DB
            cursor.execute("DELETE FROM knowledge_documents WHERE id = %s", (doc_id,))
            conn.commit()

            # 删磁盘
            try:
                if os.path.isfile(storage_path):
                    os.remove(storage_path)
            except Exception as e:
                print(f"[Knowledge] 磁盘文件删除失败(非致命): {e}")

            log_admin_action(request, admin, "delete_knowledge_doc", "knowledge_document", doc_id,
                             {"filename": row["filename"]})
            return {"message": "已删除", "id": doc_id}
    finally:
        conn.close()


@router.post("/documents/{doc_id}/reindex")
def reindex_document(doc_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    """重新向量化(先删后加)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (doc_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="文档不存在")
            if not os.path.isfile(row["storage_path"]):
                raise HTTPException(status_code=400, detail="源文件已丢失,无法重新索引")
            cursor.execute("UPDATE knowledge_documents SET status = 'pending' WHERE id = %s", (doc_id,))
            conn.commit()
    finally:
        conn.close()

    try:
        engine = get_rag_engine()
        engine.remove_document(doc_id)  # 先清
        chunk_count = engine.add_document(
            file_path=row["storage_path"],
            doc_id=doc_id,
            filename=row["filename"]
        )
    except Exception as e:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE knowledge_documents SET status = 'failed', error_msg = %s WHERE id = %s",
                    (str(e)[:500], doc_id)
                )
                conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=f"重新索引失败: {e}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_documents SET status = 'indexed', chunk_count = %s, error_msg = NULL WHERE id = %s",
                (chunk_count, doc_id)
            )
            conn.commit()
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (doc_id,))
            new_row = cursor.fetchone()
            log_admin_action(request, admin, "reindex_knowledge_doc", "knowledge_document", doc_id)
            return _to_response(new_row)
    finally:
        conn.close()


@router.get("/preview/{doc_id}")
def preview_document(doc_id: int, max_chars: int = 2000, admin: dict = Depends(get_current_admin)):
    """读原文前 N 字符用于预览"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (doc_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="文档不存在")
            if not os.path.isfile(row["storage_path"]):
                raise HTTPException(status_code=400, detail="源文件已丢失")
            with open(row["storage_path"], "r", encoding="utf-8") as f:
                content = f.read(max_chars)
            return {
                "id": doc_id,
                "filename": row["filename"],
                "content": content,
                "truncated": len(content) >= max_chars
            }
    finally:
        conn.close()


@router.post("/test-search")
def test_search(query: str, top_k: int = 3, admin: dict = Depends(get_current_admin)):
    """管理员测试 RAG 检索"""
    engine = get_rag_engine()
    col = engine.get_raw_collection()
    results = col.query(query_texts=[query], n_results=top_k)
    docs = []
    for i, (doc_text, metadata) in enumerate(zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0]
    )):
        docs.append({
            "text": doc_text,
            "filename": metadata.get("filename"),
            "doc_id": metadata.get("doc_id"),
            "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None
        })
    return {"query": query, "results": docs}
