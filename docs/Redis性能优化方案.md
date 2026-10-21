# 习惯管家 · 后端性能优化 + Redis 融入方案

> 基于对 `backend/` 全量源码(84 个 .py,不含 .venv)的静态审查得出。
> 本文先给「现状体检」,再给「Redis 分层方案」,最后给「分阶段落地」和「待你决策的问题」。
> 所有优化点都标注了对应的代码位置,可直接跳过去核对。

---

## 一、现状体检:性能瓶颈在哪里

### 1.1 最大的问题不是"没有 Redis",而是"架构是半同步的"

项目是两套 DB 访问方式并存的:

| 访问方式 | 用到的模块 | 特征 |
|---|---|---|
| **异步**(aiomysql 池) | `todos` `goals` `transactions` `meals` `checkins` `reminders` `user_settings` | 复用池,min=2/max=10,正确 |
| **同步**(pymysql **每次新建连接**) | `stats` `achievements` `reports` `export` `admin\*` `ai\*` `achievement_engine` `report_generator` `scheduler` | `get_sync_connection()` = 一次完整 TCP 握手 + MySQL 认证 |

关键代码:`backend/database.py:47-57`

```python
def get_sync_connection():
    """同步连接 — 仅用于初始化脚本(不通过 pool)"""
    return pymysql.connect(...)   # ← 注释说"仅用于脚本",实际有 25 处在请求热路径调用
```

**后果两层:**

1. 每个请求多付一次建连成本(本地约 1–5ms,远程/云 DB 会更痛);
2. FastAPI 里 `def`(非 `async def`)路由跑在 anyio 线程池里,默认容量 40 线程。DB 一慢,线程池打满,**连异步路由也跟着排队**。

> 统计:`ai_tool_executor.py` 25 处、`ai_crud_tools.py` 18 处、`admin.py` 16 处调用 `get_connection()`。

### 1.2 成就引擎是最热的"放大器"

这是我认为**投入产出比最高**的一处。

`backend/utils/achievement_engine.py:162` 的 `check_and_unlock()`:

```python
for d in defs:                                   # 遍历所有 is_active 定义
    if _already_unlocked(cur, user_id, d["code"]):  # 每人每条 1 次 SQL
        continue
    current = _eval_metric(cur, user_id, d["metric_type"])  # 每人每条 1+ 次 SQL
```

而 `_eval_metric` 的很多分支是**全表按 user_id 的 COUNT/SUM**:

```python
if metric_type == "todo_count":
    cursor.execute("SELECT COUNT(*) AS c FROM todos WHERE user_id = %s", ...)
if metric_type == "tx_expense_total":
    cursor.execute("SELECT COALESCE(SUM(ABS(amount)),0) ... FROM transactions ...")
```

**触发频率才是要命的**:用户每勾一个待办,前端 `toggleTodo` → `PUT /api/todos/{id}` → 就触发一次完整评估。

- `backend/routers/todos.py:142-148`(更新)
- `backend/routers/todos.py:65-73`(创建)
- `backend/routers/checkins.py:118`(打卡)
- `backend/routers/achievements.py:29`(手动)

按 20 条成就定义估算:一次勾选 ≈ **40+ 条 SQL + 1 次新建连接**,而用户只想要一个"勾上了"的响应。

`list_available()`(`achievement_engine.py:221`)更夸张:内部依次打开 **3 个连接**(`list_unlocked` / `list_definitions` / 自己),再对每条定义跑 `_eval_metric`。

### 1.3 首页一次 onShow 打 7 个请求

`前端/最终稿敲定/pages/index/index.js:130-137`:

```js
await Promise.all([
  app.request({ url: `/todos?done=false&date=${dateStr}` }),
  app.request({ url: `/todos?done=true&date=${dateStr}` }),
  app.request({ url: `/transactions/daily-stats?date=${dateStr}` }),
  app.request({ url: '/checkins/streak' }),
  app.request({ url: '/meals' }),
  app.request({ url: '/user/settings' })
]);
```

外加 `maybeAutoCheckin()` 的 `POST /checkins`(`index.js:95`)。**7 次 JWT 校验 + 7 次 SQL 往返**,只为了渲染一张首页。第 1、2 个请求其实是同一个表可以一次查完的。

