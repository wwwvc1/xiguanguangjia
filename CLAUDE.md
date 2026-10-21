# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

「习惯管家」个人习惯追踪应用,包含三个独立的部分:

| 目录 | 角色 | 技术栈 |
|---|---|---|
| `前端/最终稿敲定/` | 微信小程序(主产品) | 原生小程序(`.wxml` + `.wxss` + `.js`) |
| `backend/` | API + AI 服务 | FastAPI + MySQL + LangChain + ChromaDB |
| `admin-web/` | 运营管理后台 | Vue 3 + Ant Design Vue + Vite + Pinia |

主产品是**微信小程序**。设计语言遵循「I 方案(沉香玻璃)」,见 `前端/最终稿敲定/app.wxss` 顶部的设计 token 注释。

> 目录名是中文的 `前端/`,不是 `frontend/`。老文档里写成 `frontend/` 的地方都已修正。

## 启动命令

```bash
# 微信小程序(主产品)
# 微信开发者工具导入 前端/最终稿敲定/ 即可

# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 管理后台(注意目录是 admin-web/web端/)
cd admin-web/web端
npm install
npm run dev  # http://localhost:5174(vite.config.ts 里是 5174,不是 5173;strictPort=false 被占用会自动 +1)
```

小程序通过 `app.js` 顶部的 `API_BASE` 访问后端,默认 `http://127.0.0.1:8000/api`。管理后台通过 Vite proxy 转发 `/api/*` 到同一地址。

### 真机调试(手机连电脑后端)

手机上的 `127.0.0.1` 指**手机自己**,必然「网络错误」。三件事缺一不可:

1. 后端监听 `0.0.0.0`:`./scripts/start_backend.ps1`(默认已是 0.0.0.0),它会打印局域网 IP 和下面这条命令
2. 防火墙放行(需管理员):
   `netsh advfirewall firewall add rule name="habit-api-8000" dir=in action=allow protocol=TCP localport=8000`
3. 小程序切地址(Console 执行,**立刻生效,不用改源码**):

```js
wx.setStorageSync('api_base', 'http://<电脑局域网IP>:8000/api')
getApp().applyApiBase()
// 切回模拟器:
// wx.removeStorageSync('api_base'); getApp().applyApiBase()
```

   覆盖逻辑在 `app.js` 的 `resolveApiBase()`;改完 `api_base` 后 App 的 `onShow` 也会自动刷新。

另外必须在开发者工具「详情 → 本地设置」勾选 **「不校验合法域名、web-view(业务域名)、TLS 版本以及 HTTPS 证书」**
—— `http` 明文请求不开这个会被直接拦掉。先用手机浏览器打开 `http://<局域网IP>:8000/health`
验证网络层通不通,再排查小程序侧。

请求失败时 `app.js` 会打 `[request] 失败 GET <地址> → <errMsg>`,
如果日志里的地址还是 `127.0.0.1`,就是 `api_base` 没切成功。

## 小程序架构(主要工作区)

```
前端/最终稿敲定/
├── app.js              # 全局 API 请求封装 + globalData(token, statusBarHeight 等)
├── app.json            # 14 个页面路由 + tabBar 配置
├── app.wxss            # ★ 设计系统:颜色/圆角/字体/玻璃/页面渐变
├── project.config.json # 微信开发者工具项目配置
├── custom-tab-bar/     # 自定义悬浮胶囊 TabBar(4 tab)
└── pages/
    ├── index/          # 首页(数据卡 + AI 建议 + 可拖动 section + streak hero)
    ├── checkin/        # 打卡页(罗马数字 streak hero + 7 列日历)
    ├── todo/           # 待办/目标(tab + 玻璃卡)
    ├── finance/        # 收支(Georgia 斜体大数字 + 列表)
    ├── diet/           # 饮食(meal group 分类卡)
    ├── ai/             # AI 聊天(tab 切换 + 模型选择 + 流式气泡)
    ├── ai-create/      # AI 智能创建(消息流 + 工具链展示)
    ├── achievements/   # 成就页(2 列网格 + 锁定/解锁态)
    ├── stats/          # 数据洞察(KPI + 趋势图 + 关联分析)
    ├── reports/        # 周报/月报
    ├── tasks/          # 任务管理(全部/已完成/收藏)
    ├── settings/       # 设置(头像/AI 模型/导出/退出)
    ├── settings/ai-model/   # AI 模型管理
    └── login/          # 微信登录
```

