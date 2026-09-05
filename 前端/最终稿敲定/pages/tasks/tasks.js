const app = getApp();

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};

const nowTimeStr = () => new Date().toISOString().slice(0, 19).replace('T', ' ');

// 把后端 time 格式化为列表展示用的短时间字符串
const formatTime = (t) => {
  if (!t) return '';
  // 兼容 "2024-07-15 07:00:00" 和 ISO "2024-07-15T07:00:00"
  const s = String(t).replace('T', ' ');
  const datePart = s.slice(5, 10); // MM-DD
  const timePart = s.slice(11, 16); // HH:MM
  // 当天只显示时分，否则显示月日
  return s.slice(0, 10) === todayStr() ? timePart : datePart;
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    activeTab: 'todo',
    todoList: [],
    goalList: [],
    financeList: [],
    showAdd: false,
    isEdit: false,
    editId: null,
    formData: { text: '', name: '', progress: 0, category: '', desc: '', amount: 0, type: 'expense' }
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
    this.loadData();
  },

  loadData() {
    // 加载全部未完成待办
    app.request({ url: '/todos/?done=false' })
      .then(todoList => this.setData({ todoList }))
      .catch(() => this.setData({ todoList: [] }));

    // 加载目标
    app.request({ url: '/goals/' })
      .then(goalList => this.setData({ goalList }))
      .catch(() => this.setData({ goalList: [] }));

    // 加载当月收支
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    app.request({ url: `/transactions/?year=${year}&month=${month}` })
      .then(records => {
        const financeList = (records || []).map(r => ({
          ...r,
          time: formatTime(r.time)
        }));
        this.setData({ financeList });
      })
      .catch(() => this.setData({ financeList: [] }));
  },

  switchTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },

  // 打开新增弹窗
  onAdd() {
    const { activeTab } = this.data;
    const defaults = {
      todo: { text: '' },
      goal: { name: '', progress: 0 },
      finance: { category: '', desc: '', amount: 0, type: 'expense' }
    };
    this.setData({
      showAdd: true,
      isEdit: false,
      editId: null,
      formData: { ...defaults[activeTab] }
    });
  },

  // 编辑
  onEdit(e) {
    const id = e.currentTarget.dataset.id;
    const { activeTab } = this.data;
    const listKey = activeTab === 'todo' ? 'todoList' : activeTab === 'goal' ? 'goalList' : 'financeList';
    const item = this.data[listKey].find(t => t.id === id);
    if (!item) return;

    let formData = { ...item };
    // 收支编辑时，金额以绝对值显示
    if (activeTab === 'finance') {
      formData.amount = Math.abs(Number(item.amount) || 0);
    }
    this.setData({
      showAdd: true,
      isEdit: true,
      editId: id,
      formData
    });
  },

  // 点击目标卡片编辑
  onEditGoal(e) {
    const id = e.currentTarget.dataset.id;
    const item = this.data.goalList.find(t => t.id === id);
    if (!item) return;
    this.setData({
      showAdd: true,
      isEdit: true,
      editId: id,
      activeTab: 'goal',
      formData: { name: item.name, progress: item.progress }
    });
  },

  // 删除
  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    const { activeTab } = this.data;
    const urlMap = {
      todo: `/todos/${id}`,
      goal: `/goals/${id}`,
      finance: `/transactions/${id}`
    };
    const url = urlMap[activeTab];
    if (!url) return;

    wx.showModal({
      title: '确认删除',
      content: '删除后无法恢复',
      confirmColor: '#8DA9C4',
      success: (res) => {
        if (res.confirm) {
          app.request({ url, method: 'DELETE' })
            .then(() => {
              this.loadData();
              wx.showToast({ title: '已删除', icon: 'success' });
            })
            .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
        }
      }
    });
  },

  // 表单输入
  onFormInput(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail && e.detail.value !== undefined ? e.detail.value : e.currentTarget.dataset.value;
    this.setData({ [`formData.${field}`]: value });
  },

  // 保存（新增 or 编辑）
  onSave() {
    const { activeTab, isEdit, editId, formData } = this.data;
    let promise;

    if (activeTab === 'todo') {
      if (!formData.text || !formData.text.trim()) {
        wx.showToast({ title: '请输入待办内容', icon: 'none' });
        return;
      }
      promise = isEdit
        ? app.request({ url: `/todos/${editId}`, method: 'PUT', data: { text: formData.text.trim() } })
        : app.request({ url: '/todos/', method: 'POST', data: { text: formData.text.trim() } });
    } else if (activeTab === 'goal') {
      if (!formData.name || !formData.name.trim()) {
        wx.showToast({ title: '请输入目标名称', icon: 'none' });
        return;
      }
      const payload = {
        name: formData.name.trim(),
        progress: Math.min(100, Math.max(0, Number(formData.progress) || 0))
      };
      promise = isEdit
        ? app.request({ url: `/goals/${editId}`, method: 'PUT', data: payload })
        : app.request({ url: '/goals/', method: 'POST', data: payload });
    } else if (activeTab === 'finance') {
      if (!formData.category || !formData.category.trim()) {
        wx.showToast({ title: '请输入分类', icon: 'none' });
        return;
      }
      const absAmount = Math.abs(Number(formData.amount) || 0);
      const amount = formData.type === 'expense' ? -absAmount : absAmount;
      const payload = {
        category: formData.category.trim(),
        description: formData.desc || '',
        amount: amount,
        type: formData.type,
        time: nowTimeStr()
      };
      promise = isEdit
        ? app.request({ url: `/transactions/${editId}`, method: 'PUT', data: payload })
        : app.request({ url: '/transactions/', method: 'POST', data: payload });
    }

    if (!promise) return;

    promise.then(() => {
      this.loadData();
      this.setData({ showAdd: false });
      wx.showToast({ title: isEdit ? '已更新' : '已添加', icon: 'success' });
      app.bumpDataVersion();
    }).catch((err) => {
      console.error('保存失败:', err);
      wx.showToast({ title: '保存失败', icon: 'none' });
    });
  },

  // 取消
  onCancel() {
    this.setData({ showAdd: false });
  },

  // 切换待办完成状态
  toggleTodo(e) {
    const id = e.currentTarget.dataset.id;
    app.request({ url: `/todos/${id}`, method: 'PUT', data: { done: true } })
      .then(() => { this.loadData(); app.bumpDataVersion(); })
      .catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
  },

  goBack() {
    wx.navigateBack();
  },

  goAICreate() {
    wx.navigateTo({ url: '/pages/ai-create/ai-create' });
  },

  stopPropagation() {
    // 阻止弹窗点击冒泡到mask
  },

  onTypeToggle(e) {
    this.setData({ 'formData.type': e.currentTarget.dataset.value });
  }
});
