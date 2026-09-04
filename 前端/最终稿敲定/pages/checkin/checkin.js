const app = getApp();

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};

const dateMinusDays = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

// 罗马数字转换(0-50 够用)
const toRoman = (num) => {
  if (!num || num < 1) return '0';
  const map = [
    [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'],
    [5, 'v'], [4, 'iv'], [1, 'i']
  ];
  let result = '';
  let n = Math.min(num, 50);
  for (const [v, s] of map) {
    while (n >= v) { result += s; n -= v; }
  }
  return result;
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    streak: 0,
    streakRoman: '0',
    todayChecked: false,
    count: 0,
    daysInMonth: 30,
    note: '',
    checking: false,
    history: [],
    calendar: []
  },

  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });
    this.loadAll();
  },

  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
    this.loadAll();
  },

  async loadAll() {
    this.loadStreak();
    this.loadHistory();
  },

  loadStreak() {
    app.request({ url: '/checkins/streak' })
      .then(r => this.setData({
        streak: r.streak,
        streakRoman: toRoman(r.streak),
        todayChecked: r.today_checked
      }))
      .catch(() => this.setData({ streak: 0, streakRoman: '0' }));
  },

  loadHistory() {
    app.request({ url: '/checkins?days=30' })
      .then(r => {
        const items = r.items || [];
        const checkedDates = new Set(items.map(it => it.date));
        // 30 天日历(从今天往前 30 天)
        const calendar = [];
        for (let i = 29; i >= 0; i--) {
          const d = dateMinusDays(i);
          calendar.push({
            date: d,
            day: parseInt(d.split('-')[2], 10),
            checked: checkedDates.has(d),
            isToday: d === todayStr()
          });
        }
        this.setData({
          count: r.count || 0,
          history: items.slice(0, 20),
          calendar,
          daysInMonth: 30
        });
      })
      .catch(() => this.setData({ count: 0, history: [], calendar: [], daysInMonth: 30 }));
  },

  onNoteInput(e) {
    this.setData({ note: e.detail.value });
  },

  onCheckin() {
    if (this.data.checking || this.data.todayChecked) return;
    this.setData({ checking: true });
    app.request({
      url: '/checkins',
      method: 'POST',
      data: { note: this.data.note || null, auto: false }
    }).then(r => {
      this.setData({
        checking: false,
        todayChecked: true,
        note: '',
        streak: r.streak || this.data.streak,
        streakRoman: toRoman(r.streak || this.data.streak)
      });
      if (r.already) {
        wx.showToast({ title: '今日已打卡', icon: 'none' });
      } else {
        wx.showToast({ title: '打卡成功 🔥', icon: 'success' });
        if (r.newly_unlocked && r.newly_unlocked.length) {
          setTimeout(() => {
            wx.showModal({
              title: '🎉 成就解锁',
              content: r.newly_unlocked.map(a => `${a.icon} ${a.name}`).join('\n'),
              showCancel: false
            });
          }, 800);
        }
      }
      this.loadAll();
    }).catch(err => {
      this.setData({ checking: false });
      wx.showToast({ title: '打卡失败: ' + (err.response?.data?.detail || err.message), icon: 'none' });
    });
  },

  onBack() {
    wx.navigateBack();
  }
});