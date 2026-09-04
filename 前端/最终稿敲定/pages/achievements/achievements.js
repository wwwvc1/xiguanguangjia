const app = getApp();

const fmtTime = (s) => {
  if (!s) return '';
  return String(s).slice(0, 10);
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    achievements: [],
    unlockedCount: 0,
    totalCount: 0,
    progressPercent: 0
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
    this.loadAchievements();
  },

  loadAchievements() {
    app.request({ url: '/achievements/available' })
      .then(list => {
        const arr = (list || []).map(a => ({
          ...a,
          unlocked_at: fmtTime(a.unlocked_at)
        }));
        const unlockedCount = arr.filter(a => a.unlocked).length;
        const totalCount = arr.length;
        const progressPercent = totalCount > 0 ? Math.round((unlockedCount / totalCount) * 100) : 0;
        this.setData({
          achievements: arr,
          unlockedCount,
          totalCount,
          progressPercent
        });
      })
      .catch(() => this.setData({ achievements: [] }));
  },

  goBack() {
    wx.navigateBack();
  }
});
