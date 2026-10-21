"""统一配置

设计要点:
1. **路径与 CWD 解耦**:所有相对路径都基于 backend/ 目录解析,
   这样从仓库根目录、从 backend/ 或从测试目录启动,行为一致。
2. **新增配置全部有安全默认值**:不配置也能跑起来(Redis 会自动降级)。
3. 保留 .env 支持;新增项请在 .env.example 里补一行。
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录(本文件在 backend/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",          # .env 里有多余变量不要炸
        case_sensitive=True,
    )

    # ---------------- 数据库 ----------------
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "habit_tracker"

    # 异步池(aiomysql)
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 20
    # 同步池(pymysql)—— 给还没迁完 async 的旧模块兜底,避免每次请求新建连接
    DB_SYNC_POOL_MIN: int = 2
    DB_SYNC_POOL_MAX: int = 12

    # ---------------- JWT ----------------
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ---------------- LLM ----------------
    OPENAI_API_KEY: str = "sk-your-openai-api-key"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    CHAT_MODEL: str = "gpt-4o-mini"
    # langchain | openai —— 一条环境变量回滚调用层
    LLM_BACKEND: str = "langchain"

    # ---------------- Redis ----------------
    REDIS_ENABLED: bool = True
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_PREFIX: str = "hb"
    REDIS_MAX_CONNECTIONS: int = 32
    # 必须短:Redis 一旦卡住,不能让每个请求都白等
    REDIS_SOCKET_TIMEOUT: float = 0.2
    REDIS_CONNECT_TIMEOUT: float = 0.2
    # 连续失败 N 次后熔断 M 秒,期间所有缓存调用直接短路
    REDIS_FAILURE_THRESHOLD: int = 5
    REDIS_CIRCUIT_COOLDOWN: float = 15.0

    # ---------------- 缓存 TTL(秒) ----------------
    CACHE_TTL_DASHBOARD: int = 60
    CACHE_TTL_STATS: int = 300
    CACHE_TTL_ACHIEVEMENTS: int = 600
    CACHE_TTL_METRIC: int = 300
    CACHE_TTL_INSIGHTS: int = 1800
    CACHE_TTL_LLM_MODELS: int = 600

    # ---------------- RAG / 向量库 ----------------
    CHROMA_DB_PATH: str = "./chroma_db"
    RAG_COLLECTION: str = "habit_knowledge"
    EMBED_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBED_LOCAL_DIR: str = ""
    RAG_TOP_K: int = 3
    RAG_SCORE_THRESHOLD: float = 0.0   # 0 = 不过滤(保持现有行为)

    # ---------------- 观测 ----------------
    SLOW_REQUEST_MS: int = 800
    LOG_LEVEL: str = "INFO"

    # ---------------- 派生路径(只读) ----------------
    @property
    def chroma_dir(self) -> str:
        p = Path(self.CHROMA_DB_PATH)
        return str(p if p.is_absolute() else (BACKEND_DIR / p))

    @property
    def embed_local_dir(self) -> str:
        if not self.EMBED_LOCAL_DIR:
            return ""
        p = Path(self.EMBED_LOCAL_DIR)
        return str(p if p.is_absolute() else (BACKEND_DIR / p))

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()

# 让 HF 离线开关对所有入口生效(必须在 transformers 导入前)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