### 1.4 `/checkins/streak` 走的是同步连接

`backend/routers/checkins.py:181` 本身是 async + 池,但 `do_checkin` 里的 `_calc_streak`(`:33`)用的是 `get_sync_connection()`,还套了一层 `run_in_executor`:

```python
streak = await asyncio.get_event_loop().run_in_executor(None, _calc_streak, current_user)
```

同一份 streak 逻辑在 `stats.py:112-133` 又抄了一遍。

### 1.5 AI 会话状态存在进程内存里

`backend/routers/ai_general.py:13`:

```python
_chat_history: dict[str, list[dict]] = {}
```

- 重启进程 → 上下文全丢;
- 起 2 个 worker → 用户忽冷忽热;
- 且这个 dict **永不清理**,长期运行会内存泄漏。

### 1.6 配额表存在,但用户侧 AI 接口根本没扣减

`user_quotas` 表只在 `admin.py` 里读/写(`:506`、`:513`)。`/api/ai/*` 的真实调用路径上**没有任何限流**。LLM 成本完全裸奔,上游 429 只能事后感知(`ai_general.py:74`)。

### 1.7 索引缺口(按真实 SQL 反推)

| 表 | 现有索引 | 实际查询 | 缺什么 |
|---|---|---|---|
| `transactions` | `idx_user_id`、`idx_user_type` | `WHERE user_id=? AND time >= ?`、`DATE(time)`、`YEAR(time)/MONTH(time)` | 缺 **`(user_id, time)`** |
| `todos` | `idx_user_id`、`idx_due_date` | `WHERE user_id=? AND done=? AND (due_date=? OR due_date IS NULL)` | 缺 **`(user_id, done, due_date)`**;且 `OR ... IS NULL` 会让索引失效 |
| `checkins` | 建表脚本里**没找到 DDL**(只有 `checkins_add_auto.sql` 加列) | `WHERE user_id=? AND checkin_date=?` | 缺 **(user_id, checkin_date) 唯一索引**(同时天然保证打卡幂等) |
| `meals` | `idx_user_date` ✅ | `GROUP BY date` | 够用 |

`YEAR(time) = ? AND MONTH(time) = ?`(`transactions.py:26`)是典型的**函数包裹索引失效**,改成 `time >= ? AND time < ?` 即可走索引。

### 1.8 定时任务目前是坏的

`backend/uvicorn.out`:`[Scheduler] 启动失败(非致命): No module named 'apscheduler'`

即使装上,`scheduler.py:31` 也是**串行遍历所有用户 + 每人新建连接**,而且多 worker 部署时会**重复跑一遍**。

### 1.9 其他

- `transactions.py:31` 每个请求往 stdout `print` 完整 SQL 和参数,生产环境是纯损耗 + 泄敏。
- `main.py:104` `test_db()` 用了 `get_connection()` 但文件顶部没有 import —— 这是死代码/潜在 NameError。
- 项目**没有 `requirements.txt`**(README 里提到但文件不存在),依赖不可复现。

---

## 二、Redis 该怎么融(分层方案)

设计原则:**Redis 是加速层,不是正确性依赖**。任何 Redis 故障都必须降级到「直接查 MySQL」,而不是返回 500。

### 2.0 前置条件(Redis 不能替代这一层)

Redis 缓存的是 SQL 结果。如果 SQL 本身要跑 800ms,命中率再高也救不了缓存未命中和写后首读。所以:

1. 补齐 1.7 的索引;
2. 把 25 处 `get_connection()` 收拢到一个**同步连接池**(`DBUtils.PooledDB` 或 `mysql-connector` 的池),消灭"每次请求建连";
3. 中长期把这批同步路由逐步迁到 `async` + `aiomysql` 池。

这三件事不做,Redis 加进来只会让"缓存穿透那一刻"更痛。

### 2.1 基础设施层

新增 `backend/utils/redis_client.py`:

- **连接池**:`redis.ConnectionPool(max_connections=32, socket_timeout=0.2, socket_connect_timeout=0.2)`
  —— 超时必须设,否则 Redis 卡住会拖死整个请求。
