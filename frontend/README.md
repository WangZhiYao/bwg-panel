# BWG Panel 前端

Vue3 + Vite + TypeScript + ECharts 单页应用。构建产物 `dist/` 由后端 FastAPI 同源托管（前后端同源零 CORS）。

## 开发

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 代理到 127.0.0.1:8000（先起后端）
```

## 测试与构建

```powershell
npm run test       # Vitest（测试与源码同目录，*.test.ts）
npm run build      # vue-tsc 类型检查 + vite build → 产物 dist/，后端重启后 GET / 直接返回 SPA
```

## 结构

- `src/api.ts` 后端契约封装（扁平错误 → ApiError；204/网络错误区分）
- `src/router.ts` 路由 + 登录守卫（未授权踢回 /login，网络瞬断放行）
- `src/format.ts` 纯函数格式化（humanBytes/pct/倒计时/点数）
- `src/chart-theme.ts` ECharts 主题
- `src/views/` Login / Dashboard / Trends / Alerts / Settings
- `src/components/`
  - `ServerCard.vue` 双卡总览卡片（内嵌 TrafficRing / ResourceBar）
  - `SnapshotMenu.vue` 快照管理菜单 · `TopBar.vue` 顶栏 · `ConfirmDialog.vue` 强确认弹窗
- `src/tokens.css` 设计语言单一定义源（改主题只动这里）
