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

## Web Chat 应用部署（v1）

- **代码**：`server/`（FastAPI + httpx 流式代理）+ `web/`（vanilla JS 单页）
- **systemd 服务**：`aiic-chat.service`（监听 `127.0.0.1:8000`），unit 模板见 `deploy/aiic-chat.service`
- **本地启动**：`pixi run serve`（带 reload）或 `pixi run serve-prod`
- **测试**：`pixi run test`
- **Nginx**：`/etc/nginx/sites-available/aiic.fomalhaut647.com` 已改 `location /` 反代到 :8000，`proxy_buffering off` 透传 SSE。模板见 `deploy/nginx-aiic.location.conf`
- **Basic Auth**：`/etc/nginx/.htpasswd_aiic`（属主 `root:www-data` 模式 `640`，**禁止 commit**）。当前凭据：`aiic / <REDACTED>`，更换走 `sudo htpasswd /etc/nginx/.htpasswd_aiic <user>`
- **MiMo 上游**：OpenAI 兼容协议 `https://token-plan-cn.xiaomimimo.com/v1`，Bearer key 见 `.env`
- **可用 chat 模型白名单**：`mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2-pro`、`mimo-v2-omni`（在 `server/mimo.py` 维护）

## Gotchas（避免下次踩坑）

- **`http2 on;` 独立指令是 Nginx 1.25+ 才有的语法**；本机 1.24 必须用旧式 `listen 443 ssl http2;`。修改 site 配置时不要回归到新语法
- **本地公网 IP 探测要带 `-4`**：`curl -s ifconfig.me` 默认可能返回 IPv6，但 DNS A 记录是 IPv4，验证时用 `curl -s -4 ifconfig.me` 才对得上
- **临时解压证书后必须清理**：本次部署在 `/tmp/aiic_ssl_extract/` 留过私钥副本，部署完已 `rm -rf` 清理；后续若再次解压务必同样处理
- **MiMo `mimo-v2.5-pro` SSE 双流**：每个 chunk 的 `choices[0].delta` 同时可能含 `reasoning_content`（思维链）与 `content`（最终回复）。前端**只渲染 `content`**，不显示 reasoning（避免泄露 CoT）；未来"修 bug 把 reasoning 也拼上去"是错误方向
- **httpx 测试 mock 流式响应必须用 `stream=AsyncByteStream(body)`**：`httpx.Response(200, content=bytes_body)` 在 `__init__` 立即 read，使 `aiter_raw()` 抛 `StreamConsumed`。见 `tests/test_chat_streaming.py` 的 `_SSEStream` helper —— 这是绕坑，不是风格
- **`TestClient(app)` 不触发 lifespan**：要用 `app.state.*`（如 `http_client`）的测试 fixture 必须用 `with TestClient(app) as c: yield c`。见 `tests/conftest.py`
- **`httpx.InvalidURL` 不继承 `httpx.HTTPError`**：`server/main.py` 的 `event_stream` generator 兜底用 `except Exception` 是有意的—— InvalidURL / 任何意外异常都必须转 SSE error frame，否则 HTTP 200 已发出后 generator 抛异常会让客户端收到 truncated stream 无 error 帧
- **Basic Auth 口令绝不入 repo（含 commit history）**：public 仓库要求决定了任何写进 CLAUDE.md / spec / plan / commit message 的明文密码 = 公开。口令仅在 `/etc/nginx/.htpasswd_aiic` 存在；告知主办方走 IM 渠道。本次曾误入两个 commit 后用 `git filter-branch` 全历史 sed-replace `<REDACTED>` 清除（必要时可复用同样方法）

## 环境约定

- Python 环境用 **Pixi**（`pixi install` / `pixi run <task>`），不要混用 venv / conda
- 项目作者：Fomalhaut647 `<fomalhaut@stu.pku.edu.cn>`

## 密钥与配置

- **`.env`**：项目根目录的 `.env` 存放敏感配置，由用户级 gitignore（`~/.gitignore_global` 第 248 行 `.env`）兜底屏蔽，**禁止 commit**。当前包含：
  - `MIMO_API_KEY` — MiMo 大模型 API key
- **加载方式**：使用 `python-dotenv`（已加入 `pixi.toml` 依赖，约束 `>=1.2.2,<2`）。代码中通过 `from dotenv import load_dotenv; load_dotenv()` 后用 `os.environ["MIMO_API_KEY"]` 读取
- **新增 secret 流程**：直接写入 `.env`（无需改 `.gitignore`），并在本节末尾追加一行说明该变量用途

## 项目准备说明（2026-05-07 主办方下发）

> 原始 PDF 已删除，转写见 `2026-05-07_项目准备说明.md`（由 PyMuPDF 抽取）。下面为要点速览，全文以 `.md` 为准。

### 关键时间点
- **项目开始**：2026-05-10（周日）08:00 公布题目
- **截止后构建/部署 = 超时完成**（主办方会通过 SSH 登录核验部署时间）

### 必备清单
1. **AI Coding 工具**：Claude Code / GPT Codex / Cursor / Kimi Code 等任选，确认额度充足
2. **GitHub 账号**：项目仓库**必须 public**，会查代码与 commit 记录
3. **公网可访问的云服务器**：已具备 —— 见上文「服务器」章节（腾讯云新加坡，`https://aiic.fomalhaut647.com`）
4. **LLM API Keys**：OpenAI / OpenRouter / MiMo 等任选；当前已有 `MIMO_API_KEY`（见上节）
5. **音视频 API**（可选）：火山引擎多模态等，参考 `https://www.volcengine.com/docs/6561/1354845`
6. **录屏/剪辑工具**（可选）：Demo 视频 ≤3 分钟，剪映即可
7. 其他常用工具（外网访问、设计等）

### 主办方 SSH 公钥（必须部署到 `43.156.109.192` 的 `~ubuntu/.ssh/authorized_keys`）

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDuSpd2QiAYU0Er1upObsQitqG5JQ3senYa2imOvcDQl lbh@MacBookPro.local
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICsR0FbL2EzGpR8FytEKni4UFIznz8XiT+xHnX2puF/M di@Dis-MacBook-Air.local
```

主办方需通过 SSH 登录核验运行环境与部署时间，**这两把 key 务必在 5/10 之前添加完毕**。

### 提交清单
- 公网可访问的 URL（一个能调用指定模型 + Prompt 完成文本/语音对话的网页）
- GitHub public 仓库（含完整 commit 记录）
- ≤3 分钟 Demo 视频（说明设计思路 + 演示产品）

### 报销
- 上限 **¥150**（必备工具），需提供 invoice 或截图说明