- **同步客户端**(给现有 `def` 路由和 `achievement_engine` 用)+ 预留 **async 客户端**(`redis.asyncio`)给异步路由。
- **Key 命名空间**:`hb:{env}:{domain}:...`,方便 `SCAN` 清理和按环境隔离。
- **序列化**:JSON(`orjson` 可选)。`datetime`/`Decimal` 统一 `default=str`。
- **降级开关**:`REDIS_ENABLED` 环境变量;启动时做一次 `PING`,失败则整个缓存层自动变 no-op。
- **熔断**:连续 N 次超时 → 暂停缓存 M 秒,避免每个请求都白等 200ms。

`config.py` 增加:

```python
REDIS_HOST: str = "127.0.0.1"
REDIS_PORT: int = 6379
REDIS_DB: int = 0
REDIS_PASSWORD: str = ""
REDIS_ENABLED: bool = True
CACHE_TTL_DASHBOARD: int = 60
CACHE_TTL_STATS: int = 300
```

### 2.2 Key 设计表

| Key | 类型 | TTL | 用途 |
|---|---|---|---|
| `hb:{env}:dash:{uid}:{YYYY-MM-DD}` | JSON | 60s | 首页聚合数据(替代 6 个接口) |
| `hb:{env}:stats:patterns:{uid}` | JSON | 300s | `/stats/patterns` 全量结果 |
| `hb:{env}:stats:corr:{uid}` | JSON | 300s | `/stats/correlation` |
| `hb:{env}:achv:avail:{uid}` | JSON | 600s | `/achievements/available`(含进度) |
| `hb:{env}:achv:done:{uid}` | SET | — | 已解锁 code 集合,写时维护 |
| `hb:{env}:settings:{uid}` | JSON | — | `user_settings`(写时失效) |
| `hb:{env}:llm:models:{uid}` | JSON | 600s | 模型列表(管理端改了要失效) |
| `hb:{env}:streak:{uid}` | INT | 到次日 00:01 | 连续打卡天数 |
| `hb:{env}:metric:{uid}:{metric_type}` | INT | 300s | 成就 metric 单值缓存 |
| `hb:{env}:quota:{uid}:{YYYYMMDD}` | INT | 48h | 当日 AI 调用额度 |
| `hb:{env}:rl:{scope}:{uid}:{window}` | INT | 窗口长度 | 限流计数 |
| `hb:{env}:lock:{name}` | STR | 10–30s | 分布式锁 |
| `hb:{env}:chat:{uid}:{session}` | LIST | 24h | AI 对话上下文 |
| `hb:{env}:ver:{uid}:{domain}` | INT | — | **版本号**(见 2.3) |

### 2.3 缓存失效:用「版本号」而不是「删 Key」

这是我最推荐的一个设计选择。

传统做法是写入时精确 `DEL` 掉所有受影响的 key。问题是:**你永远会漏一个**。比如"改一条 transaction"要失效 `dash:*`、`stats:patterns`、`stats:corr`、`achv:avail`、`metric:tx_expense_total`……当初学者加新缓存时必然遗漏,于是脏数据线上飘。

**版本号方案**:

```
ver:{uid}:tx     ← 任何 transactions 写操作 +1
ver:{uid}:todo   ← 任何 todos 写操作 +1
ver:{uid}:checkin
ver:{uid}:settings
```

读的时候:

```python
ver = redis.incr_by_domain_snapshot(uid, "tx")   # 一次 MGET 拿多个域
cached = redis.get_json(f"dash:{uid}:{today}")
if cached and cached["_ver"]["tx"] == ver:
    return cached["data"]
# 否则回源 + 写回(带上当前 _ver)
```

**好处**:写操作只需 `INCR` 一个计数器,不需要知道有多少派生 key。**慢一点才有脏数据**,漏掉的概率归零。TTL 再兜一层底。

写入侧的埋点很轻,可以做成装饰器或 FastAPI 依赖,在 `todos.py` / `transactions.py` 的 6 个写端点各加一行。

### 2.4 读缓存:按冷热分层,不要一把梭

