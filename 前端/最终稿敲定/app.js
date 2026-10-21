// ------------------------------------------------------------
// 后端地址(模拟器 / 真机自动切换)
// ------------------------------------------------------------
// 手机上的 127.0.0.1 指**手机自己**,永远连不到电脑,所以两端地址不同:
//
//   模拟器(代码跑在电脑上)   → 127.0.0.1
//   真机调试 / 预览(跑在手机上) → 电脑的局域网 IP
//
// 运行时用 platform 自动判断,不用手动切。
//
// ⚠️ 换网络 / 路由器重启后局域网 IP 可能会变(192.168.0.101 是 DHCP 分配的),
//    变了就改下面这一行。用 ipconfig 查,或看 start_backend.ps1 启动时打印的地址。
//    建议在路由器里给这台电脑绑定固定 IP,就不用再管了。
//
// 临时覆盖(不重启也能生效,Console 里执行):
//     wx.setStorageSync('api_base', 'http://192.168.0.101:8000/api')
//     getApp().applyApiBase()
//     // 清除覆盖: wx.removeStorageSync('api_base'); getApp().applyApiBase()
const LOCAL_BASE = "http://127.0.0.1:8000/api"
const LAN_BASE = "http://192.168.0.101:8000/api"

function isDevtools() {
  try {
    // getDeviceInfo 需要基础库 2.20.1+,老的用 getSystemInfoSync 兜底
    const platform = wx.getDeviceInfo
      ? wx.getDeviceInfo().platform
      : wx.getSystemInfoSync().platform
    return platform === 'devtools'
  } catch (e) {
    return true   // 判断不出来就当模拟器,至少不会把真机地址给本机用
  }
}

function normalizeBase(base) {
  return String(base).replace(/\/+$/, '')
}

function resolveApiBase() {
  try {
    const override = wx.getStorageSync('api_base')
    if (override && typeof override === 'string' && /^https?:\/\//.test(override)) {
      return normalizeBase(override)
    }
  } catch (e) { /* storage 不可用时走默认逻辑 */ }
  return normalizeBase(isDevtools() ? LOCAL_BASE : LAN_BASE)
}

// 并发 401 时只跳一次登录页,避免多接口同时失败导致重复 reLaunch
let loginNavPending = false;

