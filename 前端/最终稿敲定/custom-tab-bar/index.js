Component({
  data: {
    selected: 0,
    list: [
      {pagePath: '/pages/index/index',      text: 'Home',   icon: '◉'},
      {pagePath: '/pages/todo/todo',        text: 'Todos',  icon: '▢'},
      {pagePath: '/pages/ai/ai',            text: 'AI',     icon: '✦'},
      {pagePath: '/pages/settings/settings', text: 'Setup',  icon: '◐'}
    ]
  },
  methods: {
    switchTab(e) {
      const {path, index} = e.currentTarget.dataset;
      wx.switchTab({url: path});
    }
  }
});
