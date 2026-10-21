"""AI Agent 层(LangChain)

- `chat_model` 负责「用哪个模型说话」(ChatOpenAI 工厂 + LLM_BACKEND 灰度开关)
- `executor`   负责「多步工具调用怎么编排」(保留自研循环,只换成 LangChain 消息对象)

刻意**没有**用 LangGraph 重写:现有工具注册表、二次确认流、SSE 事件契约
都工作得很好,换编排框架只会放大回归面。这里只替换「怎么跟模型说话」。
"""
