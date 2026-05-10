# AIIC-Project — Agent 工作指引

## 项目概览

- **当前阶段（2026-05-10）**：v2 ProjectProbe AI 模拟面试官 + **Plan2 长期训练闭环（F1/F2/F4/F5/F7） + Plan3 多模态输入（G1-G5） + Plan3.5 polish pass（5 bugs + 5 improvements + STT API 切换） + Plan3.6 layout fix（view-interview 3-col grid + OS panel 改 inline 列）已实施 + 部署完成**，活跃在 `https://aiic.fomalhaut647.com`。设计 / 实施文档：[`docs/overview.md`](docs/overview.md)、[`docs/specs/`](docs/specs)（含 Plan2 spec D + Plan3 spec E）、[`docs/plans/`](docs/plans)（含 Plan2 plan + Plan3 plan）、[`docs/progress/`](docs/progress)（Plan2/Plan3/Plan3.5 实施回顾）、[`docs/plan4-brainstorm.md`](docs/plan4-brainstorm.md)（Plan4 候选 + 答辩素材草稿）。原题：[`docs/2026-05-09_项目挑战说明.md`](docs/2026-05-09_项目挑战说明.md)
- **v1 处置**：MiMo web chat 业务代码已归档到分支 `archive/web-chat-v1`，bootstrap commit `975a1f0` 从 main 删除（保留 pixi.toml / pytest.ini / .env / docs/ 等基础设施）
- **类型 / 部署目标**：Python (Pixi)；FastAPI + httpx + DeepSeek + MiMo API；vanilla JS 单页前端 + Web Speech API；通过 `https://aiic.fomalhaut647.com` 提供 web 服务（部署详情见 [`docs/deployment.md`](docs/deployment.md)）
- **代码规模**：main 上 v2 + Plan2 + Plan3 + Plan3.5 + Plan3.6 = bootstrap 后 ~110 commits；core modules: `services/` (Plan3 加 `tts.py` MiMo OpenAI 兼容 audio.speech + `file_parse.py` PDF/Word/MD/TXT 分发) + `server/main.py` (Plan3 加 `POST /api/uploads` + `POST /api/tts/synthesize`；与 Plan2 共享 `_SAFE_ID_RE` regex 但 status 400 vs 404 各 spec-correct 差异化) + `web/` (Plan3 加双独立 toggle 🎤/🔈 + 三 textarea mic 按钮 + view-material 上传按钮 + VoiceInput class + fetchAndPlayTTS；Plan3.6 view-interview 3-col grid + OS panel inline) + `data/uploads/<user_id>/<file_id>.{ext,json}` (Plan3 上传持久化, .gitignore 屏蔽); 测试 **257 passes**（v2 baseline + Plan2 + Plan3 + Plan3.5 + Plan3.6；含 services/stt.py + endpoints_stt + Plan3.5 frontend + Plan3.6 layout 增量约 65 tests）

### Plan2 5 个 features 速览（详见 `docs/progress/Plan2-report.md`）

| feature | 用户路径 | endpoint |
|---|---|---|
| F1 持久化 | localStorage userId 启动生成；review 完成后聚合 SessionMeta 到 `data/users/<id>.json` | `GET /api/users/{id}/profile` (200+empty default) + 6 老 POST 加可选 `user_id` |
| F2 一键重练 | dashboard 时间线点「重练 X」→ interview banner → mini-report modal | `POST /api/interviewer/replay` + `POST /api/interviewer/replay/finish` |
| F4 简历多轮 | 报告页 textarea + 「让 Coach 看看」→ 不限轮次自然收敛 | `POST /api/coach/resume_iterate` (per-session lock 防并发 RMW) |
| F5 .md 导出 | 报告页 + dashboard 时间线两处「下载 .md」按钮 | `GET /api/sessions/{id}/export.md` (text/markdown; charset=utf-8) |
| F7 个人主页 | 全局 floating「我的训练」按钮 → view-profile 第 6 视图 | (前端自带，复用 F1 endpoint) |

### Plan3 5 个 features 速览（详见 `docs/progress/Plan3-report.md`）