### 每个页面 4 个文件
- `xxx.wxml` — 结构(组件嵌套,数据绑定用 `{{}}`,事件用 `bindtap`)
- `xxx.wxss` — 样式(只本页私有,公共类在 `app.wxss`)
- `xxx.js` — `Page({ data, onLoad, onShow, methods })`
- `xxx.json` — 页面配置(标题、enablePullDownRefresh 等)

### 跨页面通信
- `getApp().globalData.token` — 用户 token(JS 内存 + `wx.getStorageSync` 持久化)
- `getApp().globalData.dataVersion` — 数据版本号,任何 CRUD 后 `bumpDataVersion()` 自增,首页 onShow 检测到变化就重新拉数据
- 自定义 TabBar 通过 `this.getTabBar().setData({ selected: i })` 同步高亮

## 关键约定

### 设计 token(只在 `app.wxss` 顶部 `page{}` 内定义,所有页面通过 `var(--xxx)` 引用)
```
--agar: #142A20  主色(沉香绿)
--agar-2: #1F3D2D  深绿渐变
--brick: #8E3D2A  砖红(警示/支出)
--bone: #D8C9A5   米骨(强调点缀)
--paper: #EFE9DD  米色纸张(页面底)
--ink: #0F1A14    暖墨(主文字)
--r-sm/md/lg/pill: 12/18/24/999 rpx  圆角系统(全站只用 4 档)
```

### 单位 `rpx`(小程序原生)
- `1rpx = 屏幕宽 / 750`,在 wxss 中直接用
- 浏览器预览时用 1rpx ≈ 0.5px(750 设计宽对应 375 屏宽)
- **不要在 wxss 里写 px**;如果看到 `font-size: 30px` 是 bug

### 字体
- 全局: `font-family: 'Georgia', 'Times New Roman', 'Noto Serif CJK SC', ..., 'PingFang SC', sans-serif`
- 中文: 苹方 / 思源黑体 fallback
- 数字 / 强调: 用 `font-style: italic`(Georgia 真斜体) + `font-variant-numeric: tabular-nums`(数字等宽)

### 玻璃质感
- 卡片默认用 `backdrop-filter: blur(28rpx) saturate(180%)` + 半透明白底 + 1px 内嵌高光
- 整页有 5 层径向渐变作为底层,让 glass 模糊有内容可 blur
- **不要在 wxss 里用 `backdrop-filter: none`**

### 关键类(在 `app.wxss` 全局可用)
- `.bump` / `.bump-sm` / `.card` — 玻璃卡
- `.pit` / `.pit-sm` — 内嵌卡
- `.section-title` / `.empty-tip` / `.divider` — 列表/分隔
- `.nav-titles` / `.nav-meta` / `.serif` / `.serif-italic` — 导航排版
- `.streak-hero` — 沉香绿大数字卡
- `.bump::before` 自动加 1px 顶部高光线

## 后端 / API 关键点

- 基础 URL:`http://127.0.0.1:8000/api`(在 `app.js` 顶部改)
- 鉴权:`Authorization: Bearer <token>`;401 时 `app.js` 先尝试一次静默重登
  (`recoverSession()`:wx.login → `/auth/login`,并发只发一次),成功则重试原请求;
  失败才 `clearSession()`(内存 + storage 一起清)并用 `wx.reLaunch` 跳登录页。
  **不要只清 storage 不清 `globalData.token`** —— 登录页 onLoad 会用残留 token 弹回首页,变成 401 死循环。
- 路径尾斜杠:`backend/main.py` 有 `normalize_api_trailing_slash` 中间件,`/api/todos` 和 `/api/todos/`
  都能命中同一路由。原因:小程序跟 307 重定向会丢 `Authorization` 头 → 一堆假 401。
