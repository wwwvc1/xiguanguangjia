"""基础设施层(core)

分三层:
- config     统一配置(含 Redis / LLM_BACKEND / RAG)
- database   异步连接池 + 同步连接池(两套并存,逐步收拢)
- redis_client / cache  Redis 缓存 + 版本号失效

为什么有 core/ 而不复用 backend/config.py:
根目录的 config.py / database.py / utils/auth.py 等保留为**兼容 shim**,
只做 re-export,已有 30+ 个 import 不需要改一行就能继续工作。
新代码一律从 core.* 引入。
"""
