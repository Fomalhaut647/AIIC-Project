# 部署文档

> `aiic.fomalhaut647.com` 线上部署现状与操作手册。CLAUDE.md 的「部署」节只列必须 top-of-mind 的 gotcha，详细路径 / 版本 / 配置在这里。

## 服务器

| 项 | 值 |
|---|---|
| 厂商 / 区域 | 腾讯云轻量应用服务器，新加坡 |
| OS | Ubuntu 24.04 LTS |
| 公网 IPv4 | `43.156.109.192` |
| 用户 | `ubuntu`（免密 sudo） |
| 域名 | `aiic.fomalhaut647.com`（DNS A 已指向公网 IP） |

腾讯云**安全组** 80/443 入站规则需在控制台维护（服务器内的 UFW 当前 inactive，不要随便启用以免锁死自己）。

主办方 SSH 公钥已部署到 `~ubuntu/.ssh/authorized_keys`：

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDuSpd2QiAYU0Er1upObsQitqG5JQ3senYa2imOvcDQl lbh@MacBookPro.local
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICsR0FbL2EzGpR8FytEKni4UFIznz8XiT+xHnX2puF/M di@Dis-MacBook-Air.local
```

## Nginx

- **版本**：apt 安装的 nginx 1.24.0 (Ubuntu)；`systemctl enable --now nginx` 已设置开机自启
- **Site 配置**：`/etc/nginx/sites-available/aiic.fomalhaut647.com`，软链到 `sites-enabled/`；`default` 站点已禁用
- **行为**：`:80` 301 跳转 → `:443 ssl http2`，启用 TLS 1.2/1.3 + HSTS
- **Web root**（静态站时用）：`/var/www/aiic/`（属主 `www-data`）
- **日志**：`/var/log/nginx/aiic.{access,error}.log`

### SSL 证书

- **位置**：`/etc/nginx/ssl/aiic.fomalhaut647.com/{fullchain.crt,privkey.key}`（私钥 `600 root:root`）
- **颁发机构**：TrustAsia DV TLS RSA CA 2025（腾讯云签发）
- **有效期**：2026-05-08 → **2026-08-05**（每 3 个月需续签并重新部署）
- **证书来源**：仓库根目录的 `aiic.fomalhaut647.com_nginx.zip`（**仅部署用，含私钥，禁止 commit 进 git**；`.gitignore` 当前未屏蔽，若日后误增类似文件需手工排除）

## 改动 Nginx 入口

只需改 `/etc/nginx/sites-available/aiic.fomalhaut647.com` 中的 `location / {}`：

- **静态站**：把 `root /var/www/aiic;` 指向你的静态目录
- **反代后端**：把 `try_files ...` 整块换成 `proxy_pass http://127.0.0.1:<端口>;` 加上标准 `proxy_set_header` 头

改完执行 `sudo nginx -t && sudo systemctl reload nginx`。

## 当前线上：v1 web chat 反代（即将被替换）

> v1 (MiMo web chat) 业务代码已归档到 `archive/web-chat-v1` 分支，main 待清理。服务器上 systemd + nginx 仍按 v1 配置在跑；新实现部署时需停 v1 service + 改 nginx + 启新 service。

- **systemd 服务**：`aiic-chat.service`（监听 `127.0.0.1:8000`），unit 模板见 `deploy/aiic-chat.service`
- **本地启动**：`pixi run serve`（带 reload）或 `pixi run serve-prod`
- **测试**：`pixi run test`
- **Nginx**：`location /` 反代到 `:8000`，`proxy_buffering off` 透传 SSE。模板见 `deploy/nginx-aiic.location.conf`
- **Basic Auth**：`/etc/nginx/.htpasswd_aiic`（属主 `root:www-data` 模式 `640`，**禁止 commit**）。当前用户 `aiic`；更换走 `sudo htpasswd /etc/nginx/.htpasswd_aiic <user>`
- **MiMo 上游**：OpenAI 兼容协议 `https://token-plan-cn.xiaomimimo.com/v1`，Bearer key 见 `.env`
- **可用 chat 模型白名单**：`mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2-pro`、`mimo-v2-omni`（在 `server/mimo.py` 维护）
