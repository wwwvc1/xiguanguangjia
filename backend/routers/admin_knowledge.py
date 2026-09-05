"""管理员 RAG 知识库管理

支持「静态」(git 跟踪 .md) + 「上传」(admin 上传)双源统一 CRUD。
- 静态:列出/预览/编辑内容/重新索引;不允许 web 删除(避免与 git 冲突)
- 上传:列出/预览/编辑内容/重新索引/删除
"""
import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel, Field
from database import get_connection
from utils.admin_auth import get_current_admin
from utils.operation_logger import log_admin_action
from utils.ai_rag import get_rag_engine

router = APIRouter(prefix="/api/admin/knowledge", tags=["admin-knowledge"])

# 路径
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(_BACKEND_DIR, "knowledge_base")
UPLOAD_DIR = os.path.join(KB_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {".md", ".txt"}

# ID 字符串前缀约定
STATIC_PREFIX = "static_"
UPLOAD_PREFIX = "upload_"


# ============= 辅助 =============

def _chunk_count_map() -> dict[str, int]:
    """从 Chroma 实时算每个 doc_id 的 chunk 数"""
    engine = get_rag_engine()
    return {d["doc_id"]: d["chunk_count"] for d in engine.list_documents()}


def _to_static_doc(filename: str, stat, chunk_map: dict) -> dict:
    doc_id = f"{STATIC_PREFIX}{filename}"
    return {
        "id": doc_id,
        "source": "static",
        "filename": filename,
        "chunk_count": chunk_map.get(doc_id, 0),
        "size_bytes": stat.st_size,
        "status": "indexed",
        "error_msg": None,
        "uploaded_by": None,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "editable": True,
        "deletable": False,
    }


def _to_uploaded_doc(row: dict, chunk_map: dict) -> dict:
    doc_id = f"{UPLOAD_PREFIX}{row['id']}"
    return {
        "id": doc_id,
        "source": "uploaded",
        "filename": row["filename"],
        "chunk_count": chunk_map.get(doc_id, 0),
        "size_bytes": row.get("file_size", 0),
        "status": row["status"],
        "error_msg": row.get("error_msg"),
        "uploaded_by": row["uploaded_by"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "editable": True,
        "deletable": True,
    }


def _resolve_doc(doc_id: str) -> tuple[str, dict]:
    """根据字符串 id 解析出 (source, info)。
    info 对静态是 (filepath, filename),对上传是 DB row dict。
    """
    if doc_id.startswith(STATIC_PREFIX):
        filename = doc_id[len(STATIC_PREFIX):]
        # 安全:防止 .. 路径穿越
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise HTTPException(status_code=400, detail="非法 doc_id")
        filepath = os.path.join(KB_DIR, filename)
        if not os.path.isfile(filepath):
            raise HTTPException(status_code=404, detail="静态文档不存在")
        return "static", (filepath, filename)
    if doc_id.startswith(UPLOAD_PREFIX):
        try:
            db_id = int(doc_id[len(UPLOAD_PREFIX):])
        except ValueError:
            raise HTTPException(status_code=400, detail="非法 doc_id")
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (db_id,))
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="上传文档不存在")
                return "uploaded", row
        finally:
            conn.close()
    raise HTTPException(status_code=400, detail="未知 doc_id 前缀")


# ============= Endpoints =============

