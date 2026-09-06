const API_BASE = "http://127.0.0.1:8000/api"

function request(options) {
  const app = getApp();
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBase}${options.url}`,
      method: options.method || 'GET',
      data: options.data || {},
      header: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${app.globalData.token}`,
        ...options.header
      },
      success: (res) => {
        // 后端直接返回数据，不包 {code, data}
        const data = res.data;
        if ((res.statusCode === 200 || res.statusCode === 201) && data) {
          // 如果有 code 字段，走统一响应格式
          if (data.code !== undefined) {
            if (data.code === 200) {
              resolve(data.data);
            } else if (data.code === 401) {
              wx.removeStorageSync('token');
              wx.redirectTo({ url: '/pages/login/login' });
              reject(new Error('未授权'));
            } else {
              reject(new Error(data.message || '请求失败'));
            }
          } else {
            // 直接返回数据
            resolve(data);
          }
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.redirectTo({ url: '/pages/login/login' });
          reject(new Error('未授权'));
        } else {
          const err = new Error(data.detail || data.message || `请求失败 (${res.statusCode})`);
          err.statusCode = res.statusCode;
          err.detail = data.detail || data.message;
          reject(err);
        }
      },
      fail: (err) => {
        wx.showToast({ title: '网络错误', icon: 'none' });
        reject(err);
      }
    });
  });
}

App({
  globalData: {
    dataVersion: 0,  // 每次 CRUD 后自增,首页 onShow 检查是否变化

    statusBarHeight: 44,
    navHeight: 88,
    tabBarHeight: 120,
    apiBase: API_BASE,
    token: null,

    // 用户资料(头像 / 昵称)— 启动时从 storage 恢复,后端就绪后用真实接口同步
    userInfo: {
      nickname: '我',
      avatar: ''  // 头像 base64 或 url,空字符串 = 默认
    }
  },
  onLaunch() {
    const sys = wx.getSystemInfoSync();
    this.globalData.statusBarHeight = sys.statusBarHeight;
    this.globalData.navHeight = sys.statusBarHeight + 44;
    const safeBottom = sys.screenHeight - sys.safeArea.bottom;
    this.globalData.tabBarHeight = safeBottom + 100;
    // 从本地存储恢复 token
    const token = wx.getStorageSync('token');
    if (token) {
      this.globalData.token = token;
    } else {
      // 没有 token，跳转登录页
      wx.redirectTo({ url: '/pages/login/login' });
    }
    // 恢复用户资料(头像 / 昵称)— 即使未登录也保留(降级为默认)
    this._restoreUserInfo();
  },
  // 内部:从 storage 恢复 userInfo 到 globalData
  _restoreUserInfo() {
    try {
      const stored = wx.getStorageSync('userInfo');
      if (stored && typeof stored === 'object') {
        this.globalData.userInfo = {
          nickname: stored.nickname || '我',
          avatar: stored.avatar || ''
        };
      } else {
        // 没有就放默认值
        wx.setStorageSync('userInfo', this.globalData.userInfo);
      }
    } catch (e) {
      // 静默失败,保留默认
    }
  },
  // 全局更新 userInfo(设置页保存后调用,其他页 onShow 可重读)
  setUserInfo(partial) {
    this.globalData.userInfo = {
      ...this.globalData.userInfo,
      ...partial
    };
    try {
      wx.setStorageSync('userInfo', this.globalData.userInfo);
    } catch (e) { /* storage 满时静默失败 */ }
  },
  // 全局数据版本号:任何 CRUD 后自增,首页 onShow 检测到变化就重新拉数据
  bumpDataVersion() {
    this.globalData.dataVersion = (this.globalData.dataVersion || 0) + 1;
  },
  request: request  // 暴露给所有页面使用
});
