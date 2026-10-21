import os

# ⚠️ 必须放在一切 import 之前:huggingface_hub / transformers 在 import 时
# 就把 HF_HUB_OFFLINE 之类的开关读成常量,晚设置等于没设置(会导致
# RAG 启动时联网解析模型、断网后反复超时重试,启动卡几十秒)。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import (
    close_db_pool, close_sync_pool, init_db_pool, init_sync_pool,
)
from core import redis_client as redis_client
from utils.deps import get_current_user
from utils.exceptions import global_exception_handler, validation_exception_handler

# 路由
from routers import (
    achievements, admin, admin_achievements, admin_auth, admin_dashboard,
    admin_insights, admin_knowledge, admin_llm_models, admin_logs, ai_agent,
    ai_generate, ai_general, ai_professional, auth, checkins,
    dashboard, export, goals, meals, reminders, reports, stats, todos,
    transactions, user_llm_models, user_profile, user_settings,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("app")


def _warmup_rag():
    """后台线程预热 RAG:模型 + 向量库加载是纯本地 IO/计算,不该阻塞端口。"""
    try:
        from utils.ai_rag import init_rag_engine
        init_rag_engine()
    except Exception as e:
        print(f"[RAG] 初始化失败(非致命): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) 数据库:异步池为主 + 同步池兜底未迁移模块
    await init_db_pool()
    log.info("DB 异步连接池已就绪 (min=%s, max=%s)", settings.DB_POOL_MIN, settings.DB_POOL_MAX)
    try:
        init_sync_pool(warmup=True)
        log.info("DB 同步连接池已就绪 (min=%s, max=%s)",
                 settings.DB_SYNC_POOL_MIN, settings.DB_SYNC_POOL_MAX)
    except Exception as e:
        log.warning("同步连接池初始化失败(未迁移模块会变慢): %s", e)

    # 2) Redis:失败不阻塞启动,缓存层自动降级
    redis_client.init_redis()

    # 3) RAG 后台预热
    if os.environ.get("RAG_PRELOAD", "1") != "0":
        asyncio.get_running_loop().run_in_executor(None, _warmup_rag)

    # 4) 定时任务
    try:
        from utils.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        log.warning("Scheduler 启动失败(非致命): %s", e)

    yield

    try:
        from utils.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    await redis_client.close_redis()
    await close_db_pool()
    close_sync_pool()
    log.info("资源已释放")


app = FastAPI(title="习惯管家 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


# ============================================================
# 观测中间件:慢请求打日志
# 没有基线就无法证明"性能提升了",所以这一步不能省。
# ============================================================
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    if elapsed_ms >= settings.SLOW_REQUEST_MS:
        log.warning("慢请求 %s %s -> %s (%.0fms)",
                    request.method, request.url.path, response.status_code, elapsed_ms)
    return response


# ============================================================
# 路径尾斜杠归一化(消掉 307)
# 路由表里很多根路径写成 "/"(如 /api/todos/、/api/meals/)。
# 客户端少写斜杠时 FastAPI 默认回 307,小程序跟随重定向会丢掉
# Authorization 头 → 一堆假 401。这里在应用内部改写路径。
# ============================================================
_known_paths: set[str] = set()
_known_paths_ready = False


def _collect_route_paths(routes, out: set[str]) -> None:
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            out.add(path)
        sub_routes = getattr(route, "routes", None)
        if sub_routes:
            _collect_route_paths(sub_routes, out)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            _collect_route_paths(getattr(inner, "routes", []), out)


def _get_known_paths(app_: FastAPI) -> set[str]:
    global _known_paths, _known_paths_ready
    if not _known_paths_ready:
        _known_paths = set()
        _collect_route_paths(app_.routes, _known_paths)
        _known_paths_ready = True
    return _known_paths


@app.middleware("http")
async def normalize_api_trailing_slash(request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/api") and len(path) > 1:
        known = _get_known_paths(request.app)
        if path not in known:
            alt = path[:-1] if path.endswith("/") else path + "/"
            if alt in known:
                request.scope["path"] = alt
                raw_path = request.scope.get("raw_path")
                if isinstance(raw_path, (bytes, bytearray)):
                    request.scope["raw_path"] = alt.encode()
    return await call_next(request)


# ============================================================
# 路由注册
# ============================================================
app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(goals.router)
app.include_router(transactions.router)
app.include_router(meals.router)
app.include_router(reminders.router)
app.include_router(user_settings.router)
app.include_router(user_profile.router)
app.include_router(checkins.router)
app.include_router(achievements.router)
app.include_router(stats.router)
app.include_router(stats.insights_router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(export.router)

app.include_router(ai_professional.router)
app.include_router(ai_general.router)
app.include_router(ai_generate.router)
app.include_router(ai_agent.router)

app.include_router(admin.router)
app.include_router(admin_auth.router)
app.include_router(admin_llm_models.router)
app.include_router(user_llm_models.router)
app.include_router(admin_knowledge.router)
app.include_router(admin_logs.router)
app.include_router(admin_achievements.router)
app.include_router(admin_insights.router)
app.include_router(admin_dashboard.router)


# ============================================================
# 健康检查 / 调试端点
# ============================================================
@app.get("/health")
async def health():
    """探针用:快速返回,不依赖 DB / Redis"""
    return {"status": "ok"}


@app.get("/health/full")
async def health_full():
    """运维用:带上各依赖状态"""
    from core.database import get_pool
    db_ok = True
    db_error = None
    try:
        from core.database import fetch_value
        await fetch_value("SELECT 1")
    except Exception as e:
        db_ok = False
        db_error = str(e)

    pool = None
    try:
        pool = get_pool()
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": {
            "ok": db_ok,
            "error": db_error,
            "async_pool_size": getattr(pool, "size", None),
            "async_pool_free": getattr(pool, "freesize", None),
        },
        "redis": redis_client.status(),
        "llm_backend": settings.LLM_BACKEND,
    }


@app.get("/")
async def read_root():
    return {"message": "Hello from 习惯管家!"}


@app.get("/db-test")
async def test_db():
    """测试数据库连接(原来用的是未 import 的 get_connection,一调就 NameError)"""
    from core.database import fetch_one
    row = await fetch_one("SELECT NOW() AS now")
    return {"database_time": str(row["now"]) if row else None}


@app.get("/auth-test")
async def auth_test(current_user: int = Depends(get_current_user)):
    return {"user_id": current_user, "message": "鉴权成功！"}


@app.get("/ai/test-rag")
async def test_rag(query: str):
    """测试 RAG 检索"""
    from utils.ai_rag import search_knowledge
    results = await asyncio.to_thread(search_knowledge, query, 2)
    return {"query": query, "results": results}
