const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    models: [],
    customModels: [],
    activeModelId: null,
    activeModel: {},
    showForm: false,
    editingId: null,
    showKey: false,
    form: { name: '', base_url: '', api_key: '', model_name: '' }
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
    this.loadModels();
  },

  loadModels() {
    app.request({ url: '/llm/models/available' })
      .then(r => {
        const models = r.models || [];
        const activeId = r.active_model_id;
        const custom = models.filter(m => m.owner_user_id);
        const active = models.find(m => m.id === activeId)
                   || models.find(m => m.is_system_default)
                   || models[0]
                   || {};
        this.setData({
          models,
          customModels: custom,
          activeModelId: activeId,
          activeModel: active
        });
        wx.setStorageSync('active_model_id', activeId);
      })
      .catch(e => {
        wx.showToast({ title: e.message || '加载失败', icon: 'none' });
      });
  },

  onBack() {
    wx.navigateBack();
  },

  stopPropagation() {},

  onAdd() {
    if (this.data.customModels.length >= 3) {
      wx.showToast({ title: '最多 3 个', icon: 'none' });
      return;
    }
    this.setData({
      showForm: true,
      editingId: null,
      showKey: false,
      form: { name: '', base_url: '', api_key: '', model_name: '' }
    });
  },

  onEdit(e) {
    const item = e.currentTarget.dataset.item;
    this.setData({
      showForm: true,
      editingId: item.id,
      showKey: false,
      form: {
        name: item.name,
        base_url: item.base_url,
        api_key: '',
        model_name: item.model_name
      }
    });
  },

  onFormInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`form.${field}`]: e.detail.value });
  },

  onToggleShowKey() {
    this.setData({ showKey: !this.data.showKey });
  },

  onFormCancel() {
    this.setData({ showForm: false });
  },

  onFormSave() {
    const { form, editingId } = this.data;
    if (!form.name || !form.base_url || !form.model_name) {
      wx.showToast({ title: '请填写完整', icon: 'none' });
      return;
    }
    if (!editingId && !form.api_key) {
      wx.showToast({ title: '请填写 API Key', icon: 'none' });
      return;
    }
    let url, method, body;
    if (editingId) {
      url = `/llm/models/user/${editingId}`;
      method = 'PUT';
      body = { name: form.name, base_url: form.base_url, model_name: form.model_name };
      if (form.api_key) body.api_key = form.api_key;
    } else {
      url = '/llm/models/user';
      method = 'POST';
      body = { name: form.name, base_url: form.base_url, api_key: form.api_key, model_name: form.model_name };
    }
    app.request({ url, method, data: body })
      .then(() => {
        this.setData({ showForm: false });
        wx.showToast({ title: '已保存', icon: 'success' });
        this.loadModels();
      })
      .catch(e => wx.showToast({ title: e.message || '保存失败', icon: 'none' }));
  },

  onDelete(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认删除',
      content: '删除后将无法恢复',
      confirmColor: '#B08070',
      success: (r) => {
        if (r.confirm) {
          app.request({ url: `/llm/models/user/${id}`, method: 'DELETE' })
            .then(() => {
              wx.showToast({ title: '已删除', icon: 'success' });
              this.loadModels();
            })
            .catch(e => wx.showToast({ title: e.message || '删除失败', icon: 'none' }));
        }
      }
    });
  },

  onActivate(e) {
    const id = e.currentTarget.dataset.id;
    app.request({ url: `/llm/models/user/${id}/activate`, method: 'POST' })
      .then(() => {
        wx.setStorageSync('active_model_id', id);
        wx.showToast({ title: '已切换', icon: 'success' });
        this.loadModels();
      })
      .catch(e => wx.showToast({ title: e.message || '切换失败', icon: 'none' }));
  }
});
