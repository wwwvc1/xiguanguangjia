"""RAG 引擎(支持持久化 + 动态增删文档)

启动性能说明(踩过的坑,别再回退):
1. huggingface_hub 在 import 时就把 HF_HUB_OFFLINE 读成常量,之后再改
   os.environ 不生效 —— 于是每次启动都会去 huggingface.co 解析模型版本,
   断网/被墙时反复超时重试,启动卡 20s 以上。离线开关必须写在
   任何 langchain / transformers 导入之前(见文件顶部)。
2. 直接把本地 snapshot 绝对路径交给 SentenceTransformer,连版本解析都省了。
3. langchain / chromadb / torch / sentence-transformers 全部延迟 import:
   光 import 就要 10s+,不该出现在 uvicorn 启动和 --reload 重载的路径上。

## 本次改造(对应 agent改造方案.md 阶段二/三)

- 优先用 `langchain-chroma` / `langchain-huggingface`(官方维护的新包),
  没装时自动回退到已 sunset 的 `langchain_community`,避免直接崩。
- collection / 模型 / top_k / 阈值全部走 `core.config`,换模型不再改代码。
- `_local_model_path()` 泛化:不再硬编码 MiniLM 的缓存目录名。
- 检索可选**相似度阈值**(默认 0 = 关闭,保持改造前行为不变)。
"""
import os

# ⚠️ 必须在 import langchain / transformers / huggingface_hub 之前完成
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import threading
import time
import uuid
from typing import List, Optional

from core.config import settings

# 向后兼容:历史代码可能 import 这个常量
COLLECTION_NAME = settings.RAG_COLLECTION

_rag_engine: Optional["RAGEngine"] = None
_init_lock = threading.Lock()

_HF_HUB_DIR = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
_WEIGHT_SUFFIXES = (".safetensors", ".bin", ".onnx")


# ============================================================
# 依赖导入:新包优先,旧包兜底
# ============================================================
def _import_vectorstore():
    """返回 (Chroma 类, 来源标识)"""
    try:
        from langchain_chroma import Chroma  # type: ignore
        return Chroma, "langchain-chroma"
    except Exception:
        from langchain_community.vectorstores import Chroma  # type: ignore
        return Chroma, "langchain_community(已 sunset)"


def _import_embeddings():
    """返回 (HuggingFaceEmbeddings 类, 来源标识)"""
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore
        return HuggingFaceEmbeddings, "langchain-huggingface"
    except Exception:
        from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore
        return HuggingFaceEmbeddings, "langchain_community(已 sunset)"


# ============================================================
# 本地模型路径解析(泛化)
# ============================================================
def _has_weights(model_dir: str) -> bool:
    for _root, _dirs, files in os.walk(model_dir):
        if any(f.endswith(_WEIGHT_SUFFIXES) for f in files):
            return True
    return False


def _is_model_dir(path: str) -> bool:
    return (os.path.isdir(path)
            and os.path.isfile(os.path.join(path, "config.json"))
            and _has_weights(path))


def _hf_cache_dir_name(model_name: str) -> str:
    """BAAI/bge-small-zh-v1.5 -> models--BAAI--bge-small-zh-v1.5"""
    return "models--" + model_name.replace("/", "--")


def _local_model_path(model_name: Optional[str] = None) -> Optional[str]:
    """返回本地已缓存的模型目录;没有则 None。

    顺序:
    1. `EMBED_LOCAL_DIR`(显式指定的本地目录,最高优先级)
    2. HF cache 的 snapshots/<rev>,refs/main 指向的版本优先
    """
    explicit = settings.embed_local_dir
    if explicit and _is_model_dir(explicit):
        return explicit

    name = model_name or settings.EMBED_MODEL_NAME
    cache_name = _hf_cache_dir_name(name)
    snap_root = os.path.join(_HF_HUB_DIR, cache_name, "snapshots")
    if not os.path.isdir(snap_root):
        return None

    names = sorted(os.listdir(snap_root))
    ref_file = os.path.join(_HF_HUB_DIR, cache_name, "refs", "main")
    if os.path.isfile(ref_file):
        try:
            with open(ref_file, "r", encoding="utf-8") as f:
                ref_name = f.read().strip()
            if ref_name in names:
                names.remove(ref_name)
                names.insert(0, ref_name)
        except OSError:
            pass

    for name_ in names:
        candidate = os.path.join(snap_root, name_)
        if _is_model_dir(candidate):
            return candidate
    return None


