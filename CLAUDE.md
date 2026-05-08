# AIIC-Project — Agent 工作指引

## 项目概览

- **类型**：Python 项目（Pixi 管理，见 `pixi.toml`）；当前处于早期阶段，业务代码尚未进入仓库
- **部署目标**：通过 `https://aiic.fomalhaut647.com` 提供 web 服务

## 服务器

| 项 | 值 |
|---|---|
| 厂商 / 区域 | 腾讯云轻量应用服务器，新加坡 |
| OS | Ubuntu 24.04 LTS |
| 公网 IPv4 | `43.156.109.192` |
| 用户 | `ubuntu`（免密 sudo） |
| 域名 | `aiic.fomalhaut647.com`（DNS A 已指向公网 IP） |

腾讯云**安全组** 80/443 入站规则需在控制台维护（服务器内的 UFW 当前 inactive，不要随便启用以免锁死自己）。

## Nginx 部署现状

- **版本**：apt 安装的 nginx 1.24.0 (Ubuntu)；`systemctl enable --now nginx` 已设置开机自启
- **Site 配置**：`/etc/nginx/sites-available/aiic.fomalhaut647.com`，软链到 `sites-enabled/`；`default` 站点已禁用
- **行为**：`:80` 301 跳转 → `:443 ssl http2`，启用 TLS 1.2/1.3 + HSTS
- **Web root**：`/var/www/aiic/`（属主 `www-data`），当前为占位 HTML
- **日志**：`/var/log/nginx/aiic.{access,error}.log`

### SSL 证书

- **位置**：`/etc/nginx/ssl/aiic.fomalhaut647.com/{fullchain.crt,privkey.key}`（私钥 `600 root:root`）
- **颁发机构**：TrustAsia DV TLS RSA CA 2025（腾讯云签发）
- **有效期**：2026-05-08 → **2026-08-05**（每 3 个月需续签并重新部署）
- **证书来源**：仓库根目录的 `aiic.fomalhaut647.com_nginx.zip`（**仅部署用，含私钥，禁止 commit 进 git**；`.gitignore` 当前未屏蔽，若日后误增类似文件需手工排除）

## 后续部署 Web 应用时的改动入口

Nginx 端只需改 `/etc/nginx/sites-available/aiic.fomalhaut647.com` 中的 `location / {}`：

- **静态站**：把 `root /var/www/aiic;` 指向你的静态目录
- **反代后端**：把 `try_files ...` 整块换成 `proxy_pass http://127.0.0.1:<端口>;` 加上标准 `proxy_set_header` 头

改完执行 `sudo nginx -t && sudo systemctl reload nginx`。

## Gotchas（避免下次踩坑）

- **`http2 on;` 独立指令是 Nginx 1.25+ 才有的语法**；本机 1.24 必须用旧式 `listen 443 ssl http2;`。修改 site 配置时不要回归到新语法
- **本地公网 IP 探测要带 `-4`**：`curl -s ifconfig.me` 默认可能返回 IPv6，但 DNS A 记录是 IPv4，验证时用 `curl -s -4 ifconfig.me` 才对得上
- **临时解压证书后必须清理**：本次部署在 `/tmp/aiic_ssl_extract/` 留过私钥副本，部署完已 `rm -rf` 清理；后续若再次解压务必同样处理

## 环境约定

- Python 环境用 **Pixi**（`pixi install` / `pixi run <task>`），不要混用 venv / conda
- 项目作者：Fomalhaut647 `<fomalhaut@stu.pku.edu.cn>`

## 密钥与配置

- **`.env`**：项目根目录的 `.env` 存放敏感配置，由用户级 gitignore（`~/.gitignore_global` 第 248 行 `.env`）兜底屏蔽，**禁止 commit**。当前包含：
  - `MIMO_API_KEY` — MiMo 大模型 API key
- **加载方式**：使用 `python-dotenv`（已加入 `pixi.toml` 依赖，约束 `>=1.2.2,<2`）。代码中通过 `from dotenv import load_dotenv; load_dotenv()` 后用 `os.environ["MIMO_API_KEY"]` 读取
- **新增 secret 流程**：直接写入 `.env`（无需改 `.gitignore`），并在本节末尾追加一行说明该变量用途
