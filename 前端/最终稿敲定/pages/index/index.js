const app = getApp();
const user = require('../../utils/user.js');

const ALL_SECTIONS = [
  { key: 'finance', name: '今日结余' },
  { key: 'diet',    name: '今日饮食' },
  { key: 'todo',    name: '今日待办' }
];

const DEFAULT_LAYOUT = ['finance', 'diet', 'todo'];

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    todos: [],
    todayIncome: 0,
    todayExpense: 0,
    todayNet: 0,
    todayCalories: 0,
    calorieGoal: 1800,
    completionRate: 0,
    showTodayDetail: false,
    todayTransactions: [],
    editMode: false,
    layout: [...DEFAULT_LAYOUT],
    visibleSections: [],
    hiddenSections: [],
    topInsight: '',
    allInsights: [],
    lastDataVer: -1,
    streak: 0,
    userInfo: { nickname: '我', avatar: '' },
    todayDateLabel: ''
  },

  onLoad() {
    const g = app.globalData;
    // 计算微信胶囊的右侧位置,给自定义 nav 留 padding
    let capsuleRight = 0;
    try {
      const rect = wx.getMenuButtonBoundingClientRect();
      const sysInfo = wx.getSystemInfoSync();
      capsuleRight = (sysInfo.windowWidth - rect.left) + 8;  // 8px 间距
    } catch (e) {}
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight,
      capsuleRight: capsuleRight
    });
  },

  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({selected: 0});
    }
    // 自动打卡(每天进首页时触发,后端去重)
    this.maybeAutoCheckin();
    // 同步用户资料(头像/昵称)
    const dateLabel = (() => {
      const d = new Date();
      const weekdays = ['周日','周一','周二','周三','周四','周五','周六'];
      return `${d.getMonth() + 1}月${d.getDate()}日 · ${weekdays[d.getDay()]}`;
    })();
    this.setData({
      userInfo: user.getUserInfo(),
      todayDateLabel: dateLabel
    });
    // 数据版本号变化 → 重新拉数据(由其他页面 CRUD 触发)
    const currentVer = app.globalData.dataVersion || 0;
    if (this.data.lastDataVer !== currentVer) {
      this.loadDashboardData();
      this.setData({ lastDataVer: currentVer });
    } else {
      this.loadDashboardData();
    }
  },

  // 进入首页时自动打卡(每天一次,后端去重)
  maybeAutoCheckin() {
    try {
      const todayStr = new Date().toISOString().slice(0, 10);
      const lastDay = wx.getStorageSync('auto_checkin_day');
      // 同一天已经发过,跳过(避免每次切换 tab 都打)
      if (lastDay === todayStr) return;
      // 标记今天已发(立即标记,即使请求失败也不重复尝试)
      wx.setStorageSync('auto_checkin_day', todayStr);
      app.request({
        url: '/checkins/',
        method: 'POST',
        data: { auto: true }
      }).then(r => {
        if (r && r.streak !== undefined) {
          this.setData({ streak: r.streak });
          app.bumpDataVersion();
        }
      }).catch(() => {
        // 静默失败(不打扰用户)
      });
    } catch (e) {}
  },

  // 首页底部 streak hero 点击 → 跳转到打卡页
  goCheckin() {
    wx.navigateTo({ url: '/pages/checkin/checkin' });
  },

  async loadDashboardData() {
    try {
      if (!app.globalData.token) return;

      const today = new Date();
      const dateStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

      const todos = await app.request({ url: `/todos/?done=false&date=${dateStr}` });
      const completedToday = await app.request({ url: `/todos/?done=true&date=${dateStr}` });

      const totalToday = (todos || []).length + (completedToday || []).length;
      const completionRate = totalToday > 0
        ? Math.round(((completedToday || []).length / totalToday) * 100)
        : 0;
      this.setData({ todos, completionRate });

      const dailyStats = await app.request({ url: `/transactions/daily-stats?date=${dateStr}` });
      this.setData({
        todayIncome: dailyStats.income,
        todayExpense: dailyStats.expense,
        todayNet: dailyStats.net
      });

      // 主动拉 streak(不依赖 maybeAutoCheckin 的副作用,确保首页 streak 始终是最新的)
      try {
        const streak = await app.request({ url: '/checkins/streak' });
        if (streak && typeof streak.streak === 'number') {
          this.setData({ streak: streak.streak });
        }
      } catch (e) {
        console.warn('加载 streak 失败:', e);
      }

      const meals = await app.request({ url: '/meals/' });
      const todayCalories = (meals || [])
        .filter(m => m.date === dateStr)
        .reduce((sum, m) => sum + (Number(m.total_calories) || 0), 0);
      this.setData({ todayCalories });

      try {
        const settings = await app.request({ url: '/user/settings' });
        if (settings && settings.target_calories) {
          this.setData({ calorieGoal: settings.target_calories });
        }
        if (settings && Array.isArray(settings.home_layout) && settings.home_layout.length > 0) {
          this.setData({ layout: settings.home_layout });
        }
      } catch (e) {
        console.warn('加载用户设置失败:', e);
      }
      this._recomputeSections();

      // 异步加载 AI 建议(不阻塞主页)
      this._loadInsights();
    } catch (e) {
      console.error('加载数据失败:', e);
    }
  },

  onCheckin() {
    // 已禁用打卡入口
  },

  _loadInsights() {
    app.request({ url: '/ai/insights', method: 'POST' })
      .then(res => {
        const suggestions = res && res.suggestions ? res.suggestions : [];
        this.setData({
          topInsight: suggestions[0] || '',
          allInsights: suggestions
        });
      })
      .catch(() => this.setData({ topInsight: '', allInsights: [] }));
  },

  onShowAllInsights() {
    const list = (this.data.allInsights || []).join('\n\n');
    if (list) {
      wx.showModal({
        title: '💡 AI 个性化建议',
        content: list,
        showCancel: false,
        confirmText: '知道了'
      });
      return;
    }
    // 没有建议:先拉,再显
    wx.showLoading({ title: '正在分析…' });
    this._loadInsights();
    // 等最多 8 秒
    let waited = 0;
    const tick = setInterval(() => {
      waited += 500;
      const newList = (this.data.allInsights || []).join('\n\n');
      if (newList) {
        clearInterval(tick);
        wx.hideLoading();
        wx.showModal({
          title: '💡 AI 个性化建议',
          content: newList,
          showCancel: false,
          confirmText: '知道了'
        });
      } else if (waited >= 8000) {
        clearInterval(tick);
        wx.hideLoading();
        wx.showToast({ title: '暂无建议,稍后再试', icon: 'none' });
      }
    }, 500);
  },

  _recomputeSections() {
    const layout = this.data.layout.filter(k => ALL_SECTIONS.some(s => s.key === k));
    const visibleSections = layout.map(key => ALL_SECTIONS.find(s => s.key === key)).filter(Boolean);
    const hiddenSections = ALL_SECTIONS.filter(s => !layout.includes(s.key));
    this.setData({ visibleSections, hiddenSections });
  },

  onToggleEdit() {
    const nextMode = !this.data.editMode;
    if (nextMode) {
      this.setData({ editMode: true });
    } else {
      // 退出编辑模式 → 自动保存
      this._saveLayout();
      this.setData({ editMode: false });
    }
  },

  onMoveUp(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx <= 0) return;
    const layout = [...this.data.layout];
    [layout[idx-1], layout[idx]] = [layout[idx], layout[idx-1]];
    this.setData({ layout });
    this._recomputeSections();
  },

  onMoveDown(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx >= this.data.layout.length - 1) return;
    const layout = [...this.data.layout];
    [layout[idx], layout[idx+1]] = [layout[idx+1], layout[idx]];
    this.setData({ layout });
    this._recomputeSections();
  },

  onHideSection(e) {
    const key = e.currentTarget.dataset.key;
    const layout = this.data.layout.filter(k => k !== key);
    this.setData({ layout });
    this._recomputeSections();
  },

  onRestoreSection(e) {
    const key = e.currentTarget.dataset.key;
    const layout = [...this.data.layout, key];
    this.setData({ layout });
    this._recomputeSections();
  },

  _saveLayout() {
    app.request({
      url: '/user/settings',
      method: 'PUT',
      data: { home_layout: this.data.layout }
    }).then(() => {
      wx.showToast({ title: '已保存', icon: 'success' });
      app.bumpDataVersion();
    }).catch(() => {
      wx.showToast({ title: '保存失败', icon: 'none' });
    });
  },

  toggleTodo(e) {
    const id = e.currentTarget.dataset.id;
    const todo = this.data.todos.find(t => t.id === id);
    if (!todo) return;
    const todos = this.data.todos.map(t =>
      t.id === id ? { ...t, done: !t.done } : t
    );
    this.setData({ todos });
    app.request({
      url: `/todos/${id}`,
      method: 'PUT',
      data: { done: !todo.done }
    }).then(() => {
      app.bumpDataVersion();
    }).catch(err => {
      console.error('更新待办失败:', err);
      this.setData({ todos: this.data.todos });
    });
  },

  goPage(e) {
    const url = e.currentTarget.dataset.url;
    const tabBarPages = ['/pages/index/index', '/pages/todo/todo', '/pages/ai/ai', '/pages/settings/settings'];
    if (tabBarPages.includes(url)) {
      wx.switchTab({url});
    } else {
      wx.navigateTo({url});
    }
  },
  showTodayDetail() {
    app.request({ url: '/transactions/today' }).then(transactions => {
      this.setData({
        showTodayDetail: true,
        todayTransactions: transactions.map(t => ({
          ...t,
          icon: {'餐饮':'🍜','交通':'🚇','工资':'💼','购物':'🛒','娱乐':''}[t.category] || '',
          title: t.category,
          desc: t.description || ''
        }))
      });
    }).catch(() => {
      this.setData({ showTodayDetail: true, todayTransactions: [] });
    });
  },
  hideTodayDetail() {
    this.setData({ showTodayDetail: false });
  },
  stopPropagation() {},

  goSettings() {
    wx.switchTab({url: '/pages/settings/settings'});
  },

  onFabTap() {
    wx.navigateTo({url: '/pages/tasks/tasks'});
  }
});
