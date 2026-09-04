const app = getApp();

const TYPE_META = {
  finance: { icon: '💰', label: '收支提醒' },
  diet:    { icon: '🍎', label: '饮食提醒' },
  todo:    { icon: '✓', label: '待办提醒' },
  goal:    { icon: '🎯', label: '目标提醒' },
  other:   { icon: '🔔', label: '其他提醒' }
};

const TYPE_OPTIONS = Object.keys(TYPE_META);

// 把 "HH:MM:SS" 截成 "HH:MM" 展示
const formatTime = (t) => {
  if (!t) return '08:00';
  return String(t).slice(0, 5);
};

const WD_NAMES = ['一', '二', '三', '四', '五', '六', '日'];

const weekdayLabel = (wds) => {
  if (!wds || !Array.isArray(wds) || wds.length === 0) return '每天';
  if (wds.length === 7) return '每天';
  return '每' + wds.slice().sort((a, b) => a - b).map(d => WD_NAMES[d]).join('、');
};

const enrich = (r) => {
  const meta = TYPE_META[r.type] || TYPE_META.other;
  return {
    id: r.id,
    type: r.type,
    icon: meta.icon,
    label: meta.label,
    time: formatTime(r.time),
    enabled: !!r.enabled,
    weekdays: r.weekdays || null,
    weekdayLabel: weekdayLabel(r.weekdays)
  };
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    reminders: [],
    aiAvatar: '',
    calorieGoal: 1800,
    achSummary: '',
    activeModelName: '系统默认',
    customModelCount: 0,
    showAdd: false,
    showEdit: false,
    showAvatarSheet: false,
    formData: { type: 'todo', time: '08:00', weekdays: null },
    typeOptions: TYPE_OPTIONS,
    typeLabels: Object.fromEntries(TYPE_OPTIONS.map(t => [t, TYPE_META[t].label])),
    weekdays: ['一', '二', '三', '四', '五', '六', '日'],
    wdActive: [true, true, true, true, true, true, true],
    editId: null
  },

  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });
  },

  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 3 });
    }
    this.loadReminders();
    this.loadSettings();
    this.loadAchSummary();
    this.loadAiModels();
    this.setData({ aiAvatar: wx.getStorageSync('ai_avatar') || '' });
  },

  loadAchSummary() {
    app.request({ url: '/achievements/available' })
      .then(list => {
        const unlocked = (list || []).filter(a => a.unlocked).length;
        const total = (list || []).length;
        this.setData({ achSummary: `已解锁 ${unlocked} / ${total} 个` });
      })
      .catch(() => this.setData({ achSummary: '' }));
  },

  loadAiModels() {
    app.request({ url: '/llm/models/available' })
      .then(r => {
        const models = r.models || [];
        const activeId = r.active_model_id;
        const custom = models.filter(m => m.owner_user_id);
        const active = models.find(m => m.id === activeId) || models.find(m => m.is_system_default) || models[0];
        this.setData({
          activeModelName: active ? active.name : '系统默认',
          customModelCount: custom.length
        });
      })
      .catch(() => this.setData({ activeModelName: '系统默认', customModelCount: 0 }));
  },

  onGoAiModel() {
    wx.navigateTo({ url: '/pages/settings/ai-model/ai-model' });
  },

  onGoAchievements() {
    wx.navigateTo({ url: '/pages/achievements/achievements' });
  },

  onGoStats() {
    wx.navigateTo({ url: '/pages/stats/stats' });
  },

  onGoReports() {
    wx.navigateTo({ url: '/pages/reports/reports' });
  },

  async onExportData() {
    // 1) 先查摘要
    try {
      const r = await app.request({ url: '/export/?summary=true' });
      if (r && r.summary) {
        const c = r.counts;
        const confirmed = await new Promise((resolve) => {
          wx.showModal({
            title: '确认导出全部数据',
            content: `本次将导出:\n• 待办 ${c.todos} 条\n• 目标 ${c.goals} 个\n• 收支 ${c.transactions} 笔\n• 饮食 ${c.meals} 餐\n• 提醒 ${c.reminders} 个`,
            confirmText: '导出',
            success: (m) => resolve(m.confirm)
          });
        });
        if (!confirmed) return;
      }
    } catch (e) {
      console.warn('摘要查询失败,继续导出:', e);
    }
    // 2) 下载文件
    const url = `${app.globalData.apiBase}/export/?`;
    wx.showLoading({ title: '生成文件中...' });
    wx.downloadFile({
      url: url,
      header: { 'Authorization': 'Bearer ' + app.globalData.token },
      success: (res) => {
        wx.hideLoading();
        if (res.statusCode === 200) {
          wx.showModal({
            title: '导出成功',
            content: `文件已下载到: ${res.tempFilePath}`,
            showCancel: false,
            confirmText: '打开',
            success: () => {
              wx.openDocument({ filePath: res.tempFilePath, showMenu: true });
            }
          });
        } else {
          wx.showToast({ title: '导出失败', icon: 'none' });
        }
      },
      fail: (err) => {
        wx.hideLoading();
        console.error('下载失败', err);
        wx.showToast({ title: '下载失败', icon: 'none' });
      }
    });
  },

  async onExportTransactions() {
    // 1) 摘要确认
    try {
      const r = await app.request({ url: '/export/transactions?format=csv&summary=true' });
      if (r && r.summary) {
        const confirmed = await new Promise((resolve) => {
          wx.showModal({
            title: '确认导出账单',
            content: `本次将导出 ${r.count} 笔:\n• 收入 ¥${r.income.toFixed(2)}\n• 支出 ¥${r.expense.toFixed(2)}`,
            confirmText: '导出',
            success: (m) => resolve(m.confirm)
          });
        });
        if (!confirmed) return;
      }
    } catch (e) {
      console.warn('账单摘要查询失败,继续导出:', e);
    }
    // 2) 下载
    const url = `${app.globalData.apiBase}/export/transactions?format=csv`;
    wx.showLoading({ title: '生成文件中...' });
    wx.downloadFile({
      url: url,
      header: { 'Authorization': 'Bearer ' + app.globalData.token },
      success: (res) => {
        wx.hideLoading();
        if (res.statusCode === 200) {
          wx.openDocument({ filePath: res.tempFilePath, showMenu: true });
          wx.showToast({ title: '已打开', icon: 'success' });
        } else {
          wx.showToast({ title: '导出失败', icon: 'none' });
        }
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: '下载失败', icon: 'none' });
      }
    });
  },

  loadSettings() {
    app.request({ url: '/user/settings' })
      .then(s => {
        if (s && s.target_calories) {
          this.setData({ calorieGoal: s.target_calories });
        }
      })
      .catch(() => {});
  },

  // 饮食目标输入回车/失焦时保存
  onCalorieGoalChange(e) {
    const val = parseInt(e.detail.value, 10);
    if (isNaN(val) || val < 500 || val > 10000) {
      wx.showToast({ title: '请输入 500-10000 之间的数', icon: 'none' });
      // 还原
      this.loadSettings();
      return;
    }
    if (val === this.data.calorieGoal) return;
    app.request({
      url: '/user/settings',
      method: 'PUT',
      data: { target_calories: val }
    }).then(() => {
      this.setData({ calorieGoal: val });
      wx.showToast({ title: '已保存', icon: 'success' });
    }).catch(() => {
      wx.showToast({ title: '保存失败', icon: 'none' });
      this.loadSettings();
    });
  },

  loadReminders() {
    app.request({ url: '/reminders' })
      .then(list => {
        // 限长:只保留最近 20 条,避免 setData 累积过大
        this.setData({ reminders: (list || []).slice(0, 20).map(enrich) });
      })
      .catch(() => this.setData({ reminders: [] }));
  },

  // 开关：启用/停用提醒
  onToggle(e) {
    const { id, enabled } = e.currentTarget.dataset;
    app.request({ url: `/reminders/${id}`, method: 'PUT', data: { enabled: !enabled } })
      .then(() => this.loadReminders())
      .catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
  },

  // 删除
  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认删除',
      content: '删除后无法恢复',
      confirmColor: '#8DA9C4',
      success: (res) => {
        if (res.confirm) {
          app.request({ url: `/reminders/${id}`, method: 'DELETE' })
            .then(() => {
              this.loadReminders();
              wx.showToast({ title: '已删除', icon: 'success' });
            })
            .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
        }
      }
    });
  },

  // 点击条目 → 打开编辑
  onTapReminder(e) {
    const id = e.currentTarget.dataset.id;
    const item = this.data.reminders.find(r => r.id === id);
    if (!item) return;
    const wd = item.weekdays || null;
    const wdActive = [false, false, false, false, false, false, false];
    if (wd) wd.forEach(i => { if (i >= 0 && i < 7) wdActive[i] = true; });
    this.setData({
      showEdit: true,
      showAdd: false,
      editId: id,
      formData: { type: item.type, time: item.time, weekdays: wd },
      wdActive: wdActive
    });
  },

  // "+ 添加提醒" 入口
  onAddReminder() {
    this.setData({
      showAdd: true,
      showEdit: false,
      editId: null,
      formData: { type: 'todo', time: '08:00', weekdays: null },
      wdActive: [true, true, true, true, true, true, true]
    });
  },

  onCancel() {
    this.setData({ showAdd: false, showEdit: false });
  },

  stopPropagation() {},

  onTypeSelect(e) {
    this.setData({ 'formData.type': e.currentTarget.dataset.value });
  },

  onTimeChange(e) {
    this.setData({ 'formData.time': e.detail.value });
  },

  onToggleWeekday(e) {
    const idx = Number(e.currentTarget.dataset.value);
    const cur = (this.data.formData.weekdays || []).map(Number);
    const pos = cur.indexOf(idx);
    let next;
    if (pos >= 0) {
      next = cur.filter(d => d !== idx);
    } else {
      next = [...cur, idx].sort((a, b) => a - b);
    }
    // 全选 = 等同于空(每天)
    if (next.length === 7) next = null;
    // 直接生成 wdActive 数组,wxml 用 {{wdActive[wd]}} 渲染
    const wdActive = [false, false, false, false, false, false, false];
    if (next) {
      next.forEach(i => { if (i >= 0 && i < 7) wdActive[i] = true; });
    }
    this.setData({
      'formData.weekdays': next,
      wdActive: wdActive
    });
  },

  onSave() {
    const { formData, isEditMode, editId } = this.data;
    // 后端 time 字段是 TIME 类型，发送 "HH:MM:SS"
    const timeStr = formData.time.length === 5 ? `${formData.time}:00` : formData.time;

    if (this.data.showEdit && editId) {
      app.request({
        url: `/reminders/${editId}`,
        method: 'PUT',
        data: { type: formData.type, time: timeStr, weekdays: formData.weekdays }
      }).then(() => {
        this.loadReminders();
        this.setData({ showEdit: false });
        wx.showToast({ title: '已更新', icon: 'success' });
      }).catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
    } else {
      app.request({
        url: '/reminders',
        method: 'POST',
        data: { type: formData.type, time: timeStr, enabled: true, weekdays: formData.weekdays }
      }).then(() => {
        this.loadReminders();
        this.setData({ showAdd: false });
        wx.showToast({ title: '已添加', icon: 'success' });
      }).catch(() => wx.showToast({ title: '添加失败', icon: 'none' }));
    }
  },

  // 弹出 AI 头像操作菜单（选择 / 重置）
  onShowAvatarActions() {
    if (this.data.aiAvatar) {
      // 已自定义，给两个选项
      wx.showActionSheet({
        itemList: ['从相册/拍照 重新选择', '恢复默认头像'],
        success: (res) => {
          if (res.tapIndex === 0) this.onChooseAiAvatar();
          else if (res.tapIndex === 1) this.onResetAiAvatar();
        }
      });
    } else {
      // 未自定义，直接选择
      this.onChooseAiAvatar();
    }
  },

  // 选择并保存 AI 头像
  onChooseAiAvatar() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempFile = res.tempFiles && res.tempFiles[0] && res.tempFiles[0].tempFilePath;
        if (!tempFile) return;
        wx.getFileSystemManager().readFile({
          filePath: tempFile,
          encoding: 'base64',
          success: (data) => {
            const base64 = 'data:image/jpeg;base64,' + data.data;
            try {
              wx.setStorageSync('ai_avatar', base64);
              this.setData({ aiAvatar: base64 });
              wx.showToast({ title: '头像已更新', icon: 'success' });
            } catch (e) {
              wx.showToast({ title: '图片过大，请换一张', icon: 'none' });
            }
          },
          fail: () => wx.showToast({ title: '读取图片失败', icon: 'none' })
        });
      },
      fail: () => { /* 用户取消，无需提示 */ }
    });
  },

  // 恢复默认头像
  onResetAiAvatar() {
    wx.removeStorageSync('ai_avatar');
    this.setData({ aiAvatar: '' });
    wx.showToast({ title: '已恢复默认', icon: 'success' });
  },

  onLogout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需重新登录',
      confirmColor: '#8DA9C4',
      success: (res) => {
        if (res.confirm) {
          app.globalData.token = null;
          wx.removeStorageSync('token');
          wx.removeStorageSync('userInfo');
          wx.reLaunch({ url: '/pages/login/login' });
        }
      }
    });
  }
});
