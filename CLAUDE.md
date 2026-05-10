# AIIC-Project — Agent 工作指引

## 项目概览

- **当前阶段（2026-05-10）**：v2 ProjectProbe AI 模拟面试官**已实施 + 部署完成**，活跃在 `https://aiic.fomalhaut647.com`。设计 / 实施文档：[`docs/overview.md`](docs/overview.md)、[`docs/specs/`](docs/specs)、[`docs/plans/`](docs/plans)。原题：[`docs/2026-05-09_项目挑战说明.md`](docs/2026-05-09_项目挑战说明.md)
- **v1 处置**：MiMo web chat 业务代码已归档到分支 `archive/web-chat-v1`，bootstrap commit `975a1f0` 从 main 删除（保留 pixi.toml / pytest.ini / .env / docs/ 等基础设施）
- **类型 / 部署目标**：Python (Pixi)；FastAPI + httpx + DeepSeek API；vanilla JS 单页前端；通过 `https://aiic.fomalhaut647.com` 提供 web 服务（部署详情见 [`docs/deployment.md`](docs/deployment.md)）
- **代码规模**：main 上 v2 = bootstrap 后 44 commits；core modules: `services/` (后端智能) + `server/main.py` (FastAPI) + `web/` (前端 SPA) + `scripts/synthesize_questions.py` (离线题库合成) + `data/question_bank.{seed,synthetic}.json` (12 seed + 36 reviewed=true 合成题)；测试 59 passes

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

## 环境约定

- Python 环境用 **Pixi**（`pixi install` / `pixi run <task>`），不要混用 venv / conda
- 项目作者：Fomalhaut647 `<fomalhaut@stu.pku.edu.cn>`

## 密钥与配置

- **`.env`** 存敏感配置，由用户级 `~/.gitignore_global`（第 248 行 `.env`）兜底屏蔽，**禁止 commit**。当前包含：
  - `MIMO_API_KEY` — v1 web chat 用，v2 已弃用
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
