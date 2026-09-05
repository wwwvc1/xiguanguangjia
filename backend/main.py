from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from routers import auth, todos, goals, transactions, meals, reminders, admin, ai_professional, ai_general, ai_generate, ai_agent, user_settings, user_profile, export, achievements, stats, reports, checkins
from routers import admin_auth, admin_llm_models, user_llm_models, admin_knowledge, admin_logs, admin_achievements, admin_dashboard
# 导入工具
from config import settings
from database import init_db_pool, close_db_pool
from utils.auth import create_access_token
from utils.deps import get_current_user
from utils.exceptions import validation_exception_handler, global_exception_handler

# ============================================================
# Lifespan:启动时建 DB 连接池,关闭时释放
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    print("[DB] 连接池已初始化 (min=2, max=10)")
    yield
    await close_db_pool()
    print("[DB] 连接池已关闭")

# 创建应用
app = FastAPI(
    title="习惯管家 API",
    lifespan=lifespan,
    redirect_slashes=False,  # /api/todos 不再自动 307 到 /api/todos/,路径必须精确匹配
)

# CORS 中间件（让小程序能跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(meals.router)
app.include_router(admin.router)
app.include_router(reminders.router)
app.include_router(transactions.router)

app.add_exception_handler(Exception, global_exception_handler)
app.include_router(goals.router)
app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(ai_professional.router)
app.include_router(ai_general.router)
app.include_router(ai_generate.router)
app.include_router(ai_agent.router)
app.include_router(user_settings.router)
app.include_router(user_profile.router)
app.include_router(export.router)
app.include_router(achievements.router)
app.include_router(checkins.router)
app.include_router(stats.router)
app.include_router(stats.insights_router)
app.include_router(reports.router)
app.include_router(admin_auth.router)
app.include_router(admin_llm_models.router)
app.include_router(user_llm_models.router)
app.include_router(admin_knowledge.router)
app.include_router(admin_logs.router)
app.include_router(admin_achievements.router)
app.include_router(admin_dashboard.router)



@app.on_event("startup")
def startup_event():
    """应用启动时初始化 RAG 引擎 + 调度器(同步部分放这里,lifespan 负责连接池)"""
    from utils.ai_rag import init_rag_engine
    init_rag_engine()
    # 启动定时任务(周报月报),失败不影响主服务
    try:
        from utils.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[Scheduler] 启动失败(非致命): {e}")

# --- 健康检查(同步,探针/K8s liveness 用,不依赖 DB) ---
@app.get("/health")
def health():
    return {"status": "ok"}
# --- 测试端点 ---
@app.get("/ai/test-rag")
def test_rag(query: str):
    """测试 RAG 检索"""
    from utils.ai_rag import search_knowledge
    results = search_knowledge(query, top_k=2)
    return {"query": query, "results": results}
@app.get("/")
def read_root():
    return {"message": "Hello from 习惯管家!"}

@app.get("/db-test")
def test_db():
    """测试数据库连接"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT NOW() AS now")
            return {"database_time": cursor.fetchone()["now"]}
    finally:
        conn.close()

@app.get("/auth-test")
def auth_test(current_user: int = Depends(get_current_user)):
    """测试 JWT 鉴权"""
    return {"user_id": current_user, "message": "鉴权成功！"}