| feature | 用户路径 | endpoint / 实现 |
|---|---|---|
| G1 文件上传 | view-material 上传按钮 → multipart POST → 解析回填 textarea + warnings | `POST /api/uploads` (PyMuPDF + python-docx + md/txt 直读；10MB 单文件 / 50MB user 配额；ext 白名单 .pdf .docx .md .txt) |
| G2 STT 麦克风 | 三 textarea (onboarding / interview / resume_iterate) 旁 mic 按钮，pulse 红点 | **Plan3.5 改 MediaRecorder + multipart POST 到 `/api/stt/transcribe`**（services/stt.py 调 MiMo Omni `mimo-v2-omni` via `/v1/chat/completions + input_audio`，ffmpeg 转码 webm→wav 16kHz mono；MiMo gateway 无 `/v1/audio/transcriptions`，必须走 multimodal channel） |
| G3 TTS 朗读 | view-interview 出问题时 speaker on 自动 fetch → blob → Audio.play | `POST /api/tts/synthesize` 返 audio/mpeg；MiMo `mimo-v2.5-tts` (OpenAI 兼容 /v1/audio/speech)；503 fallback 静默降级 |
| G4 双独立 toggle | nav header 🎤/🔈，默认 off + localStorage 持久化 + 中途切换立即停掉对应通道 | (前端 state，无 endpoint) |
| G5 后端 TTS 封装 | 单调用入口 + retry-once on httpx.NetworkError + 缺 MIMO_API_KEY fail-fast | `services/tts.py:synthesize_speech` |

### Plan3.5 polish pass 速览（详见 `docs/progress/Plan3.5-report.md`）

- **5 bugs**：mic 椭圆 / 用户气泡对齐 / TTS 听不到（autoplay 3-stack）/ 内心 OS layout 隐式解 / STT 改 MediaRecorder+API
- **5 improvements**：3-col layout（左 sidebar 阶段 + 反馈 / 中对话 / 右 OS）/ 输入框加高 / humor_card 后端固定模板（删 LLM 调）。**注意**：Plan3.5 的"右 OS"实施时是 `position: fixed` 滑入抽屉, **Plan3.6 改为常驻第 3 grid 列**（参见下方 Plan3.6 速览）
- **STT 实施关键**：MiMo `/v1/audio/transcriptions` 不存在；用 `mimo-v2-omni` 多模态 via `/v1/chat/completions + input_audio` 字段；ffmpeg conda dep（pixi `ffmpeg = ">=8.1.1,<9"`）转码 webm/opus → wav 16kHz mono（MiMo 服务器只解码 mp3/flac/m4a/wav/ogg 不接 webm）
- **PR workflow**：拆两 PR 并行（PR #5 backend / PR #6 frontend），各派 fresh reviewer 5-并行 + Haiku confidence scoring < 80 丢弃；PR #5 squash merge / PR #6 rebase merge（CLAUDE.md global 跨域多 commit 用 rebase）

### Plan3.6 layout fix 速览（view-interview 3-col grid + OS panel inline）

修复 Plan3.5 实施后两个 layout bug：

- **Bug A（右侧空间浪费）**：`#app { max-width: 920px }` 把整页钳在 920px 中央 + `.interview-layout` 是 2-col grid（sidebar + main），右半屏黑色空白 30-40%。
- **Bug B（OS panel overlay）**：`#cheat-panel` 用 `position: fixed; right: 0; transform: translateX` 滑入 drawer，**不参与 layout flow**，展开时遮挡 textarea + 提交按钮。

修复方向：
- `#view-interview` 用 CSS full-bleed 跳出 `#app` 920px 钳制（`width: 100vw; margin-left: calc(-50vw + 50%)`），仅作用于面试视图（其他视图不变）。`html, body { overflow-x: clip }` 防滚动条宽差导致横向溢出
- `.interview-layout` 重写为 **3-col grid** `[sidebar 220-280px] [main 420-720px] [cheat-panel 280-380px]`，`max-width: 1500px; margin: 0 auto`
- `#cheat-panel` 从 `position: fixed` drawer → `position: sticky; top: 24px` 内联 grid 列（删 transform / box-shadow / `.hidden { display: block !important }` override；改 `role="complementary"`）
- `#btn-cheat-toggle` 从视口边缘 vertical tab → `.interview-sidebar` 内 inline button (`.cheat-toggle-inline`)
- `.interview-layout.cheat-collapsed` class：用户主动 hide OS 时，grid 退化 2-col 让主区拉宽
- 默认行为变更：`state.current_os` 存在时 panel **默认展开**（旧 drawer 时代默认收起因为会 overlay）
- 响应式：`@media (max-width: 1024px)` panel 跳到第 2 行 `grid-column: 1 / -1`；`@media (max-width: 720px)` 单列堆叠

