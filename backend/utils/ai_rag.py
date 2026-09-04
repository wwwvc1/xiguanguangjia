"""RAG 引擎(支持持久化 + 动态增删文档)"""
import os
import shutil
import uuid
from typing import List, Optional

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
import chromadb

from config import settings

_rag_engine: Optional["RAGEngine"] = None
COLLECTION_NAME = "habit_knowledge"


class RAGEngine:
    """RAG 引擎包装,持久化 + 动态增删"""

    def __init__(self, persist_dir: str, collection_name: str = COLLECTION_NAME):
        self.persist_dir = persist_dir
        self.collection_name = collection_name

        # 1. 持久化 Client
        os.makedirs(persist_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=persist_dir)

        # 2. Embedding
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # 3. 获取或创建 collection(用 LangChain 包装)
        # LangChain 的 Chroma 在 init 时不会重建已有 collection
        self.vectorstore = Chroma(
            client=self.chroma_client,
            collection_name=collection_name,
            embedding_function=self.embeddings,
        )

    # ---------- 文档管理 ----------
    def list_documents(self) -> List[dict]:
        """列出 collection 中所有文档(按 doc_id 分组)"""
        col = self.chroma_client.get_collection(self.collection_name)
        metadatas = col.get(include=["metadatas"]).get("metadatas", [])
        # 聚合
        docs = {}
        for md in metadatas:
            doc_id = md.get("doc_id")
            if not doc_id:
                continue
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": md.get("filename", ""),
                    "chunk_count": 0,
                }
            docs[doc_id]["chunk_count"] += 1
        return list(docs.values())

    def add_document(self, file_path: str, doc_id: int, filename: str) -> int:
        """把单个文档切分后入向量库,返回 chunk 数"""
        loader = TextLoader(file_path, encoding="utf-8")
        raw_docs = loader.load()

        # 切分
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n## ", "\n### ", "\n\n", "\n", "。", " "]
        )
        chunks = text_splitter.split_documents(raw_docs)

        # 注入 doc_id metadata
        for chunk in chunks:
            chunk.metadata["doc_id"] = str(doc_id)
            chunk.metadata["filename"] = filename
            chunk.metadata["chunk_uuid"] = str(uuid.uuid4())

        # 入库
        self.vectorstore.add_documents(chunks)
        return len(chunks)

    def remove_document(self, doc_id: int):
        """从向量库删除指定 doc_id 的所有 chunks"""
        col = self.chroma_client.get_collection(self.collection_name)
        # Chroma 的 where 过滤
        col.delete(where={"doc_id": str(doc_id)})

    def clear(self):
        """清空整个 collection(慎用)"""
        col = self.chroma_client.get_collection(self.collection_name)
        all_ids = col.get(include=[]).get("ids", [])
        if all_ids:
            col.delete(ids=all_ids)

    def get_raw_collection(self):
        return self.chroma_client.get_collection(self.collection_name)

    # ---------- 检索 ----------
    def search(self, query: str, top_k: int = 3) -> List[str]:
        """检索知识库,返回最相关的 top_k 个文本片段"""
        results = self.vectorstore.similarity_search(query, k=top_k)
        return [doc.page_content for doc in results]

    def build_context_string(self, query: str, top_k: int = 3) -> str:
        """检索并组装成上下文字符串"""
        chunks = self.search(query, top_k=top_k)
        return "\n\n".join(f"[参考]\n{chunk}" for chunk in chunks)


def _load_static_kb(engine: RAGEngine) -> int:
    """首次启动:把 knowledge_base/*.md 加载进向量库"""
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base")
    if not os.path.isdir(kb_dir):
        return 0
    total_chunks = 0
    for filename in os.listdir(kb_dir):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(kb_dir, filename)
        try:
            n = engine.add_document(
                file_path=filepath,
                doc_id=f"static_{filename}",  # 静态 doc 用文件名做 id
                filename=filename
            )
            total_chunks += n
            print(f"  [static KB] {filename}: {n} chunks")
        except Exception as e:
            print(f"  [static KB] {filename} failed: {e}")
    return total_chunks


def init_rag_engine() -> RAGEngine:
    """启动时调用,初始化 RAG 引擎。"""
    global _rag_engine
    persist_dir = settings.CHROMA_DB_PATH
    engine = RAGEngine(persist_dir=persist_dir)

    # 首次启动:静态 KB 还没入库才加载
    existing = engine.list_documents()
    if not existing:
        print("[RAG] 首次启动,加载静态知识库...")
        n = _load_static_kb(engine)
        print(f"[RAG] 静态知识库加载完成,共 {n} chunks")
    else:
        print(f"[RAG] 已有 {len(existing)} 个文档,跳过静态加载")

    _rag_engine = engine
    print(f"[RAG] 引擎就绪,持久化路径: {persist_dir}")
    return engine


def get_rag_engine() -> RAGEngine:
    """获取 RAG 引擎实例(单例)"""
    global _rag_engine
    if _rag_engine is None:
        init_rag_engine()
    return _rag_engine


# 向后兼容(原 API)
def search_knowledge(query: str, top_k: int = 3) -> list[str]:
    engine = get_rag_engine()
    return engine.search(query, top_k=top_k)


def build_context_string(query: str, top_k: int = 3) -> str:
    engine = get_rag_engine()
    return engine.build_context_string(query, top_k=top_k)
