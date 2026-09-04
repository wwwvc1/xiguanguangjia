const app = getApp();

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
    isLoading: false,
    currentTab: 'habit',
    scrollIntoView: '',
    aiAvatar: '',
    modelList: [],
    activeModelId: null,
    activeModelName: '系统默认',
    showModelPicker: false
  },

  onLoad() {
    const g = app.globalData;
    // 计算微信胶囊的右侧位置
    let capsuleRight = 0;
    try {
      const rect = wx.getMenuButtonBoundingClientRect();
      const sysInfo = wx.getSystemInfoSync();
      capsuleRight = (sysInfo.windowWidth - rect.left) + 8;
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
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 2 });
    }
    this.loadModels();
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

  sendMessage() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.isLoading) return;

    const userMsgId = 'msg_' + Date.now();
    // 限长:只保留最近 30 条,防止 setData 累积过大
    const next = [...this.data.messages, { id: userMsgId, role: 'user', content: text }].slice(-30);
    this.setData({
      messages: next,
      inputValue: '',
      isLoading: true
    });
    this._scrollToBottom();

    // 先创建一个空的 AI 消息占位(带 toolChain 数组)
    const aiMsgId = 'msg_' + (Date.now() + 1);
    this.setData({
      messages: [...this.data.messages, {
        id: aiMsgId,
        role: 'ai',
        content: '',
        toolChain: [],
        sources: []
      }].slice(-30)
    });
    this._scrollToBottom();

    const url = this.data.currentTab === 'habit'
      ? '/ai/chat/professional'
      : '/ai/chat/general';

    // 取最近 10 条消息作为历史(只取 user/assistant 的纯文本)
    const history = this.data.messages
      .filter(m => m.role === 'user' || (m.role === 'ai' && m.content))
      .slice(-10)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }));

    const requestTask = wx.request({
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
        // 非流式 fallback
        if (res.data && res.data.reply) {
          this._updateAiMessage(aiMsgId, res.data.reply, [], res.data.sources || []);
          this.setData({ isLoading: false });
        }
      },
      fail: (err) => {
        console.error('AI请求失败:', err);
        this._handleError(err, aiMsgId);
      }
    });

    if (requestTask.onChunkReceived) {
      let buffer = '';
      let fullReply = '';
      const toolCalls = [];  // 当前 AI 消息下的所有工具

      requestTask.onChunkReceived((res) => {
        const text = this._arrayBufferToString(res.data);
        buffer += text;
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            const t = evt.type;

            if (t === 'tool_call') {
              // 新建一个 toolChain 项(loading)
              const name = evt.name || 'unknown';
              const label = TOOL_LABELS[name] || name;
              toolCalls.push({
                id: 'tc_' + toolCalls.length + '_' + Date.now(),
                name,
                label,
                args: evt.args || {},
                ok: null,
                summary: ''
              });
              this._updateAiMessage(aiMsgId, fullReply, toolCalls);
            } else if (t === 'tool_result') {
              // 更新最后一项的结果
              if (toolCalls.length > 0) {
                const last = toolCalls[toolCalls.length - 1];
                last.ok = !!evt.ok;
                last.summary = evt.ok
                  ? fmtResult(last.name, evt.result)
                  : (evt.error || '执行失败');
              }
              this._updateAiMessage(aiMsgId, fullReply, toolCalls);
            } else if (t === 'text_delta') {
              fullReply += evt.content || '';
              this._updateAiMessage(aiMsgId, fullReply, toolCalls);
            } else if (t === 'done') {
              fullReply = evt.reply || fullReply;
              const sources = evt.sources || [];
              this._updateAiMessage(aiMsgId, fullReply, toolCalls, sources);
              this.setData({ isLoading: false });
            } else if (t === 'error') {
              this._handleError({ errMsg: evt.message || 'AI 服务异常' }, aiMsgId);
            }
          } catch (e) {
            // 忽略解析错误
          }
        }
      });
    }
  },

  // 更新 AI 消息内容(含 toolChain 渲染)
  _updateAiMessage(msgId, content, toolChain, sources) {
    // 单条内容上限 4000 字符,防止 AI 长回复把单条消息撑得太大
    const safeContent = (content || '').slice(0, 4000);
    const messages = this.data.messages.map(m => {
      if (m.id !== msgId) return m;
      const update = { ...m, content: safeContent };
      if (toolChain !== undefined) update.toolChain = toolChain;
      if (sources !== undefined) {
        // sources 数组最多保留 8 条,每条 URL+title 截断
        update.sources = (sources || []).slice(0, 8).map(s => ({
          title: String(s.title || '').slice(0, 80),
          url:   String(s.url || '').slice(0, 200)
        }));
      }
      return update;
    });
    this.setData({ messages, scrollIntoView: '' });
    this.setData({ scrollIntoView: 'chat-bottom' });
  },

  _scrollToBottom() {
    this.setData({ scrollIntoView: '' });
    this.setData({ scrollIntoView: 'chat-bottom' });
  },

  _handleError(err, aiMsgId) {
    const msg = (err && (err.errMsg || err.message)) || '';
    let toastMsg = '发送失败，请重试';
    if (msg.includes('API配置') || msg.includes('authentication')) toastMsg = 'AI服务配置异常';
    else if (msg.includes('超时') || msg.includes('timeout')) toastMsg = '网络超时，请重试';
    else if (msg.includes('频繁') || msg.includes('rate limit') || msg.includes('429')) toastMsg = '请求太频繁，请稍后再试';
    wx.showToast({ title: toastMsg, icon: 'none', duration: 2500 });
    const messages = this.data.messages.filter(m => m.id !== aiMsgId);
    this.setData({ messages, isLoading: false });
  },

  _arrayBufferToString(buffer) {
    const decoder = new TextDecoder('utf-8');
    return decoder.decode(buffer);
  },

  onFabTap() {
    wx.navigateTo({ url: '/pages/ai-create/ai-create' });
  }
});