DOM 契约保留（5 条硬约束）：所有 id / class / API / 数据流 / 依赖均不变。`#btn-cheat-toggle` `#cheat-panel` `.interview-layout` `.interview-sidebar` `.interview-main` 等 app.js 事件挂钩点全部保留。

测试：在 `tests/test_web_dom_plan3.py` 加 5 条 DOM contract test（3-col grid / no `position: fixed` / no drawer-tab class / panel inside layout / toggle inside sidebar）。Total: **257 passes**（252 baseline + 5 layout）。

## 项目挑战说明（2026-05-09 主办方下发）

> 原始 PDF 转写见 `docs/2026-05-09_项目挑战说明.md`（由 PyMuPDF 抽取）。下面为要点速览，全文以 `.md` 为准。

### 题目
**AI 模拟面试官·16 小时项目挑战**

### 关键时间点
- **题目公布**：2026-05-10（周日）08:00
- **代码 / 部署截止**：2026-05-10（周日）24:00（以邮件服务器时间戳为准；之后任何 commit / build / deploy 都判**超时**）
- **公网 URL 在线时长**：至 2026-05-15 24:00
- **答辩**：挑战结束后第二周 1v1 现场答辩（会问项目细节，每一处实现都要能讲清）

### 目标用户
本科生准备**大厂实习面试**或**保研复试**。已知痛点：
- 找不到资深学长 / 专业人士进行高频对练
- 缺乏针对性、可执行的反馈
- 其他痛点**待补充**（鼓励"做深做窄"，自己访谈用户后定）

### 必交清单
1. **Demo 视频**（≤3 分钟）：覆盖 ① 目标用户/痛点 ② 设计思路与取舍 ③ 核心功能演示 ④ 其他。一镜到底即可
2. **公网产品 URL**（在线至 5/15 24:00）：登录给测试账号；API/额度/部署受限要写明；2 把主办方 SSH key 已部署到 `43.156.109.192`，无法登录 = 视为产品无法访问
3. **Product Memo**（1-2 页）：见下结构
4. **GitHub 仓库**：public，README 含简介/运行方式/技术栈，commit history 清晰（一次性提交扣分）

### Product Memo 结构
1. 目标用户与核心痛点（访谈了谁？真实场景？）
2. 产品设计说明（核心功能？刻意不做什么？为什么？）
3. 版本迭代记录（最初方案 → 遇到什么 → 怎么改 → 为什么）
4. 下一步设计（再给一周怎么做）
5. AI 工具使用（哪些工具用在哪些环节）

### 评分维度（重点）
1. 是否真正理解目标用户
2. 是否抓住最核心的产品功能闭环
3. 有限时间内是否做出**可用**产品
4. 是否有效使用 AI 完成设计/开发/测试
5. 是否体现快速学习 / 迭代 / 主动解决问题
6. 是否像创业者一样思考（而非应试）

**核心评分句**：「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」每个设计决策都要回答这个问题

### 提交方式
邮件 → **mlic@pku.edu.cn**，截止以邮件服务器时间戳为准

### 主办方建议（不强制但都是 signal）
- **前 1 小时不写代码**，先想清楚目标用户 / 核心场景 / MVP 边界
- 找几个真实用户聊一聊（哪怕微信问 5 个问题），别纯靠想象
- **核心闭环优先**：一个完整闭环 > 五个半成品
- commit 频繁；demo 视频前 30 秒决定生死，wow moment 放最前
- **不要做现有产品的复刻**

### 公平 / 诚信
- 允许任何 AI Coding 工具 / 开源代码 / API
- 必须**清楚标注**哪些是自己写、哪些 AI 生成、哪些 fork
- 测试用脱敏简历或假数据，不要用真人信息

### 报销
上限 **¥150**：AI Coding 订阅 / LLM tokens / 多模态 API / 云服务器 / 其他。需 invoice 或截图

## 部署

线上部署现状（服务器 / Nginx / SSL / Basic Auth / v1 反代配置）详见 [`docs/deployment.md`](docs/deployment.md)。下面只列每次操作必须 top-of-mind 的 gotcha：

