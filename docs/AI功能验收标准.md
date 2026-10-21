# AI 功能验收标准

> 版本:v1.0
> 适用项目:习惯管家(个人习惯小程序 + admin-web)
> 验收日期:明天(用户要求)

---

## 0. 总览

本文档列出 **AI 功能验收** 全部标准,涵盖:
- 数据正确性(各页用真实数据,不是 mock)
- AI 解读完整性(报告 / 智能建议 / 聊天)
- CRUD 状态持久化(打勾 / 打卡 / 收支必须准)
- 系统日志完整性(所有 LLM 调用都留痕)
- 数据资产可追溯(web 端能下钻看真实数据 + 用户)
- 模型一致性(数据分析统一用系统默认模型)

---

## 1. 数据正确性(P0)

### 1.1 Web 端"数据洞察"页
- ❌ 现状:`InsightsView.vue` 798 行全 PRNG mock,4 张图(散点 / 折线 / 柱状 / 热力)都是随机数
- ✅ 验收:每张图必须读真实 API,有**可点击下钻**(点散点看具体用户,点柱状看具体时段等)

### 1.2 Web 端"数据资产分布"卡片(7 个)
- 现状:`DashboardView.vue` 数字来自 `stats.data.*`,仅是**全局计数**,无下钻
- ✅ 验收:
  - 每个卡片(待办/目标/收支/饮食/提醒/成就/报告)**必须可点击**
  - 点击打开**真实数据列表 + 显示属于哪个用户**(用户名 / ID / 创建时间)
  - 列表支持分页、按时间倒序、按用户过滤

### 1.3 小程序"数据洞察"页(`pages/stats/stats.js`)
- 现状:✅ 调 `/stats/patterns` + `/stats/correlation`,读真实数据
- ⚠️ 验收:streak 必须与打卡页一致(用 `checkins` 表,不用 `todos.due_date`)

### 1.4 小程序"AI 报告"页(`pages/reports/reports.js`)
- 现状:✅ 数据真实(`utils/report_generator.py` 读 todos/tx/meals/goals)
- ⚠️ 验收:报告里必须包含
  1. 数据快照(待办 / 收支 / 饮食 / 目标) ← 已有
  2. **数据洞察摘要**(从 `stats/patterns` 拿最佳/最差完成日、趋势)
  3. **关联分析摘要**(从 `stats/correlation` 拿运动 vs 热量等)
  4. **AI 解读**(LLM 调用,失败时降级 Markdown)

### 1.5 报告生成不能"无声覆盖"
- ⚠️ 现状:`ON DUPLICATE KEY UPDATE` 直接覆盖
- ✅ 验收:同周期重生成时,弹窗确认"将覆盖旧报告 YYYY-MM-DD 周报,是否继续?"

---

## 2. AI 解读完整性(P0)

### 2.1 系统默认模型优先
- ✅ 验收:**所有数据分析/洞察/报告/系统日志 AI 解读功能,必须调用 `settings.OPENAI_API_KEY` 的系统默认模型**,**不**受用户激活的 LLM 模型影响
- 实现位置:
  - Web 端"数据洞察"的 AI 分析(新增)
  - Web 端"系统日志"页的 AI 解读(新增)
  - 小程序"AI 报告"生成
  - 小程序"数据洞察 → AI 智能建议"(`/api/insights`)
  - 后台仪表盘 LLM 解读

### 2.2 智能创建助手 `ai-create.js`
- 现状:✅ 工具执行器真实写库(25 个工具,涵盖 todos/goals/transactions/meals/reminders)
- ⚠️ 但 **2 个问题**:
  1. `routers/ai_agent.py` 不写 `ai_chat_logs`,**会话过程无痕**
  2. 会话状态 `_SESSIONS` 是进程内 dict,**服务器重启 = 上下文丢失**
- ✅ 验收:
  - 智能创建的每条 user/assistant/tool 调用都进 `ai_chat_logs`
  - 会话上下文至少 **入 DB**(新建 `ai_agent_sessions` 表),服务器重启可恢复

### 2.3 AI 报告 LLM 调用
- 现状:`utils/report_generator.py` 直接 `OpenAI(...)` 调,**不**经 `utils/ai_logging`
- ✅ 验收:报告生成成功或失败,**都要**在 `ai_chat_logs` 留一条 assistant 行

### 2.4 AI 智能建议 `/api/insights`
- 现状:`routers/stats.py` 调 LLM,**不**经 `ai_logging`
- ✅ 验收:每次调 `/insights` 都要留痕

### 2.5 AI 任务生成 `/api/ai/generate-tasks`
- 现状:✅ 已存在(看 `routers/ai_generate.py`),但**不**写日志
- ✅ 验收:留痕

### 2.6 完整 LLM 调用清单(必须全部留痕)

