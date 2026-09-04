const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    isLoading: false
  },

  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });

    // 如果已登录，直接跳首页
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/index/index' });
    }
  },

  onWechatLogin() {
    if (this.data.isLoading) return;
    this.setData({ isLoading: true });

    // 获取微信登录 code
    wx.login({
      success: (res) => {
        if (res.code) {
          this.doLogin(res.code);
        } else {
          wx.showToast({ title: '登录失败，请重试', icon: 'none' });
          this.setData({ isLoading: false });
        }
      },
      fail: () => {
        wx.showToast({ title: '登录失败，请重试', icon: 'none' });
        this.setData({ isLoading: false });
      }
    });
  },

  doLogin(code) {
    wx.request({
      url: app.globalData.apiBase + '/auth/login',
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { code: code },
      success: (res) => {
        const data = res.data;
        // 后端直接返回 {access_token, user_id, nickname, avatar}
        if (data.access_token) {
          app.globalData.token = data.access_token;
          app.globalData.userId = data.user_id;
          app.globalData.nickname = data.nickname;
          app.globalData.avatar = data.avatar;
          wx.setStorageSync('token', data.access_token);
          wx.setStorageSync('userInfo', { user_id: data.user_id, nickname: data.nickname, avatar: data.avatar });

          wx.showToast({ title: '登录成功', icon: 'success' });
          setTimeout(() => {
            wx.switchTab({ url: '/pages/index/index' });
          }, 800);
        } else {
          wx.showToast({ title: data.detail || '登录失败', icon: 'none' });
          this.setData({ isLoading: false });
        }
      },
      fail: (err) => {
        console.error('登录请求失败:', err);
        wx.showToast({ title: '网络错误，请检查后端', icon: 'none' });
        this.setData({ isLoading: false });
      }
    });
  }
});
