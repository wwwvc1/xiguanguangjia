const app = getApp();

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    activeTab: 'todo',
    todos: [],
    completedTodos: [],
    goals: [],
    showAdd: false,
    isEditGoal: false,
    goalMode: false,
    editGoalId: null,
    formData: { text: '', startDate: '', endDate: '' },
    goalForm: { name: '', progress: 0, start_date: '', end_date: '' },
    batchMode: false,
    selectedTodos: [],
    selectedGoals: []
  },
  onLoad() {
    const g = app.globalData;
    this.setData({
      statusBarHeight: g.statusBarHeight,
      navHeight: g.navHeight,
      'formData.startDate': todayStr(),
      'formData.endDate': todayStr()
    });
  },
  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({selected: 1});
    }
    this.loadData();
  },
  loadData() {
    const today = todayStr();
    app.request({ url: `/todos/?done=false&date=${today}` }).then(todos => {
      this.setData({ todos });
    }).catch(() => { this.setData({ todos: [] }); });
    app.request({ url: '/todos/?done=true' }).then(todos => {
      this.setData({ completedTodos: todos });
    }).catch(() => { this.setData({ completedTodos: [] }); });
    app.request({ url: '/goals/' }).then(goals => {
      this.setData({ goals });
    }).catch(() => { this.setData({ goals: [] }); });
  },
  switchTab(e) {
    // 切换 tab 时退出批量模式
    this.setData({
      activeTab: e.currentTarget.dataset.tab,
      batchMode: false,
      selectedTodos: [],
      selectedGoals: []
    });
  },

  // ============ 待办相关 ============
  toggleTodo(e) {
    const id = e.currentTarget.dataset.id;
    app.request({ url: `/todos/${id}`, method: 'PUT', data: { done: true } })
      .then(() => { this.loadData(); app.bumpDataVersion(); })
      .catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
  },
  uncompleteTodo(e) {
    const id = e.currentTarget.dataset.id;
    app.request({ url: `/todos/${id}`, method: 'PUT', data: { done: false } })
      .then(() => { this.loadData(); app.bumpDataVersion(); })
      .catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
  },
  deleteTodo(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({ title: '确认删除', content: '删除后无法恢复', confirmColor: '#8DA9C4', success: (res) => {
      if (res.confirm) {
        app.request({ url: `/todos/${id}`, method: 'DELETE' })
          .then(() => { this.loadData(); app.bumpDataVersion(); wx.showToast({ title: '已删除', icon: 'success' }); })
          .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
      }
    }});
  },
  onFabTap() {
    // 根据当前 tab 决定弹窗类型
    if (this.data.activeTab === 'goal') {
      this.setData({
        showAdd: true,
        isEditGoal: false,
        goalMode: true,
        goalForm: { name: '', progress: 0, start_date: '', end_date: '' }
      });
    } else {
      this.setData({
        showAdd: true,
        isEditGoal: false,
        goalMode: false,
        formData: { text: '', startDate: todayStr(), endDate: todayStr() }
      });
    }
  },
  onEditGoal(e) {
    const id = e.currentTarget.dataset.id;
    const goal = this.data.goals.find(g => g.id === id);
    this.setData({
      showAdd: true,
      isEditGoal: true,
      goalMode: true,
      editGoalId: id,
      goalForm: {
        name: goal.name,
        progress: goal.progress,
        start_date: goal.start_date || '',
        end_date: goal.end_date || ''
      }
    });
  },
  onCancel() { this.setData({ showAdd: false }); },
  stopPropagation() {},
  onFormInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`formData.${field}`]: e.detail.value });
  },
  onGoalFormInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`goalForm.${field}`]: e.detail.value });
  },
  onSave() {
    if (this.data.isEditGoal) {
      this.saveGoal();
      return;
    }
    if (this.data.goalMode) {
      this.createGoal();
      return;
    }
    const { text, startDate, endDate } = this.data.formData;
    if (!text.trim()) { wx.showToast({ title: '请输入待办内容', icon: 'none' }); return; }
    if (startDate > endDate) { wx.showToast({ title: '开始日期不能晚于结束日期', icon: 'none' }); return; }

    const url = startDate === endDate ? '/todos/' : '/todos/batch';
    const data = startDate === endDate
      ? { text: text.trim(), due_date: startDate }
      : { text: text.trim(), start_date: startDate, end_date: endDate };

    app.request({ url, method: 'POST', data })
      .then(() => { this.loadData(); this.setData({ showAdd: false }); app.bumpDataVersion(); wx.showToast({ title: '已添加', icon: 'success' }); })
      .catch(() => wx.showToast({ title: '添加失败', icon: 'none' }));
  },
  saveGoal() {
    const { name, progress, start_date, end_date } = this.data.goalForm;
    if (!name.trim()) { wx.showToast({ title: '请输入目标名称', icon: 'none' }); return; }
    if (start_date && end_date && start_date > end_date) {
      wx.showToast({ title: '开始日期不能晚于结束日期', icon: 'none' });
      return;
    }
    app.request({
      url: `/goals/${this.data.editGoalId}`,
      method: 'PUT',
      data: {
        name: name.trim(),
        progress: Math.min(100, Math.max(0, Number(progress) || 0)),
        start_date: start_date || null,
        end_date: end_date || null
      }
    }).then(() => { this.loadData(); this.setData({ showAdd: false }); app.bumpDataVersion(); wx.showToast({ title: '已更新', icon: 'success' }); })
      .catch(() => wx.showToast({ title: '更新失败', icon: 'none' }));
  },
  createGoal() {
    const { name, start_date, end_date } = this.data.goalForm;
    if (!name.trim()) { wx.showToast({ title: '请输入目标名称', icon: 'none' }); return; }
    if (start_date && end_date && start_date > end_date) {
      wx.showToast({ title: '开始日期不能晚于结束日期', icon: 'none' });
      return;
    }
    app.request({
      url: '/goals/',
      method: 'POST',
      data: {
        name: name.trim(),
        progress: 0,
        start_date: start_date || null,
        end_date: end_date || null
      }
    }).then(() => { this.loadData(); this.setData({ showAdd: false }); app.bumpDataVersion(); wx.showToast({ title: '已添加', icon: 'success' }); })
      .catch((err) => wx.showToast({ title: '添加失败: ' + (err.response?.data?.detail || err.message), icon: 'none' }));
  },
  deleteGoal(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({ title: '确认删除', content: '删除后无法恢复', confirmColor: '#8DA9C4', success: (res) => {
      if (res.confirm) {
        app.request({ url: `/goals/${id}`, method: 'DELETE' })
          .then(() => { this.loadData(); app.bumpDataVersion(); wx.showToast({ title: '已删除', icon: 'success' }); })
          .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
      }
    }});
  },

  // ============ 批量模式 ============
  onToggleBatchTodo() {
    this.setData({
      batchMode: !this.data.batchMode,
      selectedTodos: []
    });
  },
  onToggleBatchGoal() {
    this.setData({
      batchMode: !this.data.batchMode,
      selectedGoals: []
    });
  },
  onToggleSelectTodo(e) {
    const id = e.currentTarget.dataset.id;
    const list = this.data.selectedTodos;
    const idx = list.indexOf(id);
    if (idx >= 0) list.splice(idx, 1);
    else list.push(id);
    this.setData({ selectedTodos: [...list] });
  },
  onToggleSelectGoal(e) {
    const id = e.currentTarget.dataset.id;
    const list = this.data.selectedGoals;
    const idx = list.indexOf(id);
    if (idx >= 0) list.splice(idx, 1);
    else list.push(id);
    this.setData({ selectedGoals: [...list] });
  },
  onSelectAllTodos() {
    const all = [
      ...this.data.todos.map(t => t.id),
      ...this.data.completedTodos.map(t => t.id)
    ];
    this.setData({ selectedTodos: all });
  },
  onSelectInvertTodos() {
    const all = [
      ...this.data.todos.map(t => t.id),
      ...this.data.completedTodos.map(t => t.id)
    ];
    const cur = this.data.selectedTodos;
    const inverted = all.filter(id => !cur.includes(id));
    this.setData({ selectedTodos: inverted });
  },
  onSelectAllGoals() {
    this.setData({ selectedGoals: this.data.goals.map(g => g.id) });
  },
  onSelectInvertGoals() {
    const all = this.data.goals.map(g => g.id);
    const cur = this.data.selectedGoals;
    this.setData({ selectedGoals: all.filter(id => !cur.includes(id)) });
  },
  onBatchDeleteTodos() {
    const ids = this.data.selectedTodos;
    if (ids.length === 0) {
      wx.showToast({ title: '请先勾选', icon: 'none' });
      return;
    }
    wx.showModal({
      title: '确认批量删除',
      content: `将删除 ${ids.length} 条待办,不可恢复`,
      confirmColor: '#B08070',
      success: (res) => {
        if (!res.confirm) return;
        app.request({
          url: '/todos/batch-delete',
          method: 'POST',
          data: { ids }
        }).then(r => {
          this.setData({ batchMode: false, selectedTodos: [] });
          this.loadData(); app.bumpDataVersion();
          wx.showToast({ title: `已删除 ${r.deleted} 条`, icon: 'success' });
        }).catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
      }
    });
  },
  onBatchDeleteGoals() {
    const ids = this.data.selectedGoals;
    if (ids.length === 0) {
      wx.showToast({ title: '请先勾选', icon: 'none' });
      return;
    }
    wx.showModal({
      title: '确认批量删除',
      content: `将删除 ${ids.length} 个目标,不可恢复`,
      confirmColor: '#B08070',
      success: (res) => {
        if (!res.confirm) return;
        app.request({
          url: '/goals/batch-delete',
          method: 'POST',
          data: { ids }
        }).then(r => {
          this.setData({ batchMode: false, selectedGoals: [] });
          this.loadData(); app.bumpDataVersion();
          wx.showToast({ title: `已删除 ${r.deleted} 条`, icon: 'success' });
        }).catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
      }
    });
  }
});