class RAGEngine:
    """RAG 引擎包装,持久化 + 动态增删"""

    def __init__(self, persist_dir: Optional[str] = None, collection_name: Optional[str] = None):
        t_dep = time.time()
        import chromadb

        Chroma, vs_src = _import_vectorstore()
        HuggingFaceEmbeddings, emb_src = _import_embeddings()
        print(f"[RAG] 依赖导入完成 {time.time() - t_dep:.2f}s "
              f"(vectorstore={vs_src}, embeddings={emb_src})", flush=True)

        self.persist_dir = persist_dir or settings.chroma_dir
        self.collection_name = collection_name or settings.RAG_COLLECTION

        os.makedirs(self.persist_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=self.persist_dir)

        # Embedding:优先本地目录(完全不联网)
        local_model = _local_model_path()
        if local_model:
            t = time.time()
            self.embeddings = HuggingFaceEmbeddings(model_name=local_model)
            print(f"[RAG] 本地模型加载完成 {time.time() - t:.2f}s"
                  f"(路径: {local_model})", flush=True)
        else:
            print(f"[RAG] 未找到本地模型缓存({settings.EMBED_MODEL_NAME}),"
                  "首次将联网下载(离线环境请先缓存)", flush=True)
            self.embeddings = HuggingFaceEmbeddings(model_name=settings.EMBED_MODEL_NAME)

        self.vectorstore = Chroma(
            client=self.chroma_client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )

    # ---------- 文档管理 ----------
    def list_documents(self) -> List[dict]:
        col = self.chroma_client.get_collection(self.collection_name)
        metadatas = col.get(include=["metadatas"]).get("metadatas", [])
        docs: dict = {}
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

    def add_document(self, file_path: str, doc_id, filename: str) -> int:
        from langchain_community.document_loaders import TextLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        raw_docs = TextLoader(file_path, encoding="utf-8").load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n## ", "\n### ", "\n\n", "\n", "。", " "],
        )
        chunks = splitter.split_documents(raw_docs)
        for chunk in chunks:
            chunk.metadata["doc_id"] = str(doc_id)
            chunk.metadata["filename"] = filename
            chunk.metadata["chunk_uuid"] = str(uuid.uuid4())

        self.vectorstore.add_documents(chunks)
        return len(chunks)

    def remove_document(self, doc_id):
        col = self.chroma_client.get_collection(self.collection_name)
        col.delete(where={"doc_id": str(doc_id)})

    def clear(self):
        col = self.chroma_client.get_collection(self.collection_name)
        all_ids = col.get(include=[]).get("ids", [])
        if all_ids:
            col.delete(ids=all_ids)

    def get_raw_collection(self):
        return self.chroma_client.get_collection(self.collection_name)

    # ---------- 检索 ----------
    def search(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """检索知识库。

        `RAG_SCORE_THRESHOLD > 0` 时按余弦相似度过滤掉低质量片段
        (改造前是「无阈值、无 rerank」,实测会把教材代码片段当理财建议返回)。
        默认 0 = 不过滤,与改造前行为完全一致。
        """
        k = top_k or settings.RAG_TOP_K
        threshold = settings.RAG_SCORE_THRESHOLD

        if threshold and threshold > 0:
            pairs = self.vectorstore.similarity_search_with_relevance_scores(query, k=k)
            return [doc.page_content for doc, score in pairs if score >= threshold]

        return [doc.page_content for doc in self.vectorstore.similarity_search(query, k=k)]

    def build_context_string(self, query: str, top_k: Optional[int] = None) -> str:
        chunks = self.search(query, top_k=top_k)
        return "\n\n".join(f"[参考]\n{chunk}" for chunk in chunks)


def _load_static_kb(engine: RAGEngine, existing_doc_ids: set) -> tuple:
    """启动时把 knowledge_base/*.md 加载进向量库(已存在则跳过,保留 web 编辑后的内容)"""
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")
    if not os.path.isdir(kb_dir):
        return 0, 0
    loaded = skipped = 0
    for filename in os.listdir(kb_dir):
        if not filename.endswith(".md"):
            continue
        doc_id = f"static_{filename}"
        if doc_id in existing_doc_ids:
            skipped += 1
            print(f"  [static KB] {filename}: 跳过(已存在)")
            continue
        try:
            n = engine.add_document(file_path=os.path.join(kb_dir, filename),
                                    doc_id=doc_id, filename=filename)
            loaded += 1
            print(f"  [static KB] {filename}: {n} chunks")
        except Exception as e:
            print(f"  [static KB] {filename} failed: {e}")
    return loaded, skipped


def init_rag_engine() -> RAGEngine:
    """初始化 RAG 引擎(线程安全 + 幂等)"""
    global _rag_engine
    with _init_lock:
        if _rag_engine is not None:
            return _rag_engine

        t0 = time.time()
        engine = RAGEngine()

        existing_doc_ids = {d["doc_id"] for d in engine.list_documents()}
        print(f"[RAG] 已有 {len(existing_doc_ids)} 个向量文档,扫描静态 KB...", flush=True)
        loaded, skipped = _load_static_kb(engine, existing_doc_ids)
        print(f"[RAG] 静态知识库扫描完成,新增 {loaded} 份,跳过 {skipped} 份", flush=True)

        _rag_engine = engine
        print(f"[RAG] 引擎就绪({time.time() - t0:.2f}s),持久化路径: {engine.persist_dir}",
              flush=True)
        return engine


def get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        init_rag_engine()
    return _rag_engine


# 向后兼容(原 API)
def search_knowledge(query: str, top_k: int = 3) -> list:
    return get_rag_engine().search(query, top_k=top_k)


def build_context_string(query: str, top_k: int = 3) -> str:
    return get_rag_engine().build_context_string(query, top_k=top_k)
