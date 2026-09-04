const app = getApp();

const ICONS = {
  '餐饮': '🍜', '交通': '🚇', '工资': '💼', '购物': '🛒',
  '娱乐': '🎮', '住房': '', '医疗': '💊', '教育': '📚'
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    currentYear: new Date().getFullYear(),
    currentMonth: new Date().getMonth() + 1,
    records: [],
    summary: { income: 0, expense: 0, net: 0 },
    showAdd: false,
    formData: { category: '', desc: '', amount: 0, type: 'expense' }
  },
  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight
    });
  },
  onShow() {
    this.loadData();
  },
  goBack() {
    wx.navigateBack();
  },
  loadData() {
    const { currentYear, currentMonth } = this.data;
    const monthStr = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;

    // 加载月度统计
    app.request({
      url: `/transactions/summary?month=${monthStr}`
    }).then(summary => {
      this.setData({ summary });
    }).catch(() => {
      this.setData({ summary: { income: 0, expense: 0, net: 0 } });
    });

    // 加载月度交易列表
    app.request({
      url: `/transactions?year=${currentYear}&month=${currentMonth}`
    }).then(records => {
      this.setData({
        records: records.map(r => ({
          ...r,
          icon: ICONS[r.category] || '',
          title: r.category,
          desc: r.description || ''
        }))
      });
    }).catch(() => {
      this.setData({ records: [] });
    });
  },
  onPrevMonth() {
    let { currentYear, currentMonth } = this.data;
    currentMonth--;
    if (currentMonth < 1) {
      currentMonth = 12;
      currentYear--;
    }
    this.setData({ currentYear, currentMonth }, () => this.loadData());
  },
  onNextMonth() {
    let { currentYear, currentMonth } = this.data;
    currentMonth++;
    if (currentMonth > 12) {
      currentMonth = 1;
      currentYear++;
    }
    this.setData({ currentYear, currentMonth }, () => this.loadData());
  },
  onFabTap() {
    this.setData({
      showAdd: true,
      formData: { category: '', desc: '', amount: 0, type: 'expense' }
    });
  },
  onCancel() {
    this.setData({ showAdd: false });
  },
  stopPropagation() {},
  onFormInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`formData.${field}`]: e.detail.value });
  },
  onTypeToggle(e) {
    this.setData({ 'formData.type': e.currentTarget.dataset.value });
  },
  onSave() {
    const { formData } = this.data;
    if (!formData.category.trim()) {
      wx.showToast({ title: '请输入分类', icon: 'none' });
      return;
    }
    const amount = formData.type === 'expense' ? -Math.abs(Number(formData.amount) || 0) : Math.abs(Number(formData.amount) || 0);
    const now = new Date();
    const time = now.toISOString().slice(0, 19).replace('T', ' ');

    app.request({
      url: '/transactions',
      method: 'POST',
      data: {
        category: formData.category,
        description: formData.desc || '',
        amount: amount,
        type: formData.type,
        time: time
      }
    }).then(() => {
      this.loadData();
      this.setData({ showAdd: false });
      wx.showToast({ title: '已添加', icon: 'success' });
    }).catch(err => {
      console.error('添加失败:', err);
      wx.showToast({ title: '添加失败', icon: 'none' });
    });
  }
});