- **服务器**：腾讯云新加坡 `43.156.109.192`，`ubuntu` 用户免密 sudo；80/443 入站走腾讯云**安全组**（控制台维护），UFW 当前 inactive，**不要启用**（会锁死自己）
- **Nginx 1.24（不是 1.25）**：site 配置必须用旧式 `listen 443 ssl http2;`，**不要**用 `http2 on;` 独立指令（1.25+ 才有）
- **SSL 证书到期 2026-08-05**（每 3 个月续签）；**证书 zip / `.env` / Basic Auth 口令绝禁 commit**（public 仓库 = 公开；曾误入两次后用 `git filter-branch` 全历史 sed-replace 清除）
- **公网 IP 验证用 `curl -s -4 ifconfig.me`**：默认可能返回 IPv6，与 DNS A 不匹配
- **临时解压证书后必须 `rm -rf` 清理**：私钥不能留在临时目录
- **nginx `client_max_body_size` Plan3 后必须 ≥ 12M**：FastAPI 默认 multipart limit 没事，但 nginx 默认 1M 会先拦住；Plan3 G1 上传 10MB 文件留 margin 设 12M。检查：`sudo grep -rn client_max_body_size /etc/nginx/`；如未配在 server block 加一行 + `sudo nginx -t && sudo systemctl reload nginx`
- **Plan3 PR review workflow（首用，与 Plan2 直接 main 不同）**：feature branch 在 `.worktrees/<name>` 隔离实施 → teammate `superpowers:finishing-a-development-branch` 自查 + `commit-commands:commit-push-pr` 开 PR → maintainer 派**新** teammate 激活 `code-review:code-review` 审 PR → implementer 用 `superpowers:receiving-code-review` 五步评估迭代 → reviewer APPROVED 后 maintainer 负责 `gh pr merge`（不让 implementer 自 merge）。Plan3 PR #4 走完 3 round 流程：22 commits + 2 review-fix；merge 用 `--rebase` 保留 commit 粒度（CLAUDE.md global 跨域多 commit 默认 rebase）

## 环境约定

- Python 环境用 **Pixi**（`pixi install` / `pixi run <task>`），不要混用 venv / conda
- 项目作者：Fomalhaut647 `<fomalhaut@stu.pku.edu.cn>`

## 密钥与配置

- **`.env`** 存敏感配置，由用户级 `~/.gitignore_global`（第 248 行 `.env`）兜底屏蔽，**禁止 commit**。当前包含：
  - `MIMO_API_KEY` — Plan3 G3 TTS provider (services/tts.py + /api/tts/synthesize) **+ Plan3.5 Bug 3 STT** (services/stt.py + /api/stt/transcribe via mimo-v2-omni); 缺失时 endpoint 503 "TTS not configured" / "STT not configured"。v1 web chat 已弃用，maintainer 复用同 key
  - `MIMO_BASE_URL` (可选) — Plan3 TTS + Plan3.5 STT endpoint，缺省 `https://token-plan-cn.xiaomimimo.com/v1`
  - `MIMO_MODEL` (可选) — Plan3 TTS model，缺省 `mimo-v2.5-tts`
  - `MIMO_OMNI_MODEL` (可选) — Plan3.5 STT 多模态模型（chat.completions + input_audio），缺省 `mimo-v2-omni`
  - `DEEPSEEK_API_KEY` — v2 ProjectProbe Coach + Interviewer LLM provider
  - `DEEPSEEK_BASE_URL` (可选) — DeepSeek API 端点，缺省 `https://api.deepseek.com`
  - `DEEPSEEK_MODEL` (可选) — 缺省 `deepseek-chat`
- **加载方式**：`python-dotenv`（`pixi.toml` 已固定 `>=1.2.2,<2`）→ `from dotenv import load_dotenv; load_dotenv()` → `os.environ["..."]`
- **新增 secret 流程**：写入 `.env`，并在本节末尾追加一行说明用途

## v1 (web chat) 历史 gotchas

v1 业务代码已归档到 `archive/web-chat-v1`，main 即将清理。如果新实现继续用 FastAPI + httpx + SSE，下面坑仍可能踩：

- **MiMo `mimo-v2.5-pro` SSE 双流**：每个 chunk `delta` 可能同时含 `reasoning_content`（CoT）和 `content`（最终回复）；前端**只渲染 `content`**（避免泄露 CoT）
- **httpx 测试 mock 流式响应必须用 `stream=AsyncByteStream(body)`**：`httpx.Response(content=...)` 在 init 立即 read，使 `aiter_raw()` 抛 `StreamConsumed`
- **`TestClient(app)` 不触发 lifespan**：要用 `app.state.*` 必须 `with TestClient(app) as c: yield c`
- **`httpx.InvalidURL` 不继承 `httpx.HTTPError`**：generator 兜底要用 `except Exception`，否则 200 已发出后异常 = client 收到 truncated stream 无 error 帧
