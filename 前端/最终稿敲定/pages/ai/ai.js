const app = getApp();

// 海外模型没开代理时,连接会一直挂着不报错(既不返回也不 close),
// 所以客户端自己设一个"多久没有任何数据就判定卡死"的看门狗。
const NO_RESPONSE_TIMEOUT = 45000;

const TOOL_LABELS = {
  list_todos: '查询待办',
  add_todo: '添加待办',
  add_todos_batch: '批量添加待办',
  update_todo: '更新待办',
  delete_todo: '删除待办',
  list_goals: '查询目标',
  add_goal: '添加目标',
  update_goal: '更新目标',
  delete_goal: '删除目标',
  list_transactions: '查询收支',
  add_transaction: '添加收支',
  update_transaction: '更新收支',
  delete_transaction: '删除收支',
  get_monthly_summary: '查询月结余',
  get_daily_stats: '查询日结余',
  list_meals: '查询饮食',
  add_meal: '添加饮食',
  update_meal: '更新饮食',
  delete_meal: '删除饮食',
  list_reminders: '查询提醒',
  add_reminder: '添加提醒',
  update_reminder: '更新提醒',
  delete_reminder: '删除提醒',
  get_user_settings: '查询设置',
  update_user_settings: '更新设置'
};

const fmtResult = (name, data) => {
  if (!data) return '';
  if (Array.isArray(data)) {
    if (data.length === 0) return '(空)';
    if (data.length === 1) return JSON.stringify(data[0]).slice(0, 80);
    return `共 ${data.length} 条`;
  }
  if (typeof data === 'object') {
    if (data.id && data.text) return `已添加: ${data.text}`;
    if (data.id && data.name && data.progress !== undefined) return `目标: ${data.name} ${data.progress}%`;
    if (data.id && data.category && data.amount !== undefined) return `${data.category} ¥${Math.abs(data.amount)}`;
    if (data.id && data.meal_type) return `已记录 ${data.meal_type} 餐`;
    if (data.deleted_id) return '已删除';
    if (data.target_calories) return `目标: ${data.target_calories} kcal`;
    if (data.income !== undefined && data.expense !== undefined) {
      return `收 ¥${data.income} / 支 ¥${data.expense} / 结余 ¥${data.net}`;
    }
  }
  return JSON.stringify(data).slice(0, 80);
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    messages: [],
    inputValue: '',
    // 正在等待/生成中的回复条数。只用来显示"停止"按钮和打字动画,
    // 不再当成"能不能发下一条"的开关 —— 上一条没回也能继续发。
    pendingCount: 0,
    currentTab: 'habit',
    scrollIntoView: '',
    aiAvatar: '',
    modelList: [],
    activeModelId: null,
    activeModelName: '系统默认',
    showModelPicker: false,
    // 输入框高度(rpx),根据行数动态变化,默认 80rpx(2 行 + padding)
    inputHeight: 80
  },

  onLoad() {
    const g = app.globalData;
    // 每条 AI 消息独立的请求句柄:aiMsgId -> { task, timer, closed, close() }
    this._requests = {};
    // 计算微信胶囊的右侧位置
    let capsuleRight = 0;
    try {
      const rect = wx.getMenuButtonBoundingClientRect();
      const win = wx.getWindowInfo();
      capsuleRight = (win.windowWidth - rect.left) + 8;
    } catch (e) {}
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight,
      aiAvatar: wx.getStorageSync('ai_avatar') || '',
      activeModelId: wx.getStorageSync('active_model_id') || null,
      capsuleRight: capsuleRight
    });
  },

  onShow() {
    this.setData({ aiAvatar: wx.getStorageSync('ai_avatar') || '' });
    if (!app.globalData.token) {
      app.goLogin();
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 2 });
    }
    this.loadModels();
  },

  // 页面销毁:把还在等的请求断掉,避免回调打到已销毁的页面
  onUnload() {
    Object.keys(this._requests || {}).forEach((id) => {
      const entry = this._requests[id];
      if (!entry) return;
      entry.closed = true;
      if (entry.timer) clearTimeout(entry.timer);
      try { entry.task && entry.task.abort(); } catch (e) {}
    });
    this._requests = {};
  },

  loadModels() {
    app.request({ url: '/llm/models/available' })
      .then(r => {
        const models = r.models || [];
        const activeId = r.active_model_id;
        const active = models.find(m => m.id === activeId)
                   || models.find(m => m.is_system_default)
                   || models[0]
                   || {};
        this.setData({
          modelList: models,
          activeModelId: activeId,
          activeModelName: active ? active.name : '系统默认'
        });
        wx.setStorageSync('active_model_id', activeId);
      })
      .catch(() => {
        this.setData({ modelList: [], activeModelId: null, activeModelName: '系统默认' });
      });
  },

  onInputChange(e) {
    this.setData({ inputValue: e.detail.value });
  },

  // 输入框行数变化 → 动态调整高度
  // 行高 44rpx,最少 2 行(80rpx = 16 padding + 64 content),最多 6 行(280rpx)
  onLineChange(e) {
    const lineCount = e.detail.lineCount || 1;
    const minH = 80;   // 2 行 + padding
    const maxH = 280;  // 6 行 + padding
    const lineH = 44;
    const target = Math.min(maxH, Math.max(minH, 16 + lineCount * lineH));
    if (Math.abs(target - this.data.inputHeight) > 2) {
      this.setData({ inputHeight: target });
    }
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ currentTab: tab });
  },

  onOpenModelPicker() {
    this.setData({ showModelPicker: true });
  },

  onCloseModelPicker() {
    this.setData({ showModelPicker: false });
  },

  stopPropagation() {},

  onSelectModel(e) {
    const id = e.currentTarget.dataset.id;
    if (id === this.data.activeModelId) {
      this.setData({ showModelPicker: false });
      return;
    }
    // 调接口激活
    app.request({ url: `/llm/models/user/${id}/activate`, method: 'POST' })
      .then(() => {
        wx.setStorageSync('active_model_id', id);
        this.setData({ showModelPicker: false });
        wx.showToast({ title: '已切换', icon: 'success' });
        this.loadModels();
      })
      .catch(e => {
        // 系统模型没有 /activate,本地切换即可
        wx.setStorageSync('active_model_id', id);
        this.setData({ showModelPicker: false });
        this.loadModels();
      });
  },

  onManageModels() {
    this.setData({ showModelPicker: false });
    wx.navigateTo({ url: '/pages/settings/ai-model/ai-model' });
  },

  /* ================= 发送 ================= */

  // 不在 isLoading 上做拦截:上一条没回复,这一条立刻就能发出去
  sendMessage() {
    const text = (this.data.inputValue || '').trim();
    if (!text) return;

    // 历史只取"发送本条之前"的消息,避免当前这句话既进 history 又当 message 发两遍
    const history = this.data.messages
      .filter(m => m.role === 'user' || (m.role === 'ai' && m.content))
      .slice(-10)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }));

    const stamp = Date.now();
    const userMsgId = 'msg_' + stamp + '_u';
    const aiMsgId = 'msg_' + stamp + '_a';

    // 限长:只保留最近 30 条,防止 setData 累积过大
    const messages = [
      ...this.data.messages,
      { id: userMsgId, role: 'user', content: text },
      { id: aiMsgId, role: 'ai', content: '', toolChain: [], sources: [], pending: true, error: false }
    ].slice(-30);

    this.setData({ messages, inputValue: '' });
    this._scrollToBottom();

    this._startChat(aiMsgId, text, history);
  },

  // 每条消息单独开一条请求,互不阻塞
  _startChat(aiMsgId, text, history) {
    const url = this.data.currentTab === 'habit'
      ? '/ai/chat/professional'
      : '/ai/chat/general';

    const entry = { task: null, timer: null, closed: false, gotData: false };
    this._requests[aiMsgId] = entry;
    this._syncPending();

    const close = () => {
      if (entry.closed) return;
      entry.closed = true;
      if (entry.timer) { clearTimeout(entry.timer); entry.timer = null; }
      delete this._requests[aiMsgId];
      this._syncPending();
    };
    entry.close = close;

    // 看门狗:超过 NO_RESPONSE_TIMEOUT 没有任何数据 → 判定这条回复卡死,自动停掉
    const armWatchdog = () => {
      if (entry.closed) return;
      if (entry.timer) clearTimeout(entry.timer);
      entry.timer = setTimeout(() => {
        if (entry.closed) return;
        this._abort(
          aiMsgId,
          `AI 在 ${Math.round(NO_RESPONSE_TIMEOUT / 1000)} 秒内没有响应,已自动停止(海外模型没开代理时常见)。可以直接重发,或换个模型。`
        );
      }, NO_RESPONSE_TIMEOUT);
    };

    const task = wx.request({
      url: app.globalData.apiBase + url,
      method: 'POST',
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + app.globalData.token,
        'Accept': 'text/event-stream'
      },
      data: {
        message: text,
        history: history,
        model_id: this.data.activeModelId || undefined
      },
      enableChunked: true,
      success: (res) => {
        if (entry.closed) return;
        const data = res.data || {};
        if (res.statusCode === 401) {
          this._markFailed(aiMsgId, '登录已过期,请重新登录后再发一次。');
          close();
          app.goLogin();
          return;
        }
        if (data.reply) {
          // 非流式 fallback
          this._finishMessage(aiMsgId, data.reply, undefined, data.sources || []);
        } else if (data.detail) {
          this._markFailed(aiMsgId, typeof data.detail === 'string' ? data.detail : 'AI 服务异常');
        } else if (!entry.gotData) {
          this._markFailed(aiMsgId, 'AI 没有返回内容,请重试。');
        }
        close();
      },
      fail: (err) => {
        if (entry.closed) return;  // 看门狗 / 手动停止已经处理过了
        const msg = (err && err.errMsg) || '';
        if (msg.indexOf('abort') >= 0) { close(); return; }
        console.error('AI请求失败:', err);
        this._markFailed(aiMsgId, '网络异常,没拿到回复。检查一下网络/代理后再试。');
        close();
      }
    });
    entry.task = task;
    armWatchdog();

    if (!task.onChunkReceived) return;

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let fullReply = '';
    const toolCalls = [];
    // AI 通过工具改过数据吗?改过就要在收尾时通知首页重新拉数据,
    // 否则回到首页 onShow 检测不到 dataVersion 变化,不会刷新(用户看到的"没反应")。
    let wroteData = false;

    task.onChunkReceived((res) => {
      if (entry.closed) return;
      entry.gotData = true;
      armWatchdog();  // 有数据就续命,慢速流式输出不会被误杀

      let textChunk = '';
      try {
        textChunk = typeof res.data === 'string'
          ? res.data
          : decoder.decode(new Uint8Array(res.data), { stream: true });
      } catch (e) {
        textChunk = this._arrayBufferToString(res.data);
      }

      buffer += textChunk;
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.indexOf('data: ') !== 0) continue;
        let evt;
        try {
          evt = JSON.parse(line.slice(6));
        } catch (e) {
          continue;
        }
        const t = evt.type;

        if (t === 'tool_call') {
          const name = evt.name || 'unknown';
          toolCalls.push({
            id: 'tc_' + toolCalls.length + '_' + Date.now(),
            name,
            label: TOOL_LABELS[name] || name,
            args: evt.args || {},
            ok: null,
            summary: ''
          });
          this._updateAiMessage(aiMsgId, fullReply, toolCalls);
        } else if (t === 'tool_result') {
          if (toolCalls.length > 0) {
            const last = toolCalls[toolCalls.length - 1];
            last.ok = !!evt.ok;
            last.summary = evt.ok
              ? fmtResult(last.name, evt.result)
              : (evt.error || '执行失败');
            // 写类工具(与后端 services/cache_invalidation.py 的前缀约定一致)
            if (evt.ok && /^(add|create|update|delete|remove|toggle|complete|batch|set|mark|upsert)_/.test(last.name)) {
              wroteData = true;
            }
          }
          this._updateAiMessage(aiMsgId, fullReply, toolCalls);
        } else if (t === 'text_delta') {
          fullReply += evt.content || '';
          this._updateAiMessage(aiMsgId, fullReply, toolCalls);
        } else if (t === 'done') {
          fullReply = evt.reply || fullReply;
          this._finishMessage(aiMsgId, fullReply, toolCalls, evt.sources || []);
          // 让首页/待办/收支等页面在下次 onShow 时重新拉数据
          if (wroteData) app.bumpDataVersion();
          close();
        } else if (t === 'error') {
          if (wroteData) app.bumpDataVersion();
          this._abort(aiMsgId, evt.message || 'AI 服务异常');
        }
      }
    });
  },

  // 手动停止全部等待中的回复
  stopAll() {
    Object.keys(this._requests || {}).forEach((id) => this._abort(id, '已停止生成'));
  },

  // 断掉某条消息的请求;hint 非空时在气泡里留一行说明
  _abort(aiMsgId, hint) {
    const entry = this._requests && this._requests[aiMsgId];
    if (!entry) return;
    entry.closed = true;
    if (entry.timer) { clearTimeout(entry.timer); entry.timer = null; }
    try { entry.task && entry.task.abort(); } catch (e) {}
    delete this._requests[aiMsgId];
    if (hint) this._markFailed(aiMsgId, hint);
    this._syncPending();
  },

  _syncPending() {
    const n = Object.keys(this._requests || {}).length;
    if (n !== this.data.pendingCount) this.setData({ pendingCount: n });
  },

  // 正常结束:落最终内容 + 清掉 pending
  _finishMessage(msgId, content, toolChain, sources) {
    const messages = this.data.messages.map(m => {
      if (m.id !== msgId) return m;
      const update = { ...m, content: this._clip(content), pending: false, error: false };
      if (toolChain !== undefined) update.toolChain = toolChain;
      if (sources !== undefined) update.sources = this._clipSources(sources);
      return update;
    });
    this.setData({ messages });
    this._scrollToBottom();
  },

  // 失败/超时/被停止:保留已有内容,补一行说明,并把气泡标红
  _markFailed(msgId, hint) {
    const tip = hint || '没拿到回复,请重试。';
    const messages = this.data.messages.map(m => {
      if (m.id !== msgId) return m;
      const content = m.content ? `${m.content}\n\n${tip}` : tip;
      return { ...m, content, pending: false, error: true };
    });
    this.setData({ messages });
    this._scrollToBottom();
  },

  // 更新 AI 消息内容(流式增量,含 toolChain 渲染)
  _updateAiMessage(msgId, content, toolChain, sources) {
    const messages = this.data.messages.map(m => {
      if (m.id !== msgId) return m;
      const update = { ...m, content: this._clip(content) };
      if (toolChain !== undefined) update.toolChain = toolChain;
      if (sources !== undefined) update.sources = this._clipSources(sources);
      return update;
    });
    this.setData({ messages, scrollIntoView: 'chat-bottom' });
  },

  // 单条内容上限 4000 字符,防止 AI 长回复把单条消息撑得太大
  _clip(content) {
    const raw = content || '';
    return raw.length > 4000
      ? raw.slice(0, 4000) + '\n\n...(回复已截断,完整版请看历史记录)'
      : raw;
  },

  // sources 数组最多保留 8 条,每条 URL+title 截断
  _clipSources(sources) {
    return (sources || []).slice(0, 8).map(s => ({
      title: String(s.title || '').slice(0, 80),
      url: String(s.url || '').slice(0, 200)
    }));
  },

  _scrollToBottom() {
    // 用 setTimeout 让 DOM 先更新完,再触发 scroll-into-view
    setTimeout(() => {
      this.setData({ scrollIntoView: 'chat-bottom' });
    }, 50);
  },

  _arrayBufferToString(buffer) {
    try {
      const decoder = new TextDecoder('utf-8');
      return decoder.decode(buffer);
    } catch (e) {
      return '';
    }
  },

  onFabTap() {
    wx.navigateTo({ url: '/pages/ai-create/ai-create' });
  }
});