| 优先级 | 目标 | 理由 |
|---|---|---|
| **P0** | `/stats/patterns`、`/stats/correlation` | 5–8 条聚合 SQL、60 天范围扫描,结果对"秒级新鲜度"完全不敏感。TTL 300s 用户根本感知不到 |
| **P0** | `/achievements/available` | 当前是最慢的端点之一(3 连接 + N 次 COUNT)。可以缓存到 Redis,配合 2.5 的进度计数器 |
| **P1** | 首页 dashboard 聚合 | 见 2.6,先聚合再缓存 |
| **P1** | `user_settings`、`llm/models` 列表 | 几乎不变,纯读 |
| **P2** | AI 建议(`/ai/insights`) | 结果本身就贵(调 LLM),缓存 30–60 分钟收益巨大;注意它当前把 `patterns` 又算了一遍 |
| **不做** | 分页列表(`/todos`、`/transactions` 全量) | 失效粒度太碎,命中率低,还容易脏。这类靠索引 + 分页解决 |

### 2.5 成就引擎重构(重点)

把「每次写都全量评估」改成「**事件驱动的增量计数**」:

```
写 todo 完成  →  INCR metric:{uid}:done_todo   (或标记 dirty)
                →  只评估 metric_type = done_todo 的定义
                →  达成则 SADD achv:done:{uid} + INSERT
```

具体建议:

1. **metric 走 Redis 计数器**:`todo_count` `done_todo` `tx_count` `meal_count` 这类天然是累加量,写操作时 `INCR`,读时直接用。只在对不上时(首次/缓存丢失)回源 MySQL 重建。
   - `tx_income_total` / `tx_expense_total` 用 `INCRBYFLOAT`。
   - `consecutive_checkin` / `early_reminder` 这类非单调量保留 DB 查询,但缓存 300s。
2. **定义表(`achievement_definitions`)** 全进程缓存(改配置才失效),不要每次查。
3. **已解锁集合** `achv:done:{uid}` 用 Redis SET,替代 `_already_unlocked` 的逐条 SQL。
4. **不要把成就检查放在写请求的同步路径上**:响应先返回,成就检查丢到 `BackgroundTasks`(或 2.8 的队列)。前端已经有"解锁动画"的语义,`newly_unlocked` 可以改成下次拉取时带出来。

这一层的收益:**一次勾选从 40+ SQL 降到 1–2 次 Redis 操作**。

### 2.6 首页聚合端点(收益最直观)

新增 `GET /api/dashboard?date=YYYY-MM-DD`,后端一次性返回首页需要的全部字段:

```json
{ "todos": [...], "completed_count": 3, "completion_rate": 60,
  "income": 0, "expense": 35.5, "net": -35.5,
  "calories": 1200, "streak": 7, "settings": {...} }
```

好处:
- 7 个请求 → **1 个**;
- 7 次 JWT 校验 → 1 次;
- 服务端可以用 **1 条 SQL 的 UNION/子查询** 或 3 条 SQL 并发取,而不是 6 条独立往返;
- 整包塞 Redis,TTL 60s,配合 `ver` 校验。

前端改动很小 —— `loadDashboardData()` 里 6 个 `app.request` 换成一个,数据字段名保持不变即可。

### 2.7 限流 / 配额 / 幂等(Redis 的原生场景)

这些是 Redis **最"正宗"**的用法,不涉及缓存一致性,风险最低:

1. **AI 调用限流**:`INCR rl:ai:{uid}:{分钟}` + `EXPIRE`,超阈值返回 429。同时落实 `user_quotas` 的真实扣减 —— 现在这张表形同虚设。
2. **打卡幂等**:`SET lock:checkin:{uid}:{date} 1 NX EX 10`,或直接靠 `checkins(user_id, checkin_date)` 唯一索引 + `INSERT IGNORE`。**推荐先用唯一索引**,Redis 锁作为第二道。
3. **定时任务单实例**:`SET lock:scheduler:weekly 1 NX EX 3600`,避免多 worker 重复生成周报。
4. **报��生成防并发**:`POST /reports/generate` 连点两次会生成两份;`list_reports` 的"已存在"检查本身是竞态。

### 2.8 AI 会话上下文迁移

`_chat_history` dict → `hb:{env}:chat:{uid}:{session}`:

