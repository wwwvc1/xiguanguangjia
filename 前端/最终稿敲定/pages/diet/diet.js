const app = getApp();

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};

const MEAL_TYPE_LABELS = {
  breakfast: '🌅 早餐',
  lunch: '☀️ 午餐',
  dinner: '🌙 晚餐'
};

const MEAL_TYPES = ['breakfast', 'lunch', 'dinner'];

// 把后端 meals 列表整理为今日三段（缺失则空）
function buildDisplayMeals(meals) {
  const today = todayStr();
  const todayMeals = (meals || []).filter(m => m.date === today);
  const map = {};
  todayMeals.forEach(m => { map[m.meal_type] = m; });

  return MEAL_TYPES.map(t => {
    const m = map[t];
    return {
      id: m ? m.id : null,
      meal_type: t,
      title: MEAL_TYPE_LABELS[t],
      total: m ? Number(m.total_calories) || 0 : 0,
      items: m ? (m.items || []).map(it => ({
        id: it.id,
        name: it.name,
        portion: it.portion || '',
        calories: Number(it.calories) || 0
      })) : []
    };
  });
}

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 88,
    meals: [],
    totalCalories: 0,
    recordedMealCount: 0,
    calorieGoal: 1800,
    showAdd: false,
    formData: { name: '', portion: '', calories: 0, meal_type: 'breakfast' }
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

  goBack() {
    wx.navigateBack();
  },

  loadData() {
    // 并行加载：饮食列表 + 用户设置
    Promise.all([
      app.request({ url: '/meals/' }).catch(() => []),
      app.request({ url: '/user/settings' }).catch(() => null)
    ]).then(([meals, settings]) => {
      const display = buildDisplayMeals(meals);
      const totalCalories = display.reduce((s, m) => s + m.total, 0);
      const recordedMealCount = display.filter(m => m.items.length > 0).length;
      const update = { meals: display, totalCalories, recordedMealCount };
      if (settings && settings.target_calories) {
        update.calorieGoal = settings.target_calories;
      }
      this.setData(update);
    });
  },

  onFabTap() {
    this.setData({
      showAdd: true,
      formData: { name: '', portion: '', calories: 0, meal_type: 'breakfast' }
    });
  },

  onCancel() {
    this.setData({ showAdd: false });
  },

  stopPropagation() {},

  onFormInput(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail && e.detail.value !== undefined ? e.detail.value : e.currentTarget.dataset.value;
    this.setData({ [`formData.${field}`]: value });
  },

  onMealTypeTap(e) {
    this.setData({ 'formData.meal_type': e.currentTarget.dataset.value });
  },

  onSave() {
    const { formData, meals } = this.data;
    if (!formData.name || !formData.name.trim()) {
      wx.showToast({ title: '请输入食物名称', icon: 'none' });
      return;
    }
    const newItem = {
      name: formData.name.trim(),
      portion: formData.portion || '',
      calories: Number(formData.calories) || 0
    };

    // 找到该 meal_type 的现有餐次（今日）
    const existing = meals.find(m => m.meal_type === formData.meal_type);
    const updatedItems = existing ? [...existing.items, newItem] : [newItem];
    const totalCalories = updatedItems.reduce((s, it) => s + it.calories, 0);

    const payload = {
      meal_type: formData.meal_type,
      date: todayStr(),
      total_calories: totalCalories,
      items: updatedItems
    };

    const promise = existing && existing.id
      ? app.request({ url: `/meals/${existing.id}`, method: 'PUT', data: payload })
      : app.request({ url: '/meals/', method: 'POST', data: payload });

    promise.then(() => {
      this.loadData();
      this.setData({ showAdd: false });
      wx.showToast({ title: '已添加', icon: 'success' });
      app.bumpDataVersion();
    }).catch(err => {
      console.error('添加失败:', err);
      wx.showToast({ title: '添加失败', icon: 'none' });
    });
  },

  // 删除某餐中的单项食物
  onDeleteItem(e) {
    const { mealType, itemId } = e.currentTarget.dataset;
    const meal = this.data.meals.find(m => m.meal_type === mealType);
    if (!meal || !meal.id) return;

    const remaining = meal.items.filter(it => it.id !== itemId);

    wx.showModal({
      title: '确认删除',
      content: '从该餐次中移除此项',
      confirmColor: '#8DA9C4',
      success: (res) => {
        if (!res.confirm) return;
        if (remaining.length === 0) {
          // 餐次内已无食物，删除整条 meal
          app.request({ url: `/meals/${meal.id}`, method: 'DELETE' })
            .then(() => { this.loadData(); wx.showToast({ title: '已删除', icon: 'success' }); app.bumpDataVersion(); })
            .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
        } else {
          const payload = {
            meal_type: meal.meal_type,
            date: todayStr(),
            total_calories: remaining.reduce((s, it) => s + it.calories, 0),
            items: remaining
          };
          app.request({ url: `/meals/${meal.id}`, method: 'PUT', data: payload })
            .then(() => { this.loadData(); wx.showToast({ title: '已删除', icon: 'success' }); app.bumpDataVersion(); })
            .catch(() => wx.showToast({ title: '删除失败', icon: 'none' }));
        }
      }
    });
  }
});
