# BWG Panel 后端

搬瓦工 VPS 监控管理面板后端。单体 FastAPI 进程承担全部职责：REST API、KiwiVM 调用、定时采样、告警邮件、前端静态托管。部署方式见仓库根 `README.md`。

## 模块结构

```
app/
├─ main.py        # FastAPI 装配、统一错误处理、SPA 静态托管（frontend/dist）
├─ config.py      # .env 读取、SECRET_KEY 自动生成并写回
├─ db.py          # SQLite 连接 + 版本化迁移
├─ models.py      # 表定义与访问函数
├─ auth.py        # 登录 / 签名 Cookie 会话 / 登录限速
├─ mailer.py      # SMTP 告警邮件
├─ state.py       # 进程内共享状态（客户端工厂、点数缓存等）
├─ routes/        # auth / servers / power / snapshots / alerts / settings / meta
├─ kiwivm/        # KiwiVM API 封装（超时/重试/点数账本）+ mock 假客户端
└─ scheduler/     # sampler 采样器 / alerter 告警状态机
```

## 快速开始

以下命令均在 `backend/` 目录下执行。

```powershell
python -m venv .venv                      # 首次
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env                    # 可留空
.\.venv\Scripts\python.exe -m app --mock  # 离线演示（不消耗 API 点数）
```

- 演示模式内置两台 Mock 服务器（Mock-A / Mock-B），密码打印在控制台。
- 正式模式：`.\.venv\Scripts\python.exe -m app`，登录后通过 `POST /api/servers`
  录入真实 veid + api_key（在 KiwiVM 面板左侧 API 页获取）。
- 交互式 API 文档：http://127.0.0.1:8000/docs

## 配置（backend/.env）

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | 会话签名密钥——更换后所有登录会话失效；留空则首次启动自动生成并写回 |
| `ADMIN_PASSWORD` | 首次启动的管理员初始密码；留空则自动生成并打印到控制台（仅一次） |
| `DB_PATH` | SQLite 路径，默认 `backend/data/panel.db` |
| `COOKIE_SECURE` | 反代 HTTPS 部署时改 `1`：登录 Cookie 仅经 HTTPS 传输 |

`.env` 请保持 UTF-8 编码保存（记事本另存时注意）。

## 数据与备份

- 数据库：`backend/data/panel.db`（SQLite，WAL 模式，目录已被 .gitignore 忽略）。服务器档案、采样历史、告警、设置全部在此一个文件里。
- 备份：先停服再拷贝；或不断服安全备份：
  `.\.venv\Scripts\python.exe -c "import sqlite3; sqlite3.connect('data/panel.db').execute(\"VACUUM INTO 'backup.db'\")"`

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## 开发（热重载）

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload
```

## 安全提示

默认只监听 127.0.0.1。公网访问请用 Caddy/Nginx 反代并加 HTTPS，同时启用 `COOKIE_SECURE=1`。