- 用 **LIST**:`RPUSH` 追加、`LTRIM -20 -1` 只留最近 10 轮、`EXPIRE 86400`;
- 或 **HASH + LIST 组合**(多条会话)。
- 收益:重启不丢上下文、多 worker 天然共享、自动过期不泄漏。

### 2.9 异步队列(可选,最后做)

`apscheduler` 没装、`_run_weekly` 串行逐用户 —— 用户量上来后这是定时炸弹。

两个层次:
- **低成本**:FastAPI `BackgroundTasks` 或 `threading` + 信号量(3 并发),先把串行改并发;
- **正式方案**:Redis LIST 当轻量队列 + 一个后台 worker 消费(`BRPOP`),或者干脆上 Celery/RQ。考虑到这是个人项目,**先用 LIST + 单 worker,别上 Celery**。

### 2.10 降级与观测(必须有)

- **降级**:所有 Redis 调用包 `try/except (RedisError, TimeoutError)` → 记一次日志 + 计入熔断,业务继续走 MySQL。
- **观测**:加一个 `@timed` 中间件,记录每个端点的 P50/P95 和缓存命中率(`keyspace_hits / (hits+misses)`)。**没有 baseline 就没法证明"性能提升了"**,这一步不能省。
- **慢日志**:MySQL `slow_query_log` + `long_query_time=0.3`。

---

## 三、分阶段落地(建议顺序)

### Phase 0 · 观测与基线(0.5 天)⭐ 必做
- [ ] 加耗时中间件,输出 `path / P50 / P95 / SQL 数`
- [ ] 打开 MySQL 慢查询日志
- [ ] 用 JMeter 脚本(`backend/scripts/jmeter/` 已有)跑一轮,记录 baseline
- [ ] 写个 `requirements.txt`(现在没有,环境不可复现)

**产出:一张"哪些端点慢、慢多少"的表。后面每一步都能对着它量收益。**

### Phase 1 · 消除结构性浪费(1–2 天)⭐ ROI 最高,且不需要 Redis
- [ ] 补索引:`(user_id, time)`、`(user_id, done, due_date)`、`checkins(user_id, checkin_date) UNIQUE`
- [ ] `transactions` 的 `YEAR()/MONTH()` 改范围查询
- [ ] `todos` 列表的 `OR due_date IS NULL` 拆成 `UNION ALL` 或改写
- [ ] 25 处 `get_connection()` → 同步连接池
- [ ] 删掉 `transactions.py:31` 的 debug print
- [ ] `_calc_streak` 改 async + 池;与 `stats.py` 的重复逻辑抽成一个函数
- [ ] 成就检查移出写请求同步路径(`BackgroundTasks`)

> 做完这一步,大部分用户能感知的卡顿应该已经消失。**这时候再上 Redis 才能看出叠加收益**,否则数字会被 SQL 问题污染。

### Phase 2 · Redis 基础设施(1 天)
- [ ] Windows 本地起 Redis(见第四节)
- [ ] `utils/redis_client.py`:池 + 同步/异步客户端 + JSON 编解码 + 熔断 + 降级开关
- [ ] `config.py` 加配置;`.env.example` 加样例
- [ ] `@cache` 装饰器 + `ver` 版本号工具
- [ ] 健康检查 `/health` 增加 redis 状态(不阻塞主流程)

### Phase 3 · 读缓存落地(1–2 天)
- [ ] `/stats/patterns`、`/stats/correlation` 加缓存(TTL 300s)
- [ ] `/achievements/available` 加缓存 + metric 计数器
- [ ] `user_settings`、`llm/models` 加缓存
- [ ] 写侧埋 `ver` 版本号(todos / transactions / checkins / settings)
- [ ] `/ai/insights` 结果缓存(TTL 30–60min)

### Phase 4 · 聚合端点(1 天)
- [ ] `GET /api/dashboard` 一次返回首页全部数据
- [ ] 前端 `loadDashboardData` 改为单请求
- [ ] 整包 Redis 缓存(TTL 60s)

### Phase 5 · 限流 / 配额 / 锁(1 天)
- [ ] AI 接口限流(Redis 滑动窗口或固定窗口)
- [ ] `user_quotas` 真实扣减(Redis 计数 + 异步落库)
- [ ] 打卡幂等(唯一索引 + Redis 锁)
- [ ] scheduler / report 生成的分布式锁

