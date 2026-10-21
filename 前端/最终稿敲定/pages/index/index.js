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
    todayDateLabel: '',
    // 每日首次进入的「添加今日待办」提示
    showDailyPrompt: false
  },

  onLoad() {
    const g = app.globalData;
    // 计算微信胶囊的右侧位置,给自定义 nav 留 padding
    let capsuleRight = 0;
    try {
      const rect = wx.getMenuButtonBoundingClientRect();
      const win = wx.getWindowInfo();
      capsuleRight = (win.windowWidth - rect.left) + 8;  // 8px 间距
    } catch (e) {}
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight,
      capsuleRight: capsuleRight
    });
  },

  onShow() {
    if (!app.globalData.token) {
      app.goLogin();
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
    // 没变就**完全跳过** —— 切 tab 不再触发 5+ 个 API
    const currentVer = app.globalData.dataVersion || 0;
    if (this.data.lastDataVer !== currentVer) {
      this.loadDashboardData();
      this.setData({ lastDataVer: currentVer });
    }
    // 注意:不再无条件 reload,避免切 tab 卡顿
  },

  // 进入首页时自动打卡(每天一次,后端去重)
  maybeAutoCheckin() {
    try {
      const d = new Date();
      const pad = (x) => String(x).padStart(2, '0');
      // 用本地时间避免 UTC 跨日
      const todayStr = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
      const lastDay = wx.getStorageSync('auto_checkin_day');
      // 同一天已经发过,跳过(避免每次切换 tab 都打)
      if (lastDay === todayStr) return;
      // 标记今天已发(立即标记,即使请求失败也不重复尝试)
      wx.setStorageSync('auto_checkin_day', todayStr);
      app.request({
        url: '/checkins',
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

  _todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  },

  /**
   * 首页数据加载。
   *
   * 改造前:6 个接口 Promise.all(外加自动打卡共 7 个请求),
   * 每个都要过一遍 JWT 校验、服务端各跑各的 SQL。
   *
   * 改造后:1 个 /dashboard 聚合接口 —— 服务端并发查 5 条轻量 SQL、
   * 整包缓存 60s,并用版本号在写操作后自动失效。
   * 失败时自动回退到旧的多请求路径,后端没升级也能正常用。
   */
  async loadDashboardData() {
    try {
      if (!app.globalData.token) return;
      const dateStr = this._todayStr();

      let dash = null;
      try {
        dash = await app.request({ url: `/dashboard?date=${dateStr}` });
      } catch (e) {
        console.warn('dashboard 聚合接口不可用,回退多请求模式:', e);
      }

      if (dash && typeof dash === 'object' && Array.isArray(dash.todos)) {
        this._applyDashboard(dash);
        return;
      }
      await this._loadDashboardLegacy(dateStr);
    } catch (e) {
      console.error('加载数据失败:', e);
    }
  },

  _applyDashboard(dash) {
    const setData = {
      todos: dash.todos || [],
      completionRate: dash.completion_rate || 0,
      todayIncome: dash.income || 0,
      todayExpense: dash.expense || 0,
      todayNet: dash.net || 0,
      streak: typeof dash.streak === 'number' ? dash.streak : 0,
      todayCalories: dash.calories || 0,
      todayChecked: !!dash.today_checked
    };
    if (dash.calorie_goal) setData.calorieGoal = dash.calorie_goal;
    if (Array.isArray(dash.layout) && dash.layout.length > 0) {
      setData.layout = dash.layout;
    }
    this.setData(setData);
    this._recomputeSections();
    this._maybeShowDailyPrompt(dash.total_today || 0);
  },

  // 兼容旧后端:聚合接口不存在时走原来的 6 请求
  async _loadDashboardLegacy(dateStr) {
    const [
      todosRes, completedRes, dailyStatsRes, streakRes, mealsRes, settingsRes
    ] = await Promise.all([
      app.request({ url: `/todos?done=false&date=${dateStr}` }).catch(() => []),
      app.request({ url: `/todos?done=true&date=${dateStr}` }).catch(() => []),
      app.request({ url: `/transactions/daily-stats?date=${dateStr}` }).catch(() => ({ income: 0, expense: 0, net: 0 })),
      app.request({ url: '/checkins/streak' }).catch(() => ({ streak: 0 })),
      app.request({ url: '/meals' }).catch(() => []),
      app.request({ url: '/user/settings' }).catch(() => ({}))
    ]);

    const todos = todosRes || [];
    const completedToday = completedRes || [];
    const totalToday = todos.length + completedToday.length;
    const dailyStats = dailyStatsRes || { income: 0, expense: 0, net: 0 };
    const streak = streakRes || { streak: 0 };
    const meals = mealsRes || [];
    const settings = settingsRes || {};
    const todayCalories = meals
      .filter(m => m.date === dateStr)
      .reduce((sum, m) => sum + (Number(m.total_calories) || 0), 0);

    const setData = {
      todos,
      completionRate: totalToday > 0 ? Math.round((completedToday.length / totalToday) * 100) : 0,
      todayIncome: dailyStats.income,
      todayExpense: dailyStats.expense,
      todayNet: dailyStats.net,
      streak: typeof streak.streak === 'number' ? streak.streak : 0,
      todayCalories
    };
    if (settings.target_calories) setData.calorieGoal = settings.target_calories;
    if (Array.isArray(settings.home_layout) && settings.home_layout.length > 0) {
      setData.layout = settings.home_layout;
    }
    this.setData(setData);
    this._recomputeSections();
    this._maybeShowDailyPrompt(todos.length + completedToday.length);
  },

  // ============================================================
  // 每日首次进入:提示添加今日待办
  // ------------------------------------------------------------
  // 三个判断,避免骚扰:
  //   1. 今天已经提示过 → 不再提示(跨页面切换、杀进程重进都不会重复)
  //   2. 今天已经有待办 → 说明已经规划过,不打扰
  //   3. 数据没加载出来(接口失败)→ 不弹,免得在错误状态下弹窗
  // ============================================================
  _maybeShowDailyPrompt(totalToday) {
    try {
      if (!app.globalData.token) return;
      if (this.data.showDailyPrompt) return;

      const today = this._todayStr();
      if (wx.getStorageSync('daily_prompt_day') === today) return;
      if (totalToday > 0) {
        // 已经有待办了,记一笔当天已提示,后续不再判断
        wx.setStorageSync('daily_prompt_day', today);
        return;
      }

      // 立刻落盘:保证「每天只弹一次」,即使被强杀也不会重弹
      wx.setStorageSync('daily_prompt_day', today);
      this.setData({ showDailyPrompt: true });
    } catch (e) {
      // storage 异常时静默跳过,不打扰主流程
    }
  },

  // 「去添加」→ 切到待办 tab,并让待办页自动弹出新增表单
  // (tabBar 页面只能用 switchTab,而 switchTab 不支持带 query 参数,
  //  所以用 storage 传一个一次性标记,待办页 onShow 消费掉)
  onDailyPromptGo() {
    this.setData({ showDailyPrompt: false });
    try {
      wx.setStorageSync('open_add_todo', 1);
    } catch (e) {}
    wx.switchTab({
      url: '/pages/todo/todo',
      fail: () => {
        try { wx.removeStorageSync('open_add_todo'); } catch (e) {}
      }
    });
  },

  // 「稍后」→ 今天不再提示
  onDailyPromptLater() {
    this.setData({ showDailyPrompt: false });
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
