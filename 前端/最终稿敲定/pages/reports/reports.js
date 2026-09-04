const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    filter: 'all',
    reports: [],
    detail: null,
    reportTitle: ''
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
    this.loadList();
  },

  loadList() {
    const url = this.data.filter === 'all' ? '/reports' : `/reports?type=${this.data.filter}`;
    app.request({ url }).then(list => {
      this.setData({ reports: list || [] });
    }).catch(() => this.setData({ reports: [] }));
  },

  onChangeFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.value });
    this.loadList();
  },

  onGenerate(e) {
    const type = e.currentTarget.dataset.type;
    wx.showLoading({ title: '生成中...' });
    app.request({
      url: `/reports/generate?type=${type}`,
      method: 'POST'
    }).then(() => {
      wx.hideLoading();
      wx.showToast({ title: '已生成', icon: 'success' });
      this.loadList();
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '生成失败', icon: 'none' });
    });
  },

  onOpenReport(e) {
    const id = e.currentTarget.dataset.id;
    app.request({ url: `/reports/${id}` }).then(r => {
      this.setData({ detail: r, reportTitle: r.title || '报告详情' });
    });
  },

  onCloseDetail() {
    this.setData({ detail: null, reportTitle: '' });
  },

  // 导出报告为文本(可分享/复制)
  onExportReport() {
    const r = this.data.detail;
    if (!r) return;
    const lines = [];
    lines.push(`【${r.title || '习惯报告'}】`);
    lines.push(`时间: ${r.stats.start_date} 至 ${r.stats.end_date}`);
    lines.push('');
    lines.push('📈 数据快照');
    lines.push(`- 待办: 完成 ${r.stats.todos_done || 0}/${r.stats.todos_total || 0} (${r.stats.completion_rate || 0}%)`);
    lines.push(`- 收支: 收入 ¥${r.stats.tx_income || 0} / 支出 ¥${r.stats.tx_expense || 0} / 结余 ¥${r.stats.tx_net || 0}`);
    lines.push(`- 饮食: ${r.stats.meals_count || 0} 餐 / ${r.stats.meals_calories || 0} kcal`);
    if (r.stats.goals_progress && r.stats.goals_progress.length) {
      lines.push('- 目标:');
      r.stats.goals_progress.forEach(g => {
        lines.push(`  · ${g.name} ${g.progress}%${g.done ? ' ✓' : ''}`);
      });
    }
    lines.push('');
    lines.push('🤖 AI 解读');
    lines.push(r.content || '');
    const text = lines.join('\n');
    wx.setClipboardData({ data: text, success: () => {
      wx.showToast({ title: '已复制到剪贴板', icon: 'success' });
    }});
  },

  onShareReport() {
    wx.showActionSheet({
      itemList: ['复制到剪贴板', '保存为图片(开发中)'],
      success: (res) => {
        if (res.tapIndex === 0) this.onExportReport();
        else wx.showToast({ title: '图片导出开发中', icon: 'none' });
      }
    });
  },

  goBack() {
    if (this.data.detail) {
      this.onCloseDetail();
    } else {
      wx.navigateBack();
    }
  }
});