### Phase 6 · AI 会话 + 队列(1–2 天,可选)
- [ ] `_chat_history` → Redis LIST + TTL
- [ ] 周报生成改并发 + 队列化

**总计约 6–9 个工作日**,Phase 1 结束就应该有明显用户可感提升。

---

## 四、Windows 上跑 Redis

你是 Windows 环境,几个选项:

| 方式 | 适合 | 说明 |
|---|---|---|
| **Docker Desktop** | 推荐,最接近生产 | `docker run -d -p 6379:6379 --name habit-redis redis:7-alpine` |
| **WSL2 + apt** | 已装 WSL | `sudo apt install redis-server` |
| **Memurai** | 不想装 Docker | Windows 原生 Redis 兼容服务,免费开发版 |
| **tporadowski/redis** | 最轻 | Redis 5.0.14 的 Windows 移植版,单 exe |

考虑到你后面可能还要写 `docker-compose.yml`(`backend/README.md:5` 已经提过这个想法),**建议直接上 Docker**,顺手把 MySQL 也编排进去,一举两得。

Python 依赖:`redis>=5.0`(自带 `redis.asyncio`,不需要额外装 `aioredis` —— 那个已废弃)。

---

## 五、几个需要你拍板的点

1. **Phase 1(纯 SQL/架构优化)和 Redis 谁先上?**
   我强烈建议 Phase 1 先做 —— 它不需要 Redis,风险低,而且不先做的话 Phase 3 的缓存会掩盖 SQL 问题,数据会很好看但你其实没解决根因。

2. **同步/异步要不要统一?**
   现在是两套并存。彻底统一(全部 async + aiomysql)工作量大(25+ 处调用点要改),但能根治线程池问题。折中方案:先给同步侧加连接池止血,不追求统一。

3. **缓存一致性用「版本号」还是「精确 DEL」?**
   我推荐版本号(见 2.3),代价是可能多一次回源,收益是永不漏失效。

4. **AI 会话上下文要不要落 Redis?**
   如果只跑单进程本地开发,dict 也没问题。但一旦要部署给真实用户(哪怕 2 个 worker),就必须迁。你怎么打算?

5. **要不要保留「成就检查在写请求同步路径」的语义?**
   即:勾选待办后立刻弹"解锁成就"动画。如果前端可以接受"下次进成就页才看到新解锁",那就能把成就检查完全移出热路径 —— 收益最大。如果产品上必须即时反馈,那就得用 Redis 计数器把单次评估压到毫秒级。

6. **部署形态?** 单机 uvicorn?几个 worker?有没有云服务器(云 Redis 就几块钱/月)?这决定了 Redis 是本地进程还是要考虑网络超时。

---

## 六、风险清单

| 风险 | 应对 |
|---|---|
| Redis 挂了拖垮整站 | 强制 `socket_timeout=0.2`、全链路 try/except、熔断开关、`REDIS_ENABLED=false` 一键回退 |
| 缓存脏数据 | 版本号校验 + TTL 兜底 + 灰度(先只开 `/stats` 一个端点观察一天) |
| 分布式锁死锁 | 锁必须有 TTL;释放前校验 value(用 Lua 或 `redis.lock` 自带机制) |
| 内存打满 | 所有 key 必须带 TTL(除计数器);`maxmemory-policy allkeys-lru` |
| 改 async 引入并发 bug | 同步侧先只换连接池,不换执行模型 |
| 索引加错锁表 | 小项目直接 `ALTER`,几十万行内无感;`online DDL` 只在 MySQL 5.6+ 需要注意 |

---

## 附:值得单独记一笔的"不是性能问题但会咬人"的点

- `main.py:104` `get_connection()` 未 import → `/db-test` 一调就 NameError
- `backend/requirements.txt` 不存在
- `apscheduler` 未安装,scheduler 静默失败
- `.env` 里有真实 `OPENAI_API_KEY`,且 `backend/.env` 是否已进 `.gitignore` 需要确认
- `ai_rag.py` 用的是已废弃的 `langchain` `HuggingFaceEmbeddings` / `Chroma`,启动时加载 103 个权重文件,冷启动慢
