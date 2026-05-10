# AIIC ProjectProbe — AI 模拟面试官

> **不是再问你一堆八股题，而是把你的项目追问到讲明白。**

面向准备 **AI 方向保研复试 / AI 岗位面试** 的本科生的项目深挖训练器。Demo: <https://aiic.fomalhaut647.com>（Basic Auth：账号见提交邮件）。

## 这是什么

ProjectProbe 由两个 AI 角色组成：

- **Coach（训练组长）**：了解你 + 制定训练路线 + 复盘 + 改简历 + **多轮迭代评估**（Plan2 F4）
- **Interviewer（面试官）**：模拟陌生复试老师 / 面试官，按状态机连续追问你的项目，**支持薄弱项重练模式**（Plan2 F2）

核心差异 vs 直接用 ChatGPT：

| 维度 | ChatGPT 裸用 | ProjectProbe |
|---|---|---|
| 追问稳定性 | 不稳定，容易变成泛泛聊天 | S1-S6 状态机 + required slots 强制深挖 |
| 反馈具体性 | 经常抽象「建议更具体」 | 指出 missing slots + what_i_want_to_hear |
| 元认知 | 不知道为什么被追问 | **作弊模式：偷看面试官脑回路** — 看到面试官在想什么 |
| 训练路线 | 自己规划 | Coach 根据表现安排下一轮 |
| **跨 session 记忆** | 每次重新粘项目 | **持久化 + 个人主页 dashboard 看历史训练** （Plan2 F1+F7） |
| **薄弱项闭环** | 答完没下文 | **一键重练 + mini-report 量化覆盖度提升** （Plan2 F2） |
| **简历改完验证** | 改完不知道好没 | **多轮迭代直到 missing_evidence 全覆盖** （Plan2 F4） |
| **复盘留存** | 输出无结构 | **8 段 Markdown 导出（含面试官 OS）** （Plan2 F5） |

## 核心闭环（demo 路径）

1. 首页 → 「使用示例项目体验」（财会 Agent 项目预填）
2. Interviewer 提问（S1 项目动机：「你是怎么发现这个痛点真实存在的？」）
3. 用户答（演示故意答空泛）
4. 系统识别 **缺失槽位** + 给反馈 + 追问
5. 展开 **作弊模式**，看面试官内心 OS（hidden_concern / why_this_question / risk_level）
6. 答几轮真实回答 → 状态机推进
7. **最终报告**：总分 / 关键证据 / 最危险追问 / **简历改写** / 下一轮训练计划 / **幽默卡片**

## 技术栈

- **后端**：FastAPI + httpx + python-dotenv (Pixi-managed)
- **前端**：单页 vanilla HTML/CSS/JS，无构建步骤；Plan2 加 6th view（个人主页 dashboard）+ mini-report modal + resume iterate UI
- **LLM**：DeepSeek API（OpenAI 兼容）+ JSON repair retry + fallback 模板
- **持久化**：in-memory dict + JSON 文件 dump；Plan2 加 `data/users/<user_id>.json` 用户聚合视图（atomic .tmp+rename + per-user asyncio.Lock）
- **用户身份**：Plan2 加 anonymous user_id (localStorage uuid)；6 个 v2 endpoint 透传可选 user_id（默认 anonymous 向后兼容）
- **题库**：12 hand-written seed + 离线 DeepSeek 合成扩展到 ~60 cards（reviewed=true 36 张进入运行时）
- **部署**：systemd unit + Nginx 1.24 + TLS (TrustAsia DV) + Basic Auth

## Quick start

```bash
# 1. 克隆 + 配置 .env
git clone <repo>
cp .env.example .env  # 填入 DEEPSEEK_API_KEY

# 2. 装环境
pixi install

# 3. 跑测试
pixi run test  # 136 tests pass (59 v2 baseline + 77 Plan2)

# 4. 起服务（dev mode 带 reload）
pixi run serve  # http://127.0.0.1:8000

# 5.（可选）合成题库（一次性，~15min）
pixi run synthesize-questions

# 6. 后端 e2e smoke（real DeepSeek，跑通 onboard → plan → start → next×3 → review）
pixi run python scripts/smoke_e2e.py
```

## 项目结构

```
services/                  Pydantic schemas + LLM 封装 + Coach + Interviewer
  ├── schemas.py           UserModel / InterviewPacket / InterviewTurn / EvaluationReport / QuestionCard
  ├── prompts.py           Coach + Interviewer prompt 字面常量
  ├── llm.py               DeepSeek async client + JSON repair retry + fallback
  ├── store.py             in-memory SessionStore + JSON 文件 dump
  ├── coach.py             onboard / plan / review 三个能力
  ├── interviewer.py       状态机 + slot 检测 + interviewer_os 生成
  └── question_bank.py     运行时题库查询 (target/state/tag filter)

server/main.py             FastAPI app: 8 endpoints + lifespan + 静态挂载
web/                       单页 SPA: 5 视图 (home/onboarding/material/interview/report)
scripts/                   smoke_e2e.py + synthesize_questions.py (离线合成脚本)
data/question_bank.{seed,synthetic}.json   题库
docs/                      overview.md + specs/ + plans/ (设计 + 实施文档)
tests/                     pytest suite (59 tests)
```

## 文档

- [`docs/overview.md`](docs/overview.md) — v2 总纲（双 Agent 架构 / 状态机 / 题库 / P0 边界）
- [`docs/specs/`](docs/specs) — 子方案设计（A 后端智能 / B 题库 / C API+前端）
- [`docs/plans/`](docs/plans) — 实施 plan（Plan1A/B/C，含 bite-sized TDD 任务）
- [`docs/2026-05-09_项目挑战说明.md`](docs/2026-05-09_项目挑战说明.md) — 主办方原题
- [`docs/deployment.md`](docs/deployment.md) — 服务器 / nginx / SSL / Basic Auth 部署细节

## AI 工具使用

整个项目用 **Claude Code (Opus 4.7)** 协调实施：

- **设计阶段**：人工与 Claude brainstorm → Claude 起草 spec/plan → 人工 review
- **实施阶段**：3 个并行 implementer teammate（impl-A 后端 / impl-B 题库 / impl-C API+前端），每个在隔离 git worktree 工作
- **Review 阶段**：3 个独立 reviewer teammate（用 `code-review` skill 5-parallel + Haiku confidence scoring），每个审一个 PR
- **修复阶段**：原 implementer 收到 ≥80 conf issues 后用 `receiving-code-review` skill 五步评估流程修
- **总耗时**：从 brainstorm 到部署 ~4h（包括 2 轮 reviewer + fix loop 的 process discipline）

详细 commit history 在 main 上 44 commits past bootstrap，每个 commit 一个独立故事便于 git bisect。

## License

待补