- 响应格式:后端**直接返回数据**,不包 `{code, data}`,`app.request` 兼容两种
- 主要端点:`/todos`、`/goals`、`/transactions`、`/meals`、`/reminders`、`/ai/chat/*`、`/llm/models`、`/checkins/*`、`/user/settings`、`/achievements/*`
- 后端有 RAG(ChromaDB + 业务规则 markdown 在 `backend/knowledge_base/`)
- **首页优先用 `GET /api/dashboard?date=`** 一次拿全(服务端并发 5 条查询 + 缓存 60s),
  失败了才回退到原来的多请求路径。详见 `docs/改造落地报告.md`。
- **每日首次进入弹窗**:首页数据加载完后,如果今天还没提示过且当前没有待办,
  弹「添加今日待办」。(去添加 / 稍后)
  - 去重键:`wx.getStorageSync('daily_prompt_day')`,值为 `YYYY-MM-DD`,**弹之前就落盘**,保证一天只弹一次
  - 「去添加」用 `wx.setStorageSync('open_add_todo', 1)` 传标记 → 待办页 `onShow` 里的
    `_consumeOpenAddFlag()` 消费它并自动打开新增表单(因为 `switchTab` 不能带 query 参数)
  - `/pages/todo/todo` 是 **tabBar 页面,只能用 `wx.switchTab`**,用 `navigateTo` 会静默失败

### 后端分层(`backend/`,2026-10 重构)

```
core/          配置 / 连接池 / Redis / 缓存版本号     ← 基础设施
repositories/  只有这一层写 SQL
services/      业务编排(dashboard / stats / achievement / checkin / chat_session)
agent/         LangChain 层(chat_model 工厂 + executor 多步工具编排)
routers/       Controller:HTTP 契约 + 参数校验
models/        Pydantic schema
```

- **旧 import 不用改**:`config.py` / `database.py` 是 `core/*` 的 shim,
  `utils/ai_agent.py` 按 `LLM_BACKEND` 分发到 `agent/executor.py` 或 `utils/ai_agent_legacy.py`。
- **写 SQL 一律去 `repositories/`**,不要在 router 里拼。加新表照 `todo_repo.py` 的样子写。
- **跨表业务逻辑去 `services/`**。改造前 `streak` 有三份实现,别再复制第四份。

### AI Agent(已收敛为一套)

`agent/core.py` 的 `ToolCallingAgent` 是**唯一**的工具调用循环,两个端点共用:

| 端点 | 工具 | 轮数 | 二次确认 | 输出 |
|---|---|---|---|---|
| `/api/ai/chat/professional` | 25(`utils/ai_tools.py`) | 5 | 否 | SSE |
| `/api/ai/agent`(ai-create 页) | 18(`utils/ai_crud_tools.py`) | 3 | **是** | JSON |

差异全部通过构造参数表达(`tools` / `max_iterations` / `require_confirmation` / `emit_deltas` / `result_adapter`),循环本体只有一份。
消费方式两种:`astream()` 出事件流,`aloop()` 出结构化结果。

- **不要**再写第三套循环。新增端点先看能不能复用 core 的参数。
- 工具返回格式不统一,由 `result_adapter` 归一成 {ok, data, error}:
  `utils/ai_tools` 本来就是这形状(`identity_result`);`utils/ai_crud_tools` 是「有 error 键即失败」(`crud_result`)。
- 友好错误只在 `core.friendly_error` 一处实现,**不要**在 router 里再翻译一次
  (会变成「出错了: 请求太频繁」)。`aloop` 抛的 `AgentError` 已经是人话,直接 `str(e)`。
- 回归:`python scripts/test_agent_core.py`(31 条,用 FakeLLM,不耗额度、不受 429 影响)。

第三套(`utils/ai_multi_task.py` + `/api/ai/agent/v2`,裸 SDK)**已于 2026-10 删除** —— 前端从未调用过。现在只剩 core 这一个循环。
### 两个必须知道的坑(踩过)

1. **连接池是 `autocommit=True`**。因为 MySQL 默认 REPEATABLE READ 会在首条 SELECT 建快照,
   池化连接如果只读不提交,会**永久停在旧快照上**,读不到别的连接刚插入的行
   (现象:INSERT 成功,紧接着 SELECT 返回 None,表现为 `POST /todos` 间歇性 500)。
   多语句要原子性时用 `async with transaction()`(内部 `begin()` + commit/rollback)。
