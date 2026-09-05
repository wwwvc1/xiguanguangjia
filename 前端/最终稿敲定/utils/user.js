/**
 * 用户资料管理工具
 *
 * 当前实现:localStorage 模拟 + 同步到 app.globalData.userInfo
 * 后端接口就绪后(其他 agent 开发中),只需把下列三个函数中的 localStorage
 * 部分替换为 app.request 调用即可,函数签名不变。
 *
 * 公开 API:
 *   getUserInfo()                 → { nickname, avatar }
 *   updateNickname(nickname)      → Promise<{ok}>
 *   updateAvatar(avatarBase64)    → Promise<{ok}>
 *   chooseImage(opts)             → Promise<{tempFilePath, base64}>
 */

const STORAGE_KEY = 'userInfo';
const MAX_AVATAR_BYTES = 800 * 1024; // 800KB 上限,base64 后约 1.07MB

// 工具:读取当前资料(优先 globalData,fallback storage)
function readUserInfo() {
  try {
    const app = getApp();
    if (app && app.globalData && app.globalData.userInfo) {
      return app.globalData.userInfo;
    }
  } catch (e) {}
  try {
    return wx.getStorageSync(STORAGE_KEY) || { nickname: '我', avatar: '' };
  } catch (e) {
    return { nickname: '我', avatar: '' };
  }
}

// 工具:写入资料(globalData + storage)
function writeUserInfo(partial) {
  const app = getApp();
  const next = { ...readUserInfo(), ...partial };
  if (app && app.setUserInfo) {
    app.setUserInfo(next);
  } else {
    try { wx.setStorageSync(STORAGE_KEY, next); } catch (e) {}
  }
  return next;
}

/**
 * 读取当前用户资料
 * @returns {{nickname: string, avatar: string}}
 */
function getUserInfo() {
  return readUserInfo();
}

/**
 * 更新昵称
 * @param {string} nickname
 * @returns {Promise<{ok: boolean, info?: object}>}
 */
function updateNickname(nickname) {
  const trimmed = String(nickname || '').trim();
  if (!trimmed) {
    return Promise.reject(new Error('昵称不能为空'));
  }
  if (trimmed.length > 20) {
    return Promise.reject(new Error('昵称最多 20 个字符'));
  }
  // TODO: 后端就绪后,这里先 PUT /user/profile
  // app.request({ url: '/user/profile', method: 'PUT', data: { nickname: trimmed } })
  const next = writeUserInfo({ nickname: trimmed });
  return Promise.resolve({ ok: true, info: next });
}

/**
 * 更新头像(base64 字符串)
 * 自动压缩 + 校验大小
 * @param {string} base64 形如 "data:image/jpeg;base64,xxx"
 */
function updateAvatar(base64) {
  if (!base64 || typeof base64 !== 'string') {
    return Promise.reject(new Error('头像数据无效'));
  }
  // 大小校验(粗略:base64 字符数 × 0.75 ≈ 字节数)
  const approxBytes = Math.floor(base64.length * 0.75);
  if (approxBytes > MAX_AVATAR_BYTES * 1.4) {
    return Promise.reject(new Error('图片过大,请换一张(限制 800KB)'));
  }
  // TODO: 后端就绪后,这里先 PUT /user/profile
  // app.request({ url: '/user/profile', method: 'PUT', data: { avatar: base64 } })
  const next = writeUserInfo({ avatar: base64 });
  return Promise.resolve({ ok: true, info: next });
}

/**
 * 选择图片 → 转 base64
 * @param {{sourceType?: ('album'|'camera')[], sizeType?: ('compressed'|'original')[]}} opts
 * @returns {Promise<{tempFilePath: string, base64: string}>}
 */
function chooseImage(opts = {}) {
  const { sourceType = ['album', 'camera'], sizeType = ['compressed'] } = opts;
  return new Promise((resolve, reject) => {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType,
      sourceType,
      success: (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (!file) return reject(new Error('未选择图片'));
        // 读取为 base64
        wx.getFileSystemManager().readFile({
          filePath: file.tempFilePath,
          encoding: 'base64',
          success: (data) => {
            const base64 = 'data:image/jpeg;base64,' + data.data;
            resolve({ tempFilePath: file.tempFilePath, base64 });
          },
          fail: () => reject(new Error('读取图片失败'))
        });
      },
      fail: () => reject(new Error('用户取消选择'))
    });
  });
}

/**
 * 重置用户资料(清空头像 + 昵称回默认)
 * 用于设置页"恢复默认"
 */
function resetUserInfo() {
  try { wx.removeStorageSync(STORAGE_KEY); } catch (e) {}
  const app = getApp();
  if (app && app.setUserInfo) {
    app.setUserInfo({ nickname: '我', avatar: '' });
  }
  return { nickname: '我', avatar: '' };
}

module.exports = {
  getUserInfo,
  updateNickname,
  updateAvatar,
  chooseImage,
  resetUserInfo
};
