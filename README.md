# 习惯管家(xiguanguangjia)

个人习惯追踪应用。主产品是**微信小程序**,配套运营管理后台和后端 API + AI 服务。

设计语言为「I 方案(沉香玻璃)」—— 暖米纸底色 + 沉香绿主色 + 玻璃拟态卡片。

---

## 项目组成

| 目录 | 角色 | 技术栈 |
|---|---|---|
| `前端/最终稿敲定/` | 微信小程序(主产品) | 原生小程序 wxml + wxss + js |
| `backend/` | API + AI 服务 | FastAPI + MySQL + Redis(可选)+ LangChain + ChromaDB |
| `admin-web/web端/` | 运营管理后台 | Vue 3 + Ant Design Vue + Vite + Pinia |

---

## 快速开始

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # 填数据库口令和 LLM key
.\scripts\start_backend.ps1    # 首次先按 backend/README.md 建库
```

验证: http://127.0.0.1:8000/health  ·  文档: http://127.0.0.1:8000/docs

> 建库顺序、配置项、架构说明**都在 [backend/README.md](backend/README.md)**。

### 微信小程序

微信开发者工具导入 `前端/最终稿敲定/` 即可。

后端地址在 `app.js` 顶部,模拟器用 `127.0.0.1`、真机自动用局域网 IP。
真机调试需要后端监听 `0.0.0.0` + 防火墙放行 8000 + 勾选「不校验合法域名」,
详见 [CLAUDE.md](CLAUDE.md) 的「真机调试」一节。

### 管理后台

```powershell
cd admin-web/web端
npm install
npm run dev      # http://localhost:5174(注意是 5174)
```

Vite 已配置 proxy,`/api/*` 转发到 `127.0.0.1:8000`。

---

## 目录结构

```
.
├── 前端/最终稿敲定/     # 微信小程序(14 个页面 + 自定义 TabBar)
├── backend/            # 后端(详见 backend/README.md)
├── admin-web/web端/    # 运营管理后台
├── docs/               # 改造报告与验收标准
└── CLAUDE.md           # 开发约定与踩坑记录(改代码前先看)
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [backend/README.md](backend/README.md) | 后端快速开始、分层约定、配置、关键设计、脚本、已知限制 |
| [CLAUDE.md](CLAUDE.md) | 全栈开发约定:设计 token、跨页面通信、真机调试、连接池与缓存的坑 |
| [docs/改造落地报告.md](docs/改造落地报告.md) | 性能重构与 Agent 收敛的完整记录(含实测数据) |

---

## 主要功能

- **待办 / 目标**:按天过滤、批量创建、完成率统计
- **打卡**:连续天数 streak、日历视图、幂等防重复
- **收支 / 饮食**:每日结余、热量目标、分类统计
- **成就**:12 条可配置成就,基于 metric 增量评估
- **数据洞察**:习惯模式识别、跨维度关联分析
- **AI**:多轮对话、function calling 工具链、破坏性操作二次确认、RAG 知识检索

首页采用**单一聚合接口** `GET /api/dashboard`(一次拿全,替代原来的 7 个请求)。

---

## 已知限制

- AI 接口**没有限流 / 配额**,上游 rpm 低时容易 429
- RAG 当前用英文 embedding 模型跑中文检索,召回质量待优化
- `APScheduler` 未安装,周报 / 月报定时任务会跳过
- 小程序无自动化测试,以开发者工具 + 真机为准

更多细节见 [backend/README.md 的「已知限制」](backend/README.md)。