| 端点 | 文件 | 现状 | 必须修 |
|---|---|---|---|
| `POST /api/ai/chat/general` | `routers/ai_general.py` | ✅ 写 | — |
| `POST /api/ai/chat/professional` | `utils/ai_agent.AgentExecutor` | ✅ 写 | — |
| `POST /api/ai/agent` | `routers/ai_agent.py` | ❌ 不写 | **加** |
| `POST /api/ai/agent/confirm` | `routers/ai_agent.py` | ❌ 不写 | **加** |
| `POST /api/insights` | `routers/stats.py` | ❌ 不写 | **加** |
| `POST /api/reports/generate` | `utils/report_generator.py` | ❌ 不写 | **加** |
| `POST /api/ai/generate-tasks` | `routers/ai_generate.py` | ❌ 不写 | **加** |

---

## 3. CRUD 状态持久化(P0)

### 3.1 通用规则
- ✅ 验收:**小程序所有 CRUD(待办/目标/收支/饮食/提醒/打卡/成就/设置/AI创建)都必须**
  1. 真实写库(不是只本地 setData)
  2. 成功后调 `app.bumpDataVersion()`
  3. 失败有 toast 提示,**不会**假成功
  4. 退出再进入,数据与上次一致

### 3.2 各页验证项

| 页面 | 操作 | 验收方法 |
|---|---|---|
| 待办 (index/todo) | 打勾 | DB 中 `done=1`,退出再进仍显示已完成 |
| 打卡 (checkin) | 今日打卡 | `checkins` 表多 1 行,streak +1,日历有 ✓ |
| 收支 (finance) | 记一笔 | `transactions` 多 1 行,首页/财务页都能看到 |
| 饮食 (diet) | 加一餐 | `meals` + `meal_items` 多 N 行,首页热量刷新 |
| 提醒 (settings) | 新增提醒 | `reminders` 多 1 行,首页能数到 |
| 目标 (tasks) | 进度调整 | `goals.progress` 变,首页完成率刷新 |
| AI 创建 | 加一笔 100 元 | 与手填完全一样,`transactions` 多 1 行 |
| 设置 (settings) | 改昵称/头像 | `users.nickname/avatar` 更新,所有页面顶部用户信息刷新 |

### 3.3 响应时间
- ✅ 验收:所有 CRUD 接口在本地 MySQL 环境下,**P95 < 500ms**
- 前端:点击后 < 200ms 出 toast
- 列表刷新:onShow → 首屏渲染 < 1s

---

## 4. Web 端"系统日志"页 AI 解读(P0,新增功能)

### 4.1 入口
- 在 `LogsView.vue` 顶部加"AI 解读最近 50 条"按钮

### 4.2 行为
- ✅ 验收:
  1. 点击 → 调新接口 `POST /api/admin/logs/ai-summary`(系统默认模型)
  2. 接口拉最近 50 条日志,按 action 聚合 + 时间聚合,生成结构化 prompt
  3. LLM 返 3-5 条管理员视角的洞察(异常操作、高频用户、潜在风险)
  4. 弹出**只读 modal**显示,带"复制到剪贴板"按钮
  5. **每次调用必须在 `ai_chat_logs` 留痕**(系统用户的 user_id 可以是 0 或预留 admin id)

### 4.3 数据准确性
- 必须从 `operation_logs` 表真实查
- LLM 返回的内容必须**有 grounding**:每条洞察后附引用的日志 action 列表

---

## 5. Web 端"数据洞察"页 AI 运营建议(P0,新增功能)

### 5.1 入口
- 在 `InsightsView.vue` 顶部加"AI 运营建议"按钮

### 5.2 行为
- ✅ 验收:
  1. 点击 → 调新接口 `POST /api/admin/insights/ai-summary`(系统默认模型)
  2. 接口汇总全平台数据(用户数 / DAU / 各业务表总量 / 7 天趋势 / 异常)
  3. LLM 返 3-5 条**运营建议**(用户增长 / 活跃度 / 留存 / 风险点)
  4. 弹 modal 显示,带"复制"按钮
  5. 留痕到 `ai_chat_logs`

### 5.3 图表全部接真实 API
- 4 张图必须从 `/api/admin/insights/*` 系列接口拿数据
- 图表**可下钻**:点散点 → 该用户 30 天 todo / 收支明细;点柱状 → 该时段所有用户;点热力格子 → 那 1 小时的活跃 user_id 列表
- 每条数据**带用户名 / ID** 标识

---

## 6. 数据资产分布(7 卡)AI 分析(P0,新增)

### 6.1 入口
- `DashboardView.vue` 的 7 张卡片,**任一**点击都进**统一分析页**

### 6.2 行为
- ✅ 验收:
  1. 点击"待办"卡片 → 跳 `DataAssetView?type=todos`
  2. 该页**顶部**显示真实数据表(分页 / 排序 / 用户过滤 / 创建时间)
  3. 每行显示:`id` / `用户ID+用户名` / `内容` / `创建时间` / `状态`
  4. 该页**右上**有"AI 分析"按钮 → 调 `/api/admin/insights/data-asset?type=todos`(系统默认模型)
  5. LLM 基于**这批数据**(或全局统计)给出分析,例如"近 7 天待办创建量最高的 3 个用户是 X、Y、Z,建议..."
  6. 留痕

### 6.3 支持的 7 个 type
- `todos` / `goals` / `transactions` / `meals` / `reminders` / `achievements` / `reports`

