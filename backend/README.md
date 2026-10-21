# 习惯管家 · 后端

FastAPI + MySQL + Redis(可选)+ LangChain + ChromaDB。
为微信小程序「习惯管家」和运营管理后台提供 API 与 AI 服务。

| 项 | 版本 |
|---|---|
| Python | 3.13 |
| FastAPI | 0.141 |
| MySQL | 5.7+ / 8.0 |
| Redis | 可选,5.0+ 即可(未装/连不上时自动降级) |
| LangChain | 1.3(langchain-openai 1.5) |

---

## 快速开始

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 复制配置模板,填数据库口令和 LLM key
copy .env.example .env

# 首次:建库 + 补性能索引 —— 完整顺序见下方「数据库」一节
#   schema.sql -> 各 add_*.sql -> run_migration.py -> apply_perf_indexes.py
.\.venv\Scripts\python.exe run_migration.py
.\.venv\Scripts\python.exe scripts\apply_perf_indexes.py

# 启动(自动清僵尸进程、监听 0.0.0.0、打印局域网 IP)
.\scripts\start_backend.ps1

# 或者手动启
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

验证:

```powershell
curl.exe http://127.0.0.1:8000/health        # -> {"status":"ok"}
curl.exe http://127.0.0.1:8000/health/full   # -> 带 DB / Redis 状态
# 交互式文档: http://127.0.0.1:8000/docs
```

启动日志应包含这四行:

```
DB 异步连接池已就绪 (min=2, max=20)
DB 同步连接池已就绪 (min=2, max=12)
Redis 后端: mini (127.0.0.1:6379/0)
Application startup complete.
```

> Redis 没启动也不影响 —— 日志打「Redis 不可用,缓存层降级」,应用照常运行。

---

## 目录结构

```
backend/
├── main.py               # 应用装配:lifespan、中间件、路由注册
├── config.py             # <- core/config.py 的兼容 shim
├── database.py           # <- core/database.py 的兼容 shim
│
├── core/                 # 基础设施(不依赖业务)
│   ├── config.py         #   统一配置(路径与 CWD 解耦)
│   ├── database.py       #   异步池(aiomysql)+ 同步池(pymysql)
│   ├── redis_client.py   #   缓存客户端 + 熔断 + 双后端选择
│   ├── mini_redis.py     #   纯标准库 RESP2 客户端(装不上 redis 包时用)
│   └── cache.py          #   缓存版本号原语
│
├── repositories/         # 数据访问层 —— 只有这一层写 SQL
│   ├── base.py           #   行归一化等公共工具
│   ├── todo_repo.py  transaction_repo.py  checkin_repo.py
│   ├── achievement_repo.py  meal_repo.py  misc_repo.py  llm_repo.py
│
├── services/             # 业务编排层
│   ├── dashboard_service.py      #  首页聚合(1 次请求替代 7 个)
│   ├── stats_service.py          #  习惯洞察 / 关联分析
│   ├── achievement_service.py    #  成就评估(增量 + 缓存)
│   ├── checkin_service.py        #  打卡 + streak 唯一实现
│   ├── chat_session_service.py   #  AI 对话上下文(Redis)
│   └── cache_invalidation.py     #  AI 工具写库后的缓存失效
│
├── agent/                # AI 层(LangChain)
│   ├── chat_model.py     #   ChatOpenAI 工厂 + LLM_BACKEND 开关
│   ├── core.py           #   ★ 唯一的工具调用循环
│   └── executor.py       #   /api/ai/chat/professional 的封装
│
├── routers/              # Controller:HTTP 契约 + 参数校验
├── models/               # Pydantic schema
├── utils/                # 工具(工具注册表、RAG、日志、鉴权…)
├── scripts/              # 运维 / 诊断 / 回归脚本
├── sql/                  # 建表与迁移 SQL
├── tests/                # pytest 用例(需自行装 pytest + pytest-asyncio)
└── knowledge_base/       # RAG 业务规则 markdown
```

---

## 分层约定(改代码前先看这段)

| 要加的东西 | 放哪 |
|---|---|
| 一条新 SQL | repositories/,加一个函数,不要在 router 里拼 |
| 跨表业务逻辑 | services/ |
| 一个新接口 | routers/,只做参数校验和调 service |
| 背景任务 / 缓存失效 | 同上,并记得 cache.abump |
| 基础设施(池、缓存、配置) | core/ |

旧代码里的 `from config import settings` / `from database import get_connection` **不用改**,
这两个文件是 core/ 的 shim,只做 re-export。

---

## 配置

全部配置项见 `.env.example`。常用的几个:

| 变量 | 默认 | 说明 |
|---|---|---|
| DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME | localhost:3306 root | MySQL |
| SECRET_KEY | 必改 | JWT 签名密钥 |
| OPENAI_BASE_URL / OPENAI_API_KEY / CHAT_MODEL | — | LLM 兜底配置 |
| LLM_BACKEND | langchain | 改 openai 可回滚到改造前的裸 SDK 实现 |
| REDIS_ENABLED | true | 设 false 整体关闭缓存 |
| RAG_PRELOAD | 1 | 设 0 关闭启动时的向量模型预热 |

> **注意**:模型优先取自数据库 `llm_models` 表(`is_system_default=1`),**不是** `.env`。
> 改了 `.env` 不生效时,跑 `python scripts/which_model.py <user_id>` 确认实际用的是哪个。

---

## 关键设计(都是踩过坑之后定下的)

### 1. 双连接池:异步为主,同步兜底

新代码走 `async with get_conn()`(aiomysql 池);尚未迁移的老模块走 `get_connection()`,
现在也已改成从池里借,不再是每次请求新建 TCP 连接。

### 2. 池是 autocommit=True —— 别改回去

MySQL 默认 REPEATABLE READ 在**首条 SELECT** 建快照。池化连接如果只读不提交,
会永久停在旧快照上,读不到别的连接刚插入的行 ——
表现为「INSERT 成功,紧接着 SELECT 返回 None」,即 `POST /todos` 间歇性 500。

需要多语句原子性时用 `async with transaction()`,它内部会 `begin()`。

### 3. 缓存失效用版本号,不用 DEL

写操作 `cache.abump(uid, "todo")` 自增计数器;读时比对缓存里的版本快照,对不上就当未命中。

**新增缓存时不需要写任何 DEL 逻辑** —— 这是刻意设计,精确 DEL 你必然会漏一个。

### 4. 只有一个 Agent 循环

`agent/core.py` 的 `ToolCallingAgent` 被两个端点共用,差异全是构造参数:

| 端点 | 工具 | 轮数 | 二次确认 | 输出 |
|---|---|---|---|---|
| /api/ai/chat/professional | 25 | 5 | 否 | SSE |
| /api/ai/agent(ai-create 页) | 18 | 3 | 是 | JSON |

`astream()` 出事件流,`aloop()` 出结构化结果,循环本体只有一份。
**不要再写第三套。** 回归:`python scripts/test_agent_core.py`(31 条,用 FakeLLM,不耗额度)。

### 5. Redis 是可选的加速层

`socket_timeout` 0.2s + 熔断(连续失败 5 次短路 15s)+ 全链路降级。
官方 `redis` 包装不上时自动回退到 `core/mini_redis.py`(纯标准库 RESP2 实现),
两者方法签名一致,上层无感。启动日志会打印当前后端是 `redis-py` 还是 `mini`。

### 6. RAG 的离线启动

`HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` 必须在**任何** langchain / transformers 导入之前设置
(huggingface_hub 在 import 时就固化常量,晚设置无效 → 断网时启动卡 20s+)。
现在写在 `main.py` 第一行和 `utils/ai_rag.py` 顶部。
向量模型在 lifespan 里用后台线程预热,端口先可用。

---

## 主要 API

