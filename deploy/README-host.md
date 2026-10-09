# Ubuntu 22.04: Git + systemd 部署

API 和 Worker 直接运行在宿主机，Mihomo 也运行在宿主机；PostgreSQL 可由本机安装或单独使用 Docker。准备 Python 3.13、Node.js 24、Git、Nginx；仅在使用容器数据库时安装 Docker Engine 和 Compose 插件。以下路径固定为 `/opt/apps/novelaipay`，服务用户为 `novelaipay`。

## 首次部署

```bash
sudo useradd --system --home /opt/apps/novelaipay --shell /usr/sbin/nologin novelaipay
sudo mkdir -p /opt/apps/novelaipay
sudo chown novelaipay:novelaipay /opt/apps/novelaipay
sudo -u novelaipay git clone https://github.com/Kala9527/novelaipay.git /opt/apps/novelaipay
cd /opt/apps/novelaipay
sudo -u novelaipay cp .env.example .env
sudo -u novelaipay cp config.example.yaml config.yaml
```

编辑 `.env` 中的数据库凭据、`APP_SECRET_KEY`、`UPSTREAM_KEY_ENCRYPTION_KEY` 和 `PAYMENT_WEBHOOK_SECRET`，以及 `config.yaml` 中的管理员信息。Fernet 密钥可用 `python3.13 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'` 生成；各密钥使用不同随机值。确保文件属主为 `novelaipay`，权限为 600，且 `DATABASE_URL` 未设置，否则它会覆盖 `DB_HOST`/`DB_PORT`。

若添加出口代理时报 `Fernet key must be 32 url-safe base64-encoded bytes`，说明宿主机 `.env` 的 `UPSTREAM_KEY_ENCRYPTION_KEY` 格式错误，与代理地址无关。先在 `backend` 目录运行 `../.venv/bin/python -c 'from app.config import get_settings; get_settings(); print("encryption key OK")'` 检查配置。首次部署且尚无已加密的上游密钥、代理地址或 SMTP 密码时，可用上面的命令生成新 key，替换 `.env` 中的占位值，再重启 API 和 Worker。已有加密数据时必须找回原来的 Fernet key；随意换 key 会使现有密文无法解密。

如果 PostgreSQL 使用 Docker，保持 `.env` 中 `DB_HOST=127.0.0.1`、`DB_PORT=5433`、`DB_BIND_PORT=5433`，运行：

```bash
docker compose -f compose.db.yaml up -d
docker compose -f compose.db.yaml ps
```

数据库只映射到宿主机 `127.0.0.1:5433`。如果使用已安装的 PostgreSQL，创建 `.env` 中指定的数据库和用户，将 `DB_PORT` 改为实际监听端口（通常为 5432），不用启动 Compose。

```bash
cd /opt/apps/novelaipay
sudo -u novelaipay python3.13 -m venv .venv
sudo -u novelaipay .venv/bin/pip install -r backend/requirements.txt
sudo -u novelaipay npm --prefix frontend ci
sudo -u novelaipay npm --prefix frontend run build
sudo -u novelaipay mkdir -p data/images
cd backend
sudo -u novelaipay ../.venv/bin/python -m app.prepare_db
sudo -u novelaipay ../.venv/bin/python -m app.bootstrap
cd ..
sudo cp deploy/novelaipay-api.service deploy/novelaipay-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now novelaipay-api novelaipay-worker
curl -i http://127.0.0.1:8009/healthz
```

按 [Nginx 配置](novelaipay.nginx.conf) 设置域名和 HTTPS。API 只监听本机 8009 端口，由 Nginx 对外提供服务；图片写入仓库根目录的 `data/images`，备份时须与数据库一起保留。

## Mihomo 出口

在本机运行的 Mihomo 若监听 `127.0.0.1:7890`，管理页“IP 管理”填写 `http://127.0.0.1:7890`。为上游账户选择此代理，使用账户行的网络图标检查连接。API 的检查请求和 Worker 的生图请求都从宿主机发出，无需 `host.docker.internal`、`allow-lan` 或开放 7890 端口。`host.docker.internal` 只用于 API/Worker 也运行在容器中的备用部署方式。未分配代理的账户会遵循 systemd 服务进程的 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量；本项目的 `.env` 由应用读取，单独在其中添加这两个变量不会设置服务进程环境。建议逐账户选择代理。

## Git 更新

更新前备份数据库和 `data/images`，保留 `.env`、`config.yaml` 及原有 Fernet 密钥。然后：

```bash
cd /opt/apps/novelaipay
sudo -u novelaipay git pull --ff-only
sudo -u novelaipay .venv/bin/pip install -r backend/requirements.txt
sudo -u novelaipay npm --prefix frontend ci
sudo -u novelaipay npm --prefix frontend run build
cd backend
sudo -u novelaipay ../.venv/bin/python -m app.prepare_db
sudo -u novelaipay ../.venv/bin/python -m app.bootstrap
cd ..
sudo cp deploy/novelaipay-api.service deploy/novelaipay-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart novelaipay-api novelaipay-worker
sudo systemctl status novelaipay-api novelaipay-worker --no-pager
```

本次 IP 管理功能需要迁移至 Alembic `0017`；`app.prepare_db` 会升级现有数据库。排查时用 `journalctl -u novelaipay-api -u novelaipay-worker -n 100 --no-pager`。回退 Git 代码不会自动回退数据库结构。