### 6.4 数据安全
- 大量数据时**只取样本**(最多 200 条)给 LLM,避免超 token 限
- 敏感信息(密码 / token)不进 prompt

---

## 7. 系统默认模型配置(P0)

### 7.1 约定
- 数据分析 / 报告 / 系统日志 / 数据洞察 **统一** 走 `llm_models.is_system_default=1` 的模型
- 后端 helper 新建 `utils/llm_admin.py::get_admin_llm_client()` 返回 (client, model_name)
- 不读 `users` 表,不走 `get_llm_client_for_user()`

### 7.2 验收
- ✅ 验收:把"系统默认模型"删了,数据分析/报告应该**全部失败 + 报错"系统默认模型未配置"**,不是 fallback 到用户模型

---

## 8. 知识库 + RAG(P1)

### 8.1 现状
- ✅ RAG 引擎在 `utils/ai_rag.py`,数据能加载
- ✅ 4 份静态 + N 份上传
- ⚠️ 但只有 `/api/ai/chat/professional` 用了 RAG(拼到 system prompt)
- ❌ `/api/insights` / 报告生成 / 系统日志 AI 解读**没**用 RAG

### 8.2 验收
- ✅ `/insights` 和报告生成的 prompt 里**可选**拼 `search_knowledge(topic, top_k=2)` 拿相关业务知识
- ✅ Web 端"数据洞察"和"系统日志"AI 解读也支持 RAG(可选)

---

## 9. schema.sql 缺列(P1,致命)

### 9.1 问题
- `backend/sql/schema.sql:49-58` 的 `todos` 表**没有 `due_date` 列**
- 但是代码到处引用 `todos.due_date`:
  - `routers/stats.py` weekday 分布、30 天趋势
  - `routers/todos.py` 列表查询
  - `routers/reports.py` 报告生成
  - `utils/report_generator.py` 报告统计
- 如果生产 DB 是从 `schema.sql` 初始化的,**所有这些查询会 SQL 错误崩掉**

### 9.2 验收
- ✅ `schema.sql` 加上 `due_date DATETIME NULL` 列
- ✅ 加 `INDEX idx_due_date (due_date)`
- ✅ 写一个 `sql/add_todos_due_date.sql` 兼容老的迁移
- ✅ 跑一次 ALTER 验证

---

## 10. 性能 + 稳定性(P2)

### 10.1 首页 onShow 重拉风暴
- 现状:`index.js` 切 tab 每次都全量重拉 5+ 个接口
- ✅ 验收:加 `lastDataVer` 节流,没变更不重拉(已有框架,需完善)

### 10.2 报告生成慢
- 现状:同步 LLM,可能 5-10s
- ✅ 验收:加"生成中"loading 状态,后端可考虑异步(本期不做)

---

## 11. 验收清单(明天检查用)

### A. 数据正确性 ✅
- [ ] Web"数据洞察"4 张图都是真实数据,不是 mock
- [ ] Web"数据资产分布"7 卡可点击下钻,显示真实数据 + 用户
- [ ] 小程序 stats 页 streak 与 checkin 页一致
- [ ] 小程序报告含数据洞察 + 关联分析摘要

### B. AI 解读完整 ✅
- [ ] 7 路 LLM 调用全部进 `ai_chat_logs`
- [ ] 所有数据分析/报告用系统默认模型
- [ ] Web"系统日志"有"AI 解读"按钮并工作
- [ ] Web"数据洞察"有"AI 运营建议"按钮并工作
- [ ] 数据资产分析支持 7 个 type

### C. CRUD 状态正确 ✅
- [ ] 待办打勾 → DB 写入 → 退出再进仍显示已完成
- [ ] 打卡 → 写入 → streak 更新
- [ ] 收支 → 写入 → 财务页可见
- [ ] 饮食 → 写入 → 首页热量更新
- [ ] AI 创建助手 → 工具真实写库 + bumpDataVersion

### D. 系统日志完整 ✅
- [ ] 智能创建会话进 `ai_chat_logs`
- [ ] AI 报告生成进 `ai_chat_logs`
- [ ] 智能建议进 `ai_chat_logs`
- [ ] AI 任务生成进 `ai_chat_logs`

### E. Schema 修复 ✅
- [ ] `schema.sql` 加 `todos.due_date` 列 + 索引
- [ ] 跑迁移验证 ALTER

### F. 性能 ✅
- [ ] CRUD 接口 P95 < 500ms
- [ ] 列表刷新 onShow < 1s
- [ ] toast 响应 < 200ms

---

## 实施顺序(给开发者)

1. **P0 修 schema**(防止线上崩)
2. **P0 补 5 路 LLM 日志**
3. **P0 修 stats streak 一致性**
4. **P0 重写 Web"数据洞察"(接真实 API + 加 AI 按钮)**
5. **P0 Web"系统日志"加 AI 解读按钮**
6. **P0 Web"数据资产分布"下钻 + AI 分析**
7. **P0 LLM 配置:换 DeepSeek 让 AI 真能跑**
8. **P1 智能创建会话持久化**
9. **P2 性能优化**

预计 1-2 个完整工作日。
