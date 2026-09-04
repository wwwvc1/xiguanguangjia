# 习惯管家 - 管理后台

Vue3 + Ant Design Vue + Vite + Pinia 的管理后台。

## 启动

```bash
cd admin-web
npm install
npm run dev
```

浏览器打开 http://localhost:5173

## 配置

默认通过 Vite proxy 转发 `/api/*` 到 `http://127.0.0.1:8000`(后端 FastAPI)。

如果后端端口不同,改 `vite.config.js` 的 `server.proxy`。

## 默认账号

通过后端命令创建:
```bash
cd ../backend
python -m scripts.create_admin admin Admin@123 超级管理员
```

## 技术栈

- Vite 5 + Vue 3.4
- Ant Design Vue 4.x
- Pinia
- Vue Router
- Axios
- ECharts(预留,图表用)

## 响应式

- < 768px:侧栏隐藏,顶栏 Drawer 触发
- ≥ 768px:固定侧栏
- 内容区网格:xs 1 列 / sm 2 列 / lg 4 列
