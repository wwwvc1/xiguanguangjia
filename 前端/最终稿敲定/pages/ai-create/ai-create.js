const app = getApp();

const examplePrompts = [
  '添加一个待办:买菜',
  '看看我今天有什么待办',
  '我这个月花了多少?',
  '记录午餐:鸡腿饭 600 卡',
];

let _msgIdCounter = 0;
const nextMsgId = () => ++_msgIdCounter;

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    inputValue: '',
    isGenerating: false,
    messages: [],          // {id, role, content, ...}
    examples: examplePrompts,
    sessionId: '',         // 后端会话 ID,持久化
    scrollToId: ''
  },

  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });
    // 恢复 session_id(实现多轮记忆)
    const sid = wx.getStorageSync('ai_agent_session_id');
    if (sid) this.setData({ sessionId: sid });
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  onExampleTap(e) {
    const text = e.currentTarget.dataset.text;
    this.setData({ inputValue: text });
  },

  // 工具:滚到底部
  scrollToBottom() {
    const last = this.data.messages[this.data.messages.length - 1];
    if (last) this.setData({ scrollToId: `msg-${last.id}` });
  },

  // 工具:动作名→中文标签
  actionLabel(tool) {
    const map = {
      add_todo: '加待办', add_goal: '加目标', add_transaction: '加收支', add_meal: '加饮食',
      update_todo: '改待办', update_goal: '改目标', update_transaction: '改收支',
      delete_todo: '删待办', delete_goal: '删目标', delete_transaction: '删收支', delete_meal: '删饮食',
      list_todos: '查待办', list_goals: '查目标', list_transactions: '查收支', list_meals: '查饮食',
      aggregate_transactions: '统计收支', aggregate_todos: '统计待办', aggregate_goals: '统计目标'
    };
    return map[tool] || tool;
  },

  resultTitle(kind) {
    const map = {
      todos: '待办列表', goals: '目标列表', transactions: '收支记录', meals: '饮食记录',
      'aggregate_transactions': '收支统计', 'aggregate_todos': '待办统计', 'aggregate_goals': '目标统计'
    };
    return map[kind] || '结果';
  },

  // 发送消息
  onSend() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.isGenerating) return;

    // 1) 推用户消息
    const userMsg = { id: nextMsgId(), role: 'user', content: text };
    const newMessages = [...this.data.messages, userMsg];
    this.setData({
      messages: newMessages,
      inputValue: '',
      isGenerating: true
    });
    this.scrollToBottom();

    // 2) 调后端
    this.callAgent(text, newMessages);
  },

  callAgent(message, currentMessages) {
    const self = this;
    wx.request({
      url: app.globalData.apiBase + '/ai/agent',
      method: 'POST',
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + app.globalData.token
      },
      data: {
        message: message,
        session_id: self.data.sessionId || undefined
      },
      success: (res) => {
        const data = res.data || {};
        if (data.session_id) {
          self.setData({ sessionId: data.session_id });
          wx.setStorageSync('ai_agent_session_id', data.session_id);
        }
        self.handleAgentResponse(data, currentMessages);
      },
      fail: (err) => {
        console.error('AI 请求失败:', err);
        self.appendAiMessage('网络出错,请稍后再试 🙏');
        self.setData({ isGenerating: false });
      }
    });
  },

  // 处理响应
  handleAgentResponse(data, currentMessages) {
    const summary = (data.summary || '').trim();
    const intent = data.intent;

    let newMessages = [...currentMessages];

    // 1) AI 总结气泡(chat 类无 action 也没 summary 时不显示)
    if (summary) {
      newMessages.push({ id: nextMsgId(), role: 'ai', content: summary });
    }

    // 2) 已执行的动作(增/查/聚合)
    if (data.actions && data.actions.length) {
      newMessages.push({
        id: nextMsgId(),
        role: 'actions',
        actions: data.actions
      });
    }

    // 3) 待确认操作
    if (data.needs_confirmation && data.pending_actions && data.pending_actions.length) {
      newMessages.push({
        id: nextMsgId(),
        role: 'confirm',
        confirmationRequest: data.confirmation_request,
        pendingActions: data.pending_actions
      });
    }

    // 4) 查询结果列表(独立渲染)
    if (intent === 'read' && data.actions && data.actions.length) {
      const listAct = data.actions.find(a => a.tool && a.tool.startsWith('list_'));
      if (listAct && listAct.result && listAct.result.items) {
        newMessages.push({
          id: nextMsgId(),
          role: 'result',
          kind: listAct.tool.replace('list_', ''),
          items: listAct.result.items
        });
      }
    }

    this.setData({ messages: newMessages, isGenerating: false });
    this.scrollToBottom();
  },

  // 追加纯文本 AI 消息(网络错误用)
  appendAiMessage(content) {
    const newMessages = [...this.data.messages, { id: nextMsgId(), role: 'ai', content }];
    this.setData({ messages: newMessages });
    this.scrollToBottom();
  },

  // 确认执行
  onAcceptConfirm(e) {
    const msgId = e.currentTarget.dataset.msgId;
    const target = this.data.messages.find(m => m.id === msgId);
    if (!target) return;

    // 把该消息标记为已处理(改文案)
    const updated = this.data.messages.map(m => {
      if (m.id === msgId) {
        return { ...m, confirmationRequest: '⏳ 正在执行...', role: 'confirm' };
      }
      return m;
    });
    this.setData({ messages: updated, isGenerating: true });

    wx.request({
      url: app.globalData.apiBase + '/ai/agent/confirm',
      method: 'POST',
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + app.globalData.token
      },
      data: {
        session_id: this.data.sessionId,
        message: '确认'
      },
      success: (res) => {
        const data = res.data || {};
        // 移除原 confirm 卡片,追加 AI 总结 + 执行结果
        const filtered = this.data.messages.filter(m => m.id !== msgId);
        let newMsgs = [...filtered];
        const summary = (data.summary || '').trim();
        if (summary) {
          newMsgs.push({ id: nextMsgId(), role: 'ai', content: summary });
        }
        if (data.actions && data.actions.length) {
          newMsgs.push({ id: nextMsgId(), role: 'actions', actions: data.actions });
        }
        this.setData({ messages: newMsgs, isGenerating: false });
        this.scrollToBottom();
      },
      fail: () => {
        this.setData({ isGenerating: false });
        wx.showToast({ title: '执行失败', icon: 'none' });
      }
    });
  },

  // 取消确认
  onCancelConfirm(e) {
    const msgId = e.currentTarget.dataset.msgId;
    const filtered = this.data.messages.filter(m => m.id !== msgId);
    filtered.push({ id: nextMsgId(), role: 'ai', content: '好的,已取消。' });
    this.setData({ messages: filtered });
    this.scrollToBottom();
    // 通知后端清除 pending(可选,过 1 小时会自动过期)
    wx.request({
      url: app.globalData.apiBase + '/ai/agent/reset',
      method: 'POST',
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + app.globalData.token
      },
      data: { session_id: this.data.sessionId }
    });
  },

  // 清空对话
  onResetSession() {
    wx.showModal({
      title: '清空对话',
      content: '清空后当前会话记忆会丢失,确定?',
      success: (res) => {
        if (!res.confirm) return;
        if (this.data.sessionId) {
          wx.request({
            url: app.globalData.apiBase + '/ai/agent/reset',
            method: 'POST',
            header: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ' + app.globalData.token
            },
            data: { session_id: this.data.sessionId }
          });
        }
        wx.removeStorageSync('ai_agent_session_id');
        this.setData({ messages: [], sessionId: '' });
      }
    });
  },

  onBack() {
    wx.navigateBack();
  }
});
