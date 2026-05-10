> 起草日期：2026-05-08
> 状态：Active
> 子方案编号：A-mimo-web-chat

# A — MiMo Web Chat 第一版设计

## 1. 背景与目标

主办方 5/10 截止前需要部署一个公网可访问的网页，能直接在 web 端与指定大模型完成多轮文本对话（见仓库 `2026-05-07_项目准备说明.md`）。本子方案交付该网页的第一版，托管于已配置好 TLS 的 `https://aiic.fomalhaut647.com`，使用 MiMo 的 OpenAI 兼容协议作为模型后端。

**第一版功能边界**（已与维护者确认）：

- 多轮文本流式 chat
- 模型下拉切换（chat-capable 模型）
- 多会话侧栏（localStorage 持久化）
- HTTP Basic Auth 收口访问

**显式排除**：图片输入、TTS 朗读、登录系统、对话云端持久化、rate limit、token 计费 UI。

## 2. 上游 API

| 项 | 值 |
|---|---|
| Base URL | `https://token-plan-cn.xiaomimimo.com/v1` |
| 协议 | OpenAI Chat Completions 兼容 |
| 认证 | `Authorization: Bearer ${MIMO_API_KEY}` |
| API key 来源 | 项目根 `.env` → `MIMO_API_KEY` |

**已通过实测确认可用模型**（`GET /v1/models`）：

- Chat 用：`mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2-pro`、`mimo-v2-omni`
- 非 chat 排除：`mimo-v2-tts`、`mimo-v2.5-tts`、`mimo-v2.5-tts-voiceclone`、`mimo-v2.5-tts-voicedesign`

> Anthropic 兼容端点（`/anthropic`）本期不使用，但后端在常量层留好可切换的余地。

## 3. 总体架构

```
浏览器 (单页 HTML + vanilla JS)
    │  HTTPS
    ▼
Nginx :443  ── HTTP Basic Auth (htpasswd) ──┐
    │  reverse proxy（关闭 buffering）        │
    ▼                                         │
FastAPI 127.0.0.1:8000  (systemd, pixi run)   │
    │  Bearer ${MIMO_API_KEY}                  │
    ▼                                         │
https://token-plan-cn.xiaomimimo.com/v1       │
                                              │
所有请求 (含 /static/*) 先过 Basic Auth ───────┘
```

**关键决策**：

- API key 必须留服务器端，所以**必须**有后端代理；浏览器只跟自家后端讲话
- 鉴权放 Nginx 层（HTTP Basic Auth），不进应用代码 —— 简单且对 SSE 透明
- 前端单页 + vanilla JS：无构建步骤，5/10 截止前部署摩擦最小
- 流式：从 MiMo → FastAPI → Nginx → 浏览器全链路 SSE 透传

## 4. 后端 (FastAPI)

### 4.1 依赖（追加进 `pixi.toml`）

- `fastapi`
- `uvicorn[standard]`（带 httptools / uvloop）
- `httpx`

### 4.2 路由

| Method | Path | 行为 |
|---|---|---|
| GET | `/` | 返回 `web/index.html`（StaticFiles） |
| GET | `/static/*` | 静态资源（`app.js` / `styles.css` 等） |
| GET | `/api/models` | 返回 chat 模型白名单（硬编码常量数组） |
| POST | `/api/chat` | SSE 代理转发到 MiMo `/v1/chat/completions` |
| GET | `/api/health` | 200 OK，部署/监控用 |

### 4.3 `/api/chat` 行为细则

**入参**（JSON）：

```json
{
  "model": "mimo-v2.5-pro",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": true
}
```

**校验**：

- `model` 必须在白名单中，否则返回 400
- `messages` 非空、每项有 `role` ∈ `{system,user,assistant}` 与字符串 `content`
- `stream` 必须为 true（本期不支持非流式）

**转发**：

- 用 `httpx.AsyncClient.stream("POST", ...)` 透传 body 与上游 SSE
- 响应头：`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`、`Connection: keep-alive`
- 上游错误（4xx/5xx）：透传 status code 与 JSON body 给前端，让前端在消息流里渲染错误气泡

### 4.4 配置加载

- `python-dotenv` 在进程启动时 `load_dotenv()`
- 缺 `MIMO_API_KEY` → 启动失败并打印明确错误
- 模型白名单写死在 `server/main.py`（或抽到 `server/mimo.py`）

## 5. 前端 (单页 HTML + vanilla JS)

### 5.1 文件

- `web/index.html` — 整页骨架
- `web/app.js` — 状态管理 + 渲染 + 流式拉取
- `web/styles.css` — 简约暗色主题
- 通过 CDN 引入：`marked`（Markdown 渲染）、`highlight.js`（代码高亮，可选）

### 5.2 布局

```
┌──────────────┬────────────────────────────────┐
│ 会话列表      │  ┌─模型下拉────────────────┐    │
│ + 新建        │  │ mimo-v2.5-pro       v │    │
│ • 会话 A ✏ ✕  │  └─────────────────────────┘    │
│ • 会话 B      │                                │
│ • 会话 C      │  [user]   你好                  │
│              │  [assistant] 你好！...          │
│              │  [assistant] (streaming...)     │
│              │                                │
│              │  ┌─输入框───────────┐ [发送]    │
│              │  └──────────────────┘           │
└──────────────┴────────────────────────────────┘
```

### 5.3 状态模型