// 原始请求:不带任何 401 兜底逻辑(内部使用,避免递归)
function send(options, token) {
  const app = getApp();
  const header = Object.assign(
    { 'Content-Type': 'application/json' },
    token ? { 'Authorization': `Bearer ${token}` } : {},
    options.header || {}
  );
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.apiBase}${options.url}`,
      method: options.method || 'GET',
      data: options.data || {},
      header,
      success: resolve,
      fail: (err) => {
        // 打日志不受 silent 开关影响:「网络错误」时最需要知道请求打到哪个地址。
        // 真机上如果这里还是 127.0.0.1,说明 api_base 没切过去。
        console.error(
          '[request] 失败 ' + (options.method || 'GET') + ' ' +
          app.globalData.apiBase + options.url + ' → ' +
          ((err && err.errMsg) || err)
        );
        if (!options.silent) wx.showToast({ title: '网络错误', icon: 'none' });
        reject(err);
      }
    });
  });
}

// 统一解析响应:兼容「后端直接返回数据」和 {code, data} 两种格式
function unwrap(res) {
  const data = res.data;
  const statusCode = res.statusCode;

  if (data && typeof data === 'object' && data.code !== undefined) {
    if (data.code === 200) return data.data;
    const err = new Error(data.message || '请求失败');
    err.statusCode = data.code;
    throw err;
  }
  if (statusCode >= 200 && statusCode < 300) return data;

  const detail = data && (data.detail || data.message);
  const err = new Error(
    typeof detail === 'string' ? detail : `请求失败 (${statusCode})`
  );
  err.statusCode = statusCode;
  err.detail = detail;
  throw err;
}

function unauthorizedError() {
  const err = new Error('未授权,请重新登录');
  err.statusCode = 401;
  return err;
}

/**
 * 全局请求封装
 * options: { url, method, data, header, silent, noAuthRetry }
 * 401 处理:先尝试一次静默重登(并发只发一次),成功则自动重试本次请求;
 *           失败才清理会话并跳登录页。这样过期/换了 SECRET_KEY 的旧 token
 *           不会把首页刷成一片 401,也不会在登录页和首页之间弹来弹去。
 */
function request(options) {
  const app = getApp();
  return send(options, app.globalData.token).then((res) => {
    if (res.statusCode !== 401 || options.noAuthRetry) return unwrap(res);

    return app.recoverSession()
      .then((ok) => {
        if (!ok) {
          app.goLogin();
          throw unauthorizedError();
        }
        return send(options, app.globalData.token);
      })
      .then(unwrap);
  });
}

App({
  globalData: {
    dataVersion: 0,  // 每次 CRUD 后自增,首页 onShow 检查是否变化

    statusBarHeight: 44,
    navHeight: 88,
    tabBarHeight: 120,
    apiBase: resolveApiBase(),
    token: null,
    userId: null,

    // 用户资料(头像 / 昵称)— 启动时从 storage 恢复,后端就绪后用真实接口同步
    userInfo: {
      nickname: '我',
      avatar: ''  // 头像 base64 或 url,空字符串 = 默认
    }
  },
  onLaunch() {
    // 兼容不同基础库:优先 getWindowInfo(必含 statusBarHeight),降级 getSystemInfoSync
    let statusBarHeight = 44;
    try {
      const win = wx.getWindowInfo();
      if (win && typeof win.statusBarHeight === 'number') {
        statusBarHeight = win.statusBarHeight;
      }
    } catch (e) {}
    if (!statusBarHeight) {
      try {
        const sys = wx.getSystemInfoSync();
        statusBarHeight = sys.statusBarHeight || 44;
      } catch (e) {}
    }
    this.globalData.statusBarHeight = statusBarHeight;
    this.globalData.navHeight = statusBarHeight + 44;

    // 底部安全区高度
    let safeBottom = 20;
    try {
      const win = wx.getWindowInfo();
      const appBase = wx.getAppBaseInfo();
      safeBottom = (win.screenHeight || 0) - (appBase.safeArea?.bottom || win.screenHeight);
      if (safeBottom < 0) safeBottom = 0;
    } catch (e) {}
    this.globalData.tabBarHeight = safeBottom + 100;

    // 后端地址:允许用 storage 里的 api_base 覆盖(真机调试换局域网 IP 用)
    this.applyApiBase();

    // 从本地存储恢复 token(内存和 storage 必须保持一致)
    this.globalData.token = wx.getStorageSync('token') || null;
    // 恢复用户资料(头像 / 昵称)— 即使未登录也保留(降级为默认)
    this._restoreUserInfo();
  },
  // 小程序切回前台时刷新后端地址:
  // 真机调试时在 Console 改完 api_base,把小程序切后台再回来就生效了。
  onShow() {
    this.applyApiBase();
  },

  // 重新解析后端地址。改完 storage 里的 api_base 后调用它即可生效,
  // 不用重新编译;不调用的话,下次小程序切回前台(onShow)也会自动刷新。
  applyApiBase() {
    const base = resolveApiBase();
    this.globalData.apiBase = base;
    return base;
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
  // ===== 会话管理 =====

  // 登录/注册/静默重登成功后统一写 token(内存 + storage)
  setToken(payload) {
    if (!payload || !payload.access_token) return false;
    this.globalData.token = payload.access_token;
    this.globalData.userId = payload.user_id;
    try {
      wx.setStorageSync('token', payload.access_token);
      wx.setStorageSync('userInfo', {
        user_id: payload.user_id,
        nickname: payload.nickname || this.globalData.userInfo.nickname || '我',
        avatar: payload.avatar || this.globalData.userInfo.avatar || ''
      });
    } catch (e) {}
    this._restoreUserInfo();
    return true;
  },

  // 只清会话(内存 + storage),不动用户资料
  clearSession() {
    this.globalData.token = null;
    this.globalData.userId = null;
    try { wx.removeStorageSync('token'); } catch (e) {}
  },

  // 跳登录页:任何页面都能用(reLaunch 能关闭 tabBar 页,redirectTo 不行)
  goLogin() {
    this.clearSession();
    let route = '';
    try {
      const pages = getCurrentPages();
      const current = pages && pages.length ? pages[pages.length - 1] : null;
      route = (current && (current.route || current.__route__)) || '';
    } catch (e) {}
    if (route === 'pages/login/login') return;
    if (loginNavPending) return;
    loginNavPending = true;
    wx.reLaunch({
      url: '/pages/login/login',
      complete: () => { loginNavPending = false; }
    });
  },

  // 401 时静默重新登录(微信 code → /auth/login),并发只发一次
  recoverSession() {
    if (this._recovering) return this._recovering;
    this._recovering = this._silentWechatLogin()
      .catch(() => false)
      .then((ok) => {
        this._recovering = null;
        return ok;
      });
    return this._recovering;
  },

  _silentWechatLogin() {
    return new Promise((resolve) => {
      wx.login({
        success: (res) => {
          if (!res.code) return resolve(false);
          wx.request({
            url: `${this.globalData.apiBase}/auth/login`,
            method: 'POST',
            header: { 'Content-Type': 'application/json' },
            data: { code: res.code },
            success: (r) => {
              const data = r.data || {};
              if (r.statusCode >= 200 && r.statusCode < 300 && data.access_token) {
                this.setToken(data);
                resolve(true);
              } else {
                // 后端账号密码模式或服务异常,静默重登不可用
                resolve(false);
              }
            },
            fail: () => resolve(false)
          });
        },
        fail: () => resolve(false)
      });
    });
  },

  // 全局数据版本号:任何 CRUD 后自增,首页 onShow 检测到变化就重新拉数据
  bumpDataVersion() {
    this.globalData.dataVersion = (this.globalData.dataVersion || 0) + 1;
  },
  request: request  // 暴露给所有页面使用
});