| 分组 | 端点 |
|---|---|
| 鉴权 | POST /api/auth/register、/api/auth/login、/api/auth/login-with-password |
| 首页 | **GET /api/dashboard**(一次拿全,优先用这个) |
| 待办 | GET/POST /api/todos、PUT/DELETE /api/todos/{id}、POST /api/todos/batch |
| 目标 / 收支 / 饮食 / 提醒 | /api/goals、/api/transactions、/api/meals、/api/reminders |
| 打卡 | POST /api/checkins、GET /api/checkins/streak、/api/checkins/today |
| 成就 | GET /api/achievements、/api/achievements/available |
| 洞察 | GET /api/stats/patterns、/api/stats/correlation、POST /api/ai/insights |
| AI | POST /api/ai/chat/general、/api/ai/chat/professional、/api/ai/agent |
| 模型 | GET /api/llm/models/available、POST /api/llm/models/user |
| 设置 / 资料 / 导出 | /api/user/settings、/api/user/profile、/api/export |
| 管理端 | /api/admin/** |

路径尾斜杠会被 `normalize_api_trailing_slash` 中间件归一化 ——
`/api/todos` 和 `/api/todos/` 命中同一路由(小程序跟随 307 会丢 Authorization 头)。

---

## 脚本

| 脚本 | 用途 |
|---|---|
| `start_backend.ps1` | 启动器:清僵尸进程 → 起 uvicorn → 轮询 /health → 打印局域网 IP |
| `apply_perf_indexes.py` | **部署必跑**,幂等加性能索引,`--explain` 看执行计划 |
| `test_agent_core.py` | Agent 循环单测(31 条,不需要 LLM) |
| `smoke_api.py` | 端到端冒烟(38 条:首页聚合 / 缓存失效 / CRUD / 打卡 / 洞察 / 成就 / 收支) |
| `smoke_misc.py` | 其余路由回归(10 条) |
| `smoke_ai_cache.py` | AI 工具写库后缓存是否立即失效(7 条) |
| `smoke_ai.py` | AI 链路契约(11 条,会真实调 LLM,可能 429) |
| `which_model.py` | 我到底在用哪个模型?为什么 `.env` 没生效? |
| `test_all_models.py` | 逐个测 llm_models 里所有模型的连通性 |
| `bench_queries.py` | 索引 / 查询改写基准(合成数据,跑完自动清理) |
| `inspect_indexes.py` | 查看现有索引与行数 |
| `redis_doctor.py` | Redis 体检:版本 / 内存 / 淘汰策略 / 命中率 |
| `redis_compat_check.py` | 换 Redis 版本时验证命令兼容性 |
| `create_admin.py` | 创建管理员账号 |
| `export_openapi.py` | 导出 OpenAPI JSON |
| `jmeter/setup_data.py` | 压测前造测试用户和 token |

---

## 数据库

> ⚠️ **没有一键初始化脚本**。`sql/` 是历次增量迁移的堆叠,新环境要按下面顺序执行。

### 从零建库

```powershell
# 1. 基础表(users / todos / goals / transactions / meals / reminders / 角色 / token 黑名单)
mysql -u root -p habit_tracker < sql/schema.sql

# 2. 增量表与字段(顺序按依赖)
mysql -u root -p habit_tracker < sql/create_checkins.sql
mysql -u root -p habit_tracker < sql/add_user_settings.sql
mysql -u root -p habit_tracker < sql/add_achievements.sql
mysql -u root -p habit_tracker < sql/achievement_definitions.sql
mysql -u root -p habit_tracker < sql/add_reports.sql
mysql -u root -p habit_tracker < sql/add_todos_due_date.sql
mysql -u root -p habit_tracker < sql/alter_user_avatar.sql

# 3. phase3(含 DELIMITER 存储过程,必须用脚本跑)
.\.venv\Scripts\python.exe run_migration.py

# 4. 性能索引(幂等,可反复跑)
.\.venv\Scripts\python.exe scripts\apply_perf_indexes.py
```

`sql/checkins_add_auto.sql` 已被 `create_checkins.sql` 取代(它用的
`ADD COLUMN IF NOT EXISTS` 是 MariaDB 语法,MySQL 8 不支持)。

### 性能索引

`scripts/apply_perf_indexes.py` 会补这些(幂等):

| 表 | 索引 | 服务的查询 |
|---|---|---|
| todos | (user_id, done, due_date) | 首页 / 待办页按天过滤 |
| todos | (user_id, done, created_at) | 无日期过滤时的排序 |
| transactions | (user_id, time) | 日报 / 月报 / 60 天范围扫描 |
| transactions | (user_id, type, time) | 支出按天聚合 |
| goals | (user_id, done) | 成就 metric |
| reminders | (user_id, enabled, time) | 成就 metric |

实测(3 万行合成数据,`scripts/bench_queries.py`):

| 场景 | 加索引前 | 加索引后 |
|---|---|---|
| todos 按天过滤 | 47.42 ms | 0.46 ms |
| transactions 按月聚合 | 108.74 ms | 9.58 ms |

---

## 测试

当前环境未安装 pytest / pytest-asyncio,所以用 `scripts/` 下的冒烟脚本,合计 **86 条断言**:

```powershell
# 需要后端已在运行
.\.venv\Scripts\python.exe scripts\smoke_api.py
.\.venv\Scripts\python.exe scripts\smoke_misc.py
.\.venv\Scripts\python.exe scripts\smoke_ai_cache.py

# 不需要后端(纯单测)
.\.venv\Scripts\python.exe scripts\test_agent_core.py
```

冒烟脚本默认连 `127.0.0.1:18001`,改脚本顶部的 `BASE` 即可。

---

## 已知限制

- **AI 接口没有限流 / 配额**。`user_quotas` 表存在但用户侧接口未扣减,
  上游 rpm 很低时容易 429。
- **RAG 检索质量待优化**:当前 embedding 是英文模型 `all-MiniLM-L6-v2` 跑中文,
  且知识库里混有与业务无关的教材内容(`doc_id=4` 的 72 条)。
  建议换 `BAAI/bge-small-zh-v1.5` + 清理知识库 + 设 `RAG_SCORE_THRESHOLD`。
- **`APScheduler` 未安装**,周报 / 月报定时任务会静默跳过。
- **`admin.py` 仍是同步实现**(17 个路由,低频,已享受同步连接池收益)。
- **`utils/achievement_engine.py`** 是旧成就引擎,`admin.py` / `goals.py` 仍有调用,
  新代码请用 `services/achievement_service.py`。