2. **`todos` 按天过滤保留 `due_date = ? OR due_date IS NULL` 写法**。
   实测在 `(user_id, done, due_date)` 索引下 OR 比 UNION ALL 更快(0.46 vs 0.57 ms),
   收益全部来自索引。别再"优化"成 UNION ALL。

### 缓存(Redis,可选)

- `REDIS_ENABLED=false` 可整体关闭,应用退回直连 MySQL,功能不受影响。
- 失效用**版本号**:写操作 `cache.abump(uid, "todo")` 自增计数器,读时版本对不上就当未命中。
  **新增缓存时不需要去写任何 DEL 逻辑**,这是刻意的设计。
- 官方 `redis` 包没装时自动回退到 `core/mini_redis.py`(纯标准库 RESP2 实现)。
  启动日志会打印 `Redis 后端: redis-py | mini`。

### 后端启动慢(已修,别再回退)
- `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` 必须在**任何** langchain/transformers 导入之前设置
  (huggingface_hub 在 import 时就把它们固化成常量,晚设置无效 → 每次启动都去 huggingface.co
  解析模型版本,断网时反复超时重试,实测卡 20s+)。现在写在 `main.py` 第一行和 `utils/ai_rag.py` 顶部。
- `utils/ai_rag.py` 用 `_local_model_path()` 把 `~/.cache/huggingface/hub/.../snapshots/<rev>`
  的绝对路径直接交给 `SentenceTransformer`,彻底不走 Hub 解析。
- `chromadb` / `torch` / `sentence-transformers` 一律延迟 import(光 import 就 10s+),
  RAG 在 lifespan 里用后台线程预热;纯调接口不想烧 CPU 时设 `RAG_PRELOAD=0`。
- 需要重新下载模型时临时 `set HF_HUB_OFFLINE=0`(或用镜像 `HF_ENDPOINT=https://hf-mirror.com`)。

## 设计参考

**设计稿 HTML 预览已删除**(2026-10 清理仓库时移除,含 `前端/待选小程序前端/`、`admin-web/待选web前端/`、`admin-web/design-scheme-*`、`design-mockup-images/`)。

现在要参考视觉,**直接看已落地的代码**,这是唯一可信来源:

| 想看什么 | 去哪看 |
|---|---|
| 颜色 / 圆角 / 字体 / 玻璃 / 渐变 token | `前端/最终稿敲定/app.wxss` 顶部 `page{}` |
| 通用类(`.bump` / `.pit` / `.card` / `.section-title` / `.streak-hero`) | `app.wxss` 全局 |
| 弹窗怎么写 | 任意页面的 `.modal-mask` + `.modal-content.bump` + `.modal-actions`(10+ 个页面都用了同一套) |
| 列表 / 空态 / 分隔 | `.empty-tip` / `.divider` |
| 复杂卡片(数据卡、AI 建议、快捷按钮) | `pages/index/index.wxss` |

**不要再去找 HTML 预览稿**,它们已经不在仓库里了。

## 修改 UI 的工作流

1. 在 `app.wxss` 顶部 `page{}` 改 token(如想换主色,把 `--agar` 换掉即可)
2. 单页私有样式改对应 `pages/xxx/xxx.wxss`(不污染全局)
3. 设计参考:见上节「设计参考」,直接抄已落地页面的 wxss
4. 只有一个前端目录:`前端/最终稿敲定/`(老的「原始版」已不存在)
5. 修改完后,用微信开发者工具「清除模拟器缓存」再编译,确保 setData/storage 不残留旧值

## 测试改动

- 没有单测框架(小程序项目);以「开发者工具调试器 + 模拟器 + 真机」为准
- 常见调试陷阱:
  - `setData` 超过 256KB 警告 → 长对话/列表分页
  - `backdrop-filter` 在低端 Android 失效 → 已有半透明 fallback
  - 真机 emoji 渲染差异 → 设计稿用抽象 Unicode 已规避