@router.get("/documents")
def list_documents(
    source: Optional[str] = None,        # "static" | "uploaded" | None=全部
    is_active: Optional[bool] = None,    # 仅对 uploaded 生效
    admin: dict = Depends(get_current_admin)
):
    """文档列表:静态(扫 KB 目录) + 上传(查 DB)双源合并,chunk_count 从 Chroma 实时算"""
    chunk_map = _chunk_count_map()
    items: list[dict] = []

    if source in (None, "static"):
        for fn in sorted(os.listdir(KB_DIR)):
            if not fn.endswith(".md") or fn.startswith("."):
                continue
            full = os.path.join(KB_DIR, fn)
            if not os.path.isfile(full):
                continue
            try:
                stat = os.stat(full)
            except OSError:
                continue
            items.append(_to_static_doc(fn, stat, chunk_map))

    if source in (None, "uploaded"):
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                where = ["1=1"]
                params: list = []
                if is_active is not None:
                    where.append("status = %s")
                    params.append("indexed" if is_active else "pending")
                cursor.execute(
                    "SELECT * FROM knowledge_documents WHERE " + " AND ".join(where) + " ORDER BY id DESC",
                    tuple(params)
                )
                for row in cursor.fetchall():
                    items.append(_to_uploaded_doc(row, chunk_map))
        finally:
            conn.close()

    # 静态在前,上传在后,各自按文件名/id 排
    return {"documents": items}


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin)
):
    """上传 .md/.txt,落盘 + DB + 向量化"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"只支持 {', '.join(ALLOWED_EXT)} 格式")

    safe_name = f"{uuid.uuid4().hex}{ext}"
    disk_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码必须是 UTF-8")
    with open(disk_path, "w", encoding="utf-8") as f:
        f.write(text)
    file_size = len(content)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_documents (filename, storage_path, chunk_count, file_size, status, uploaded_by)
                   VALUES (%s, %s, 0, %s, 'pending', %s)""",
                (file.filename, disk_path, file_size, admin["id"])
            )
            db_id = cursor.lastrowid
            conn.commit()
    finally:
        conn.close()

    doc_id = f"{UPLOAD_PREFIX}{db_id}"
    try:
        engine = get_rag_engine()
        chunk_count = engine.add_document(
            file_path=disk_path,
            doc_id=doc_id,
            filename=file.filename
        )
    except Exception as e:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE knowledge_documents SET status = 'failed', error_msg = %s WHERE id = %s",
                    (str(e)[:500], db_id)
                )
                conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=f"向量化失败: {e}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_documents SET status = 'indexed', chunk_count = %s WHERE id = %s",
                (chunk_count, db_id)
            )
            conn.commit()
            cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (db_id,))
            row = cursor.fetchone()
    finally:
        conn.close()

    log_admin_action(request, admin, "upload_knowledge_doc", "knowledge_document", db_id,
                     {"filename": file.filename, "chunk_count": chunk_count})
    return _to_uploaded_doc(row, _chunk_count_map())


@router.get("/documents/{doc_id}/content")
def get_document_content(doc_id: str, admin: dict = Depends(get_current_admin)):
    """获取完整原文(供编辑器初始化用,不限 2000 字符)"""
    source, info = _resolve_doc(doc_id)
    if source == "static":
        filepath, filename = info
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"id": doc_id, "filename": filename, "content": content, "truncated": False}
    else:
        row = info
        if not os.path.isfile(row["storage_path"]):
            raise HTTPException(status_code=400, detail="源文件已丢失")
        with open(row["storage_path"], "r", encoding="utf-8") as f:
            content = f.read()
        return {"id": doc_id, "filename": row["filename"], "content": content, "truncated": False}


class ContentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5 * 1024 * 1024)


