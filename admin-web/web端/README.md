# 习惯管家 · 管理后台 (web端)

Phase 0 基础架构骨架 — 只搭好 Vite + Vue 3 + TS + Pinia + vue-router + axios,**不包含业务功能**。
Phase 1-5 会按视图逐步填充。

## 启动

```bash
npm install
npm run dev      # http://localhost:5174 (不和 admin-web 原 5173 冲突)
npm run build    # 生产构建 (含 vue-tsc 类型检查)
npm run preview  # 预览 dist
npm run type-check
```

后端默认 `http://127.0.0.1:8000`,Vite proxy 把 `/api/*` 转发过去。

## 目录

```
src/
  api/         8 个 *.ts: 每个 export 函数声明 (Phase 2 才实现 body)
  components/  glass/earth/chart/form/ui 子目录
  composables/ useCountup / useMagneticHover / useStaggerEnter
  router/      10 个路由 + 登录守卫
  stores/      auth/theme/ui 三个 Pinia store
  utils/       format/permissions/constants
  views/       10 个 .vue 占位
  App.vue      <router-view /> + transition
  main.ts      createApp + Pinia + router + axios + 错误处理
```

## 设计 Token

继承自 `待选web前端/16-混合-纯Canvas2D-高透玻璃.html`,集中在 `App.vue` 顶部 `<style>` 中:

- 玻璃 3 档 (`--glass-1/2/3-bg/border/blur`)
- 紫青渐变 (`--accent-1: #7c5cff`, `--accent-2: #34d399`)
- light + dark 主题完整覆盖