# BWG Panel · 搬瓦工 VPS 监控管理面板

自托管的 [BandwagonHost](https://bandwagonhost.com)（搬瓦工）VPS 监控与管理面板：单体 FastAPI 进程 + SQLite，前端 Vue3 SPA 由后端同源托管。运行在你的第三台常开机器（NAS / 服务器）上 7×24 采样，**VPS 内零侵入**（不装任何 agent，仅调 KiwiVM 官方 API）。

## 功能

- **监控**：在线状态、月流量用量与剩余、流量重置倒计时、磁盘/内存/负载、CPU 节流标志；ECharts 趋势页（流量日耗、磁盘/内存时间序列，24h / 7d / 30d）
- **管理**：开机 / 关机 / 重启 / 强制结束（kill）、快照创建 / 删除 / 恢复；kill 与快照恢复需输入服务器昵称强确认，全部操作记入审计日志
- **告警**：掉线（5 分钟去抖）、流量超阈值（默认 80% / 95%，可调）、CPU 节流、采集异常、邮件通道故障 —— SMTP 邮件推送 + 面板高亮 + 历史记录，恢复时补发恢复邮件
- **点数友好**：默认每 5 分钟采样一轮；即时刷新带 60s 去重；KiwiVM API 点数余量常显于页脚，低水位自动降级暂停即时刷新
- **安全**：veid / api_key 只存后端、永不进浏览器；单用户 bcrypt 密码 + 签名 Cookie 会话（7 天）；登录限速 5 次/分钟/IP
- **离线演示**：`--mock` 模式内置两台假服务器（含演化数据），完整链路可演示，不消耗 API 点数

## 架构

```
浏览器（Vue3 SPA）
   │  同源 HTTP/JSON（签名 Cookie 会话）
FastAPI 单进程（Docker / systemd 常驻）
   ├─ REST API + 静态托管前端构建产物（同源零 CORS）
   ├─ APScheduler 定时采样（默认 5 分钟）→ SQLite 历史趋势
   ├─ 告警状态机 → SMTP 邮件
   └─ KiwiVMClient（api.64clouds.com，统一超时/重试/点数账本）
        ↓ HTTPS（veid + api_key）
     搬瓦工 VPS ×N
```

| 端 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · uvicorn · httpx · APScheduler · SQLite（WAL） |
| 前端 | Vue 3 · Vite · TypeScript · ECharts |

## 目录结构

```
bwg-panel/
├─ backend/            # FastAPI 后端（app/、tests/、requirements.txt）→ 详见 backend/README.md
├─ frontend/           # Vue3 SPA（构建产物 dist/ 由后端托管）→ 详见 frontend/README.md
├─ Dockerfile          # 多阶段：node 构建前端 → python 运行时单镜像
├─ docker-compose.yml  # 数据卷 + 环境变量 + 常驻
└─ .dockerignore
```

## 部署：Docker（推荐）

需要 Docker 20+；NAS 为 ARM 架构时用 `docker buildx --platform linux/arm64` 构建。

```bash
docker compose up -d --build
docker compose logs -f        # ADMIN_PASSWORD 留空时，初始密码只在首次启动日志打印一次
```

打开 `http://<主机>:8000`，登录后在设置页录入服务器的 `veid` + `api_key`（KiwiVM 面板左侧 API 页获取）。

不带 compose 的等效命令：

```bash
docker build -t bwg-panel .
docker run -d --name bwg-panel -p 8000:8000 -v bwg-data:/data --restart unless-stopped bwg-panel
```

### 环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `SECRET_KEY` | 会话签名密钥。**容器部署建议显式固定**（`openssl rand -base64 32`），否则容器重建后所有登录会话失效 | 自动生成 |
| `ADMIN_PASSWORD` | 首次启动的管理员初始密码；落库后即可删除该变量 | 自动生成并打印日志 |
| `DB_PATH` | SQLite 路径 | `/data/panel.db`（镜像内） |
| `COOKIE_SECURE` | 反代 HTTPS 后设 `1`：登录 Cookie 仅经 HTTPS 传输 | `0` |
| `TZ` | 容器时区 | 镜像默认（建议 `Asia/Shanghai`） |

### 数据与备份

全部状态（服务器档案、采样历史、告警、设置）都在一个 SQLite 文件里（卷 `bwg-data` → `/data/panel.db`）。不断服安全备份：

```bash
docker exec bwg-panel python -c "import sqlite3; sqlite3.connect('/data/panel.db').execute(\"VACUUM INTO '/data/backup.db'\")"
docker cp bwg-panel:/data/backup.db ./backup.db
```

恢复/迁移到新机器：停容器 → 用备份文件覆盖卷里的 `panel.db` → 重启。

### 公网暴露

容器直接映射的 8000 端口是明文 HTTP，仅适合内网。公网访问请前置 Caddy/Nginx 反代加 HTTPS，并在环境变量中启用 `COOKIE_SECURE=1`。

### 离线演示（不耗点数）

```bash
docker run --rm -p 8000:8000 bwg-panel python -m app --host 0.0.0.0 --mock
```

## 本地开发

后端（`backend/` 目录下）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app --mock      # 离线演示模式，http://127.0.0.1:8000/docs
```

前端（`frontend/` 目录下，另开终端）：

```powershell
npm install
npm run dev      # http://localhost:5173，/api 代理到 127.0.0.1:8000（先起后端）
```

测试：

```powershell
cd backend  ; .\.venv\Scripts\python.exe -m pytest -v
cd frontend ; npm run test
```

## 更多文档

- [backend/README.md](backend/README.md) — 后端开发、`.env` 配置、数据备份细节
- [frontend/README.md](frontend/README.md) — 前端结构与开发