```
LocalStorage 顶层 key: "aiic.chat.v1"
{
  conversations: [
    {
      id: string,           // crypto.randomUUID()
      title: string,        // 默认首条 user 消息前 24 字符
      model: string,        // 创建时所选模型
      messages: [{role, content}, ...]
    }
  ],
  activeId: string | null
}
```

- 任何消息变动都在写完后 `localStorage.setItem` 落盘
- 刷新后从 localStorage 恢复

### 5.4 行为

- **新建会话**：左上角 `+ 新建`，置当前；空消息列表
- **切换会话**：点击列表项，主区重渲染
- **重命名**：列表项 ✏ 按钮 → `prompt()` 弹窗
- **删除**：✕ 按钮 → `confirm()` 确认；若删的是当前则 fallback 到首项或新建
- **发送**：回车（Shift+回车换行）或点按钮；发送中按钮变"停止"，点击 `AbortController.abort()`
- **流式渲染**：`fetch` + `response.body.getReader()` + `TextDecoder` 解析 SSE，逐 chunk append 到当前 assistant 消息并重 render Markdown
- **错误**：上游错误以特殊样式气泡显示，不写入正式 messages 数组（重发不带错误污染上下文）
- **滚动**：流式期间自动滚到底，但若用户已上滑则不强制

## 6. 部署

### 6.1 systemd unit (`deploy/aiic-chat.service`)

```ini
[Unit]
Description=AIIC MiMo Chat (FastAPI)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AIIC-Project
ExecStart=/home/ubuntu/AIIC-Project/.pixi/envs/default/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### 6.2 Nginx site config 改动（`/etc/nginx/sites-available/aiic.fomalhaut647.com`）

`location / {}` 整块替换为：

```nginx
auth_basic "AIIC Chat";
auth_basic_user_file /etc/nginx/.htpasswd_aiic;

proxy_pass http://127.0.0.1:8000;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

# SSE 关键：必须关闭缓冲
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 600s;
```

### 6.3 部署步骤（实施计划阶段细化）

1. `pixi add` 后端依赖
2. 写后端 + 前端代码
3. 本地 `pixi run uvicorn ... --port 8000` 自测
4. `sudo cp deploy/aiic-chat.service /etc/systemd/system/` → `systemctl enable --now aiic-chat`
5. 生成 htpasswd：`sudo htpasswd -c /etc/nginx/.htpasswd_aiic <用户名>`
6. 替换 nginx site 的 `location /`，`nginx -t && systemctl reload nginx`
7. curl 验流式 + 浏览器实测
8. 提交 + 更新 `CLAUDE.md`

## 7. 测试策略

### 7.1 自动化（pytest）

- `tests/test_models_endpoint.py`：白名单返回正确
- `tests/test_chat_validation.py`：非法 model / 空 messages → 400
- `tests/test_chat_streaming.py`：用 `httpx.MockTransport` 模拟 MiMo 返回 SSE，断言 FastAPI 端按 chunk 透传
- `tests/test_chat_upstream_error.py`：MiMo 返回 401/500 时，FastAPI 透传 status + body

### 7.2 手动

- 浏览器访问域名，先弹 Basic Auth → 输对凭据进入页面
- 创建会话、发消息、看流式渲染、切换会话、删除、刷新后恢复
- 模型切换后再发消息，观察请求 payload 中 `model` 字段
- 移动端响应式：iOS Safari / Android Chrome 一遍

### 7.3 端到端验收

`https://aiic.fomalhaut647.com` 完成至少 3 轮多轮对话，流式可见，刷新后历史还在。

## 8. 风险与 gotchas

- **Nginx SSE 缓冲**：`proxy_buffering off` 必加，否则浏览器看不到流式
- **应用层双保险**：响应头加 `X-Accel-Buffering: no`
- **HTTP Basic Auth 凭据明文经网络**：HTTPS 已强制，可接受；htpasswd 文件 `600 www-data:www-data`，**禁止 commit**
- **`http2 on;` 语法**：本机 nginx 1.24，保留旧式 `listen 443 ssl http2;`，不要切新语法
- **流式中断**：用户按"停止"后前端 abort，**后端的 httpx stream 也要随之关闭**（FastAPI `StreamingResponse` 收到客户端断连会传播取消，但需要确认 httpx 客户端 cancel 干净，避免 socket 泄漏）
- **会话 token 涨爆**：第一版不裁剪 messages，靠用户自己新建会话；UI 显示当前消息条数即可
- **localStorage 容量**：浏览器一般 5–10 MB，第一版不显式管理；超限报错时简单 toast 提示

## 9. 文件结构

```
AIIC-Project/
├── pixi.toml                  # 加 fastapi / uvicorn / httpx
├── .env                       # 已存在，含 MIMO_API_KEY
├── server/
│   ├── __init__.py
│   ├── main.py                # FastAPI app + 路由
│   └── mimo.py                # MiMo 上游常量 + httpx 流式封装
├── web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
│   ├── test_models_endpoint.py
│   ├── test_chat_validation.py
│   ├── test_chat_streaming.py
│   └── test_chat_upstream_error.py
├── deploy/
│   ├── aiic-chat.service
│   └── nginx-aiic.location.conf  # 仅 location /，便于复制粘贴
└── docs/specs/2026-05-08-mimo-web-chat-design.md   # 本文件
```

## 10. 后续可拓展（不在本期范围）

- 图片输入（vision）走 `mimo-v2-omni`
- TTS 朗读 assistant 回复（`mimo-v2.5-tts`）
- Anthropic 兼容端点切换
- 会话云端持久化 + 多用户登录
- 上下文窗口可视化与自动裁剪
