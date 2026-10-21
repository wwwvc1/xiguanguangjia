const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    isLoading: false,
    loginMode: 'wechat',      // 'wechat' | 'password'
    isRegisterMode: false,    // false = 登录, true = 注册
    form: { username: '', password: '', nickname: '' }
  },

  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });
    // 只有内存和 storage 都有 token 才算已登录,避免残留全局 token
    // 把用户从登录页又弹回首页(之前 401 死循环的根因之一)
    if (app.globalData.token && wx.getStorageSync('token')) {
      wx.switchTab({ url: '/pages/index/index' });
    } else {
      app.clearSession();
    }
  },

  // 切换登录/注册模式
  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({
      loginMode: mode,
      isRegisterMode: false,
      form: { username: '', password: '', nickname: '' }
    });
  },

  // 切换登录 vs 注册
  toggleRegisterMode() {
    this.setData({
      isRegisterMode: !this.data.isRegisterMode,
      form: { username: '', password: '', nickname: '' }
    });
  },

  // 输入框双向绑定
  onInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`form.${field}`]: e.detail.value });
  },

  // ===== 微信登录 =====
  onWechatLogin() {
    if (this.data.isLoading) return;
    this.setData({ isLoading: true });

    wx.login({
      success: (res) => {
        if (res.code) {
          this.doWechatLogin(res.code);
        } else {
          wx.showToast({ title: '登录失败,请重试', icon: 'none' });
          this.setData({ isLoading: false });
        }
      },
      fail: () => {
        wx.showToast({ title: '登录失败,请重试', icon: 'none' });
        this.setData({ isLoading: false });
      }
    });
  },

  doWechatLogin(code) {
    wx.request({
      url: app.globalData.apiBase + '/auth/login',
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { code },
      success: (res) => this._handleAuthResponse(res, '登录成功'),
      fail: () => {
        wx.showToast({ title: '网络错误,请检查后端', icon: 'none' });
        this.setData({ isLoading: false });
      }
    });
  },

  // ===== 账号密码登录/注册 =====
  onPasswordSubmit() {
    if (this.data.isLoading) return;
    const { username, password, nickname } = this.data.form;
    if (!username || username.length < 3) {
      wx.showToast({ title: '账号至少 3 位', icon: 'none' });
      return;
    }
    if (!password || password.length < 6) {
      wx.showToast({ title: '密码至少 6 位', icon: 'none' });
      return;
    }
    this.setData({ isLoading: true });

    const endpoint = this.data.isRegisterMode ? '/auth/register' : '/auth/login-with-password';
    const body = this.data.isRegisterMode
      ? { username, password, nickname: nickname || undefined }
      : { username, password };

    wx.request({
      url: app.globalData.apiBase + endpoint,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: body,
      success: (res) => this._handleAuthResponse(res, this.data.isRegisterMode ? '注册成功' : '登录成功'),
      fail: () => {
        wx.showToast({ title: '网络错误,请检查后端', icon: 'none' });
        this.setData({ isLoading: false });
      }
    });
  },

  // 统一处理登录/注册响应
  _handleAuthResponse(res, successText) {
    const data = res.data || {};
    if (data.access_token) {
      app.setToken(data);
      wx.showToast({ title: successText, icon: 'success' });
      setTimeout(() => {
        wx.switchTab({ url: '/pages/index/index' });
      }, 600);
    } else {
      wx.showToast({ title: data.detail || '登录失败', icon: 'none' });
      this.setData({ isLoading: false });
    }
  }
});