@router.put("/documents/{doc_id}/content")
def update_document_content(
    doc_id: str,
    payload: ContentUpdate,
    request: Request,
    admin: dict = Depends(get_current_admin)
):
    """更新文档内容:写盘 + 删旧 chunks + 重新入库(自动 reindex)"""
    source, info = _resolve_doc(doc_id)
    engine = get_rag_engine()

    if source == "static":
        filepath, filename = info
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(payload.content)
        try:
            engine.remove_document(doc_id)
        except Exception as e:
            print(f"[edit static] remove_document 失败(非致命): {e}")
        chunk_count = engine.add_document(
            file_path=filepath,
            doc_id=doc_id,
            filename=filename
        )
        log_admin_action(request, admin, "edit_knowledge_doc", "knowledge_document", None,
                         {"source": "static", "filename": filename, "chunk_count": chunk_count})
        return {"id": doc_id, "source": "static", "filename": filename, "chunk_count": chunk_count, "message": "已保存并重新索引"}

    else:
        row = info
        disk_path = row["storage_path"]
        with open(disk_path, "w", encoding="utf-8") as f:
            f.write(payload.content)
        file_size = len(payload.content.encode("utf-8"))
        try:
            engine.remove_document(doc_id)
        except Exception as e:
            print(f"[edit upload] remove_document 失败(非致命): {e}")
        chunk_count = engine.add_document(
            file_path=disk_path,
            doc_id=doc_id,
            filename=row["filename"]
        )
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE knowledge_documents SET chunk_count = %s, file_size = %s, status = 'indexed', error_msg = NULL WHERE id = %s",
                    (chunk_count, file_size, row["id"])
                )
                conn.commit()
        finally:
            conn.close()
        log_admin_action(request, admin, "edit_knowledge_doc", "knowledge_document", row["id"],
                         {"filename": row["filename"], "chunk_count": chunk_count})
        return {"id": doc_id, "source": "uploaded", "filename": row["filename"], "chunk_count": chunk_count, "message": "已保存并重新索引"}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, request: Request, admin: dict = Depends(get_current_admin)):
    """删除文档(只支持上传的,静态不允许删)"""
    if not doc_id.startswith(UPLOAD_PREFIX):
        raise HTTPException(status_code=400, detail="静态文档不能从 web 删除,请通过 git 流程管理")
    source, info = _resolve_doc(doc_id)
    # resolve_doc 已经检查过 DB 存在性
    row = info
    storage_path = row["storage_path"]

    try:
        engine = get_rag_engine()
        engine.remove_document(doc_id)
    except Exception as e:
        print(f"[Knowledge] 向量库删除失败(非致命): {e}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM knowledge_documents WHERE id = %s", (row["id"],))
            conn.commit()
    finally:
        conn.close()

    try:
        if os.path.isfile(storage_path):
            os.remove(storage_path)
    except Exception as e:
        print(f"[Knowledge] 磁盘文件删除失败(非致命): {e}")

    log_admin_action(request, admin, "delete_knowledge_doc", "knowledge_document", row["id"],
                     {"filename": row["filename"]})
    return {"message": "已删除", "id": doc_id}


@router.post("/documents/{doc_id}/reindex")
def reindex_document(doc_id: str, request: Request, admin: dict = Depends(get_current_admin)):
    """重新向量化(先删后加)。静态和上传都支持。"""
    source, info = _resolve_doc(doc_id)
    engine = get_rag_engine()

    if source == "static":
        filepath, filename = info
        try:
            engine.remove_document(doc_id)
        except Exception as e:
            print(f"[reindex static] remove_document 失败(非致命): {e}")
        chunk_count = engine.add_document(
            file_path=filepath,
            doc_id=doc_id,
            filename=filename
        )
        log_admin_action(request, admin, "reindex_knowledge_doc", "knowledge_document", None,
                         {"source": "static", "filename": filename})
        return {"id": doc_id, "source": "static", "filename": filename, "chunk_count": chunk_count}

    else:
        row = info
        if not os.path.isfile(row["storage_path"]):
            raise HTTPException(status_code=400, detail="源文件已丢失,无法重新索引")
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE knowledge_documents SET status = 'pending' WHERE id = %s", (row["id"],))
                conn.commit()
        finally:
            conn.close()

        try:
            engine.remove_document(doc_id)
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
                        (str(e)[:500], row["id"])
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
                    (chunk_count, row["id"])
                )
                conn.commit()
                cursor.execute("SELECT * FROM knowledge_documents WHERE id = %s", (row["id"],))
                new_row = cursor.fetchone()
        finally:
            conn.close()
        log_admin_action(request, admin, "reindex_knowledge_doc", "knowledge_document", row["id"])
        return _to_uploaded_doc(new_row, _chunk_count_map())


@router.get("/preview/{doc_id}")
def preview_document(doc_id: str, max_chars: int = 2000, admin: dict = Depends(get_current_admin)):
    """读原文前 N 字符用于预览"""
    source, info = _resolve_doc(doc_id)
    if source == "static":
        filepath, filename = info
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(max_chars)
        return {
            "id": doc_id,
            "filename": filename,
            "content": content,
            "truncated": len(content) >= max_chars
        }
    else:
        row = info
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
