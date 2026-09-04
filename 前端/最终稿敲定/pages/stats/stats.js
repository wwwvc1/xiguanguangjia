const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    summary: {},
    trend: [],
    weekdayStats: [],
    txTop5: [],
    correlations: []
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
    this.loadAll();
  },

  loadAll() {
    Promise.all([
      app.request({ url: '/stats/patterns' }).catch(() => null),
      app.request({ url: '/stats/correlation' }).catch(() => null)
    ]).then(([patterns, corr]) => {
      if (patterns) {
        const trend = (patterns.completion_trend || []).map(t => ({
          ...t,
          dateLabel: t.date.slice(5)  // MM-DD
        }));
        const txAll = (patterns.tx_category_stats || []).filter(t => t.type === 'expense');
        txAll.sort((a, b) => b.total - a.total);
        this.setData({
          summary: patterns.summary || {},
          trend,
          weekdayStats: patterns.todo_weekday_stats || [],
          txTop5: txAll.slice(0, 5)
        });
      }
      if (corr && corr.insights) {
        this.setData({ correlations: corr.insights });
      }
    });
  },

  goBack() {
    wx.navigateBack();
  }
});
