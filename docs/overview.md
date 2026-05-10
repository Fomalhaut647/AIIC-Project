# AIIC v2 — ProjectProbe Overview

> 起草日期：2026-05-10
> 版本：v2（AI 模拟面试官 16h Challenge 实现）
> 取代：v1 MiMo Web Chat（已归档到分支 `archive/web-chat-v1`，历史文档在 `docs/archive/v1/`）
> 上游约束：[`2026-05-09_项目挑战说明.md`](2026-05-09_项目挑战说明.md)（主办方需求 / 评分维度 / 截止时间）

---

## 1. 版本动机

v1（MiMo Web Chat）是赛前热身练手，与本次挑战题目无关。本次挑战要求做 **AI 模拟面试官**，目标用户、产品形态、核心闭环全部不同。v2 完全重写业务代码，复用 v1 已验证的部署管道（FastAPI + SSE + nginx Basic Auth + Pixi/Python）。

---

## 2. 一句话定位

**ProjectProbe 是面向准备 AI 方向保研复试 / AI 岗位面试的本科生的项目深挖训练器。**

它不是普通 AI 面试聊天框，而是由 Coach + Interviewer 组成的双 Agent Team。Coach 懂用户 + 制定训练路线 + 复盘 + 改简历；Interviewer 模拟陌生复试 / 面试老师 + 围绕项目连续追问。

---

## 3. 目标用户

### 3.1 双场景

| 场景 | 典型用户 | 偏重 |
|---|---|---|
| **保研复试** | 大三准备保研 AI 方向（如人工智能创新中心、各高校 AI 实验室） | 研究动机、方法新颖性、faculty 匹配、未来研究方向 |
| **AI 岗位面试** | 准备大厂 / 独角兽 AI 算法 / 工程实习与校招 | 工程实现、系统设计、生产化经验、性能 / 成本权衡、团队协作 |

两场景在「项目深挖」层面 80% 重合（动机 / 架构 / baseline / 实验 / 失败反思），仅在 S6（匹配与总结）阶段分叉为两套 prompt 模板。

### 3.2 共同痛点

- 找不到资深学长 / 工程师 / 研究者高频对练
- 没有得到针对性、可执行的反馈
- 不知道老师 / 面试官会如何追问自己的项目
- 简历项目描述写得空泛 / 关键词堆砌但讲不深
- 一次 mock 后没有形成下一轮训练计划

### 3.3 非目标用户（v2 不服务）

- 通用求职者（非 AI 方向）
- 纯算法刷题用户
- 需要真实视频面试的人
- 需要长期职业规划系统的人
- 需要大规模题库刷题的人

---

## 4. 核心洞察 + 差异化

### 4.1 核心洞察

> AI 面试中学生真正的困难不是「没有题目」，而是「不知道自己的项目哪里讲得空、为什么会被追问、答完之后该怎么修」。

所以 ProjectProbe 的核心**不是问更多问题**，而是：**发现回答中的缺失槽位，围绕缺失槽位连续追问，直到把项目讲明白。**

### 4.2 vs 直接使用 ChatGPT

| 维度 | ChatGPT 裸用 | ProjectProbe |
|---|---|---|
| Prompt 工程 | 用户自己写 | Coach 帮你打包 |
| 追问稳定性 | 不稳定，容易变成泛泛聊天 | 状态机 + required slots 强制深挖 |
| 反馈具体性 | 经常抽象「建议更具体」 | 指出缺失槽位 + what_i_want_to_hear |
| 训练路线 | 用户自己规划 | Coach 根据当前表现安排下一轮 |
| 元认知 | 用户不知道为什么被追问 | 作弊模式展示面试官内心判断 |

### 4.3 评分核心句

> 「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」

每个设计决策都要回答这个问题。无法回答 → 砍掉。

---

## 5. 双 Agent Team 架构

### 5.1 设计原则

> 训练系统需要长期理解用户，但模拟面试官必须保持陌生视角。

一个 LLM 同时承担「懂你」+「不懂你」会角色混淆。拆为两个 Agent，信息不对称是设计意图。

### 5.2 Coach（训练组长）

**负责**：
- 用户场景澄清（保研 vs 求职 vs 混合）→ `UserModel.target`
- 维护本 session 用户画像（goal / projects / weaknesses / preferred_style）
- 选定训练模式（普通项目面 / 压力面 / 简历修改 / 薄弱项重练）
- 打包 `interview_packet` 喂给 Interviewer
- 面试结束后基于 `InterviewTurn[]` 生成复盘报告
- 简历项目描述改写
- 幽默卡片生成
- 下一轮训练计划

**不负责**：
- 模拟正式面试官提问
- 在面试过程中替用户回答
- 给 Interviewer 透露用户长期画像 / 弱点

### 5.3 Interviewer（盲测面试官）

**负责**：
- 模拟第一次见到候选人的复试老师 / 大厂面试官
- 只读 `interview_packet` + 项目材料 + 当前对话历史
- 优先围绕项目追问，按状态机推进
- 检查 required slots 是否被覆盖；缺则继续追问
- 输出 `interviewer_os`（作弊模式内容）

**不负责**：
- 任何宏观训练规划
- 安慰 / 鼓励
- 看用户长期画像或过往失败记录
- 自动脑补用户没说出口的信息

### 5.4 Coach 双场景适配（v2 新增）

Coach onboarding 第一轮必问场景：

> "你这次主要是为了准备保研复试，还是 AI 岗位面试？还是两者都准备？"

写入 `UserModel.target ∈ {"保研", "求职", "混合"}`，下游：
- `interview_packet.target` 透传给 Interviewer
- Interviewer prompt 在 S6 状态分两套模板（研究匹配 vs 岗位匹配）
- `QuestionCard.applies_to` 按 target 过滤
- focus_slots 默认值按 target 不同（保研偏研究 / 求职偏工程）

### 5.5 信息流

```
用户输入 (自然语言需求)
   ↓
Coach 澄清 (含场景) → UserModel
   ↓
用户粘贴项目材料
   ↓
Coach → InterviewPacket (含 target / focus_slots / 风格)
   ↓
Interviewer 第一问
   ↓ (循环)
   用户回答 → Interviewer 评估 → InterviewTurn (feedback / missing_slots / next_question / interviewer_os)
   ↓
   覆盖 required slots? → 进入下一状态 / 否则追问
   ↓
面试结束
   ↓
Coach 接收完整 InterviewTurn[] → EvaluationReport
   ├─ 总结 + evidence + dangerous_questions
   ├─ resume_rewrite (original / rewritten / missing_evidence)
   ├─ next_training_plan
   └─ humor_card
```

---

## 6. 项目深挖状态机

Interviewer 不自由聊天。每个状态有 required slots，全部覆盖才跳转。

| 状态 | 名称 | required slots（关键词） |
|---|---|---|
| S1 | 项目动机 | 为什么做 / 目标用户 / 痛点真实性 / 时机 / 与方向相关性 |
| S2 | 项目概述 | 目标 / 输入输出 / 系统架构 / 用户流程 / **个人贡献** |
| S3 | 技术深挖 | 技术方案 / 方法选择理由 / 关键模块 / 替代方案 / 工程实现 |
| S4 | 实验验证 | **baseline** / 指标 / 数据来源 / 评估方法 / 对照实验 / 错误分析 |
| S5 | 失败反思 | 失败 case / 边界条件 / 当前局限 / 风险控制 / 改进方向 |
| S6 | 匹配与总结 | （按 target 双模板）研究方向匹配 / 岗位匹配 / 个人成长 / 适配理由 |

### 跳转规则

- 当前回答覆盖 required slots → 进入下一状态
- 当前回答没覆盖 → 继续追问缺失槽位
- 用户连续回答空泛（≥3 次）→ 降低问题复杂度 + 要求举例 + 必要时切换到基础概念
- 项目材料太少 → 先追问项目背景再进入状态机

---

## 7. 作弊模式

### 7.1 设计目的

让用户**看到面试官在想什么**：为什么追问 / 担心什么 / 想听到什么。这是 ProjectProbe 最大的元认知价值，也是 Demo 视频前 30 秒的 wow moment。

产品化名：「**作弊模式：偷看面试官脑回路**」（默认收起，按钮展开）。

### 7.2 输出结构（`InterviewTurn.interviewer_os`）

```json
{
  "hidden_concern": "候选人可能只讲了架构愿景，但没有真实验证闭环。",
  "why_this_question": "公式验证是这个项目能否落地的核心。如果讲不清，老师会怀疑系统只是 demo。",
  "missing_slots": ["测试样例设计", "异常 case", "baseline"],
  "what_i_want_to_hear": ["如何构造样例数据", "如何覆盖异常 case", "如何设计 baseline"],
  "risk_level": "高"
}
```

### 7.3 防 chain-of-thought 泄露

prompt 显式要求：「不要输出完整推理过程，只输出面向用户的面试官判断摘要。」

---

## 8. 合成题库

### 8.1 策略

P0 必交：12 seed questions（手写覆盖核心追问类型）+ DeepSeek 合成扩展到约 60 条。

合成是**离线一次性脚本**，不在用户运行时调用。结果保存到 `data/question_bank.synthetic.json`，标记 `reviewed=true` 的才进入 demo 路径。

实现策略：用 AgentTeam 派 1 个 implementer 专门负责「seed 撰写 + DeepSeek 合成 + 抽检」，与 Coach/Interviewer 主流程并行开发。

### 8.2 选题优先级（Interviewer 提问时）

1. 基于用户项目和上一轮回答**生成**追问（最优先）
2. 从合成题库中按项目 tags + applies_to 过滤匹配的问题
3. 项目相关基础概念
4. 通用八股（兜底）

### 8.3 QuestionCard 结构

```json
{
  "id": "eval_baseline_001",
  "category": "实验验证",
  "tags": ["baseline", "evaluation", "project_deep_dive"],
  "applies_to": ["保研", "求职"],
  "trigger": "用户项目中提到模型 / Agent / 系统效果 / 自动化提升",
  "question": "你如何证明你的方案比一个更简单的 baseline 更好？",
  "followups": ["你的 baseline 具体是什么？", "你比较的是准确率、效率、成本，还是用户体验？"],
  "good_answer_points": ["明确 baseline", "定义评估指标", "说明数据来源"],
  "red_flags": ["只说效果更好但没有证据", "没有 baseline"],
  "related_slots": ["baseline", "指标", "数据来源", "错误分析"],
  "difficulty": "中",
  "source": "synthetic",
  "reviewed": true
}
```

### 8.4 合成 prompt 关键约束

- 不生成「请介绍你的项目」之类低质问题
- 每题必须有 `followups` + `red_flags` + `related_slots`
- 输出严格 JSON 数组，不带 Markdown / 解释文字
- 按 target 标记 `applies_to`

---

## 9. 简历改写 + 幽默卡片

### 9.1 简历改写

报告页输出 `EvaluationReport.resume_rewrite`：

```json
{
  "original": "我做了一个 AI 财务助理...",
  "rewritten": "我设计并实现了一个面向中小企业的 AI 财务助理：采用'AI 生成公式 + 本地引擎核算'的脱敏架构，AI 不接触真实数值..."，
  "missing_evidence": ["缺少 baseline 对比", "缺少异常 case 覆盖率"]
}
```

Demo 视频 1:50–2:30 evidence 段需要这一段撑场（用户能直观看到「AI 把我的简历改具体了」）。

### 9.2 幽默卡片

`EvaluationReport.humor_card`：标题 + 内容。Coach 生成。规则：
- 必须引用本轮**真实暴露**的具体问题
- 把问题重新解释为「高价值 bug」/ 调试梗 / 数学梗
- 不允许空泛鸡汤
- 结尾给一个具体的下一步动作

---

## 10. 技术栈

| 层 | 选择 | 理由 |
|---|---|---|
| 后端 | FastAPI + httpx + python-dotenv | v1 已验证；SSE 流式 + 异步 LLM 代理走顺 |
| 前端 | 单页 vanilla HTML/CSS/JS | 复用 v1 SSE pipe（含 `reasoning_content` 过滤经验）；无 Node 工具链 |
| LLM | DeepSeek (`DEEPSEEK_API_KEY` 已配置) | 指令遵从 + JSON 输出稳定；Coach/Interviewer prompt 链需要这两点 |
| LLM 封装 | 统一 `services/llm.py` | 业务层不直接调 SDK；统一 retry + JSON repair + 降级模板 |
| 持久化 | in-memory dict + JSON 文件兜底 | **不上 SQLite**；mock 工具，重启丢 session 可接受 |
| 环境 | Pixi (`pixi install` / `pixi run <task>`) | 项目硬约束 |
| 部署 | systemd `aiic-chat.service` + nginx Basic Auth + TLS | 复用 v1 部署管道；细节见 `docs/deployment.md` |

### 10.1 LLM provider 封装契约

```python
# services/llm.py
def call_deepseek(messages, response_schema=None, temperature=0.7, max_tokens=2000) -> dict | str:
    """
    - 自动注入 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL（从 .env）
    - response_schema 给定时：要求 JSON 输出 → Pydantic 校验 → 失败一次 repair retry → 仍失败返回降级模板
    - response_schema 为 None：返回纯文本
    - 统一 logging，便于 Demo 后回放调用链
    """
```

### 10.2 持久化兜底

- session_id → in-memory dict（默认）
- 后台异步 dump 到 `data/sessions/<session_id>.json`（可选，便于复盘）
- 服务重启 = 用户需要重新开始 session（mock 工具的合理边界）

---

## 11. 数据契约（关键结构摘要）

完整 JSON schema 在实现阶段维护到 `services/schemas.py`（Pydantic）。下面只列字段名，便于与 ChatGPT 设计文档 §18 交叉对照。

| 类型 | 关键字段 |
|---|---|
| `UserModel` | id / goal / **target ∈ {保研, 求职, 混合}** / target_program / projects / strengths / recurring_weaknesses / preferred_style / current_stage |
| `TrainingPlan` | recommended_next_step / reason / steps[] |
| `InterviewPacket` | **target** / interviewer_style / intensity / project_summary / focus_slots / constraints / question_policy |
| `InterviewTurn` | id / session_id / state / question / answer / score / covered_slots / missing_slots / feedback / next_question / source / **interviewer_os** |
| `EvaluationReport` | overall_score / summary / strengths / weaknesses / evidence[] / dangerous_questions / **resume_rewrite** / next_training_plan / **humor_card** |
| `QuestionCard` | id / category / tags / **applies_to[]** / trigger / question / followups / good_answer_points / red_flags / related_slots / difficulty / source / reviewed |

**v2 新增字段（vs ChatGPT 设计文档原版）**：`UserModel.target` / `InterviewPacket.target` / `QuestionCard.applies_to`。

---

## 12. 关键 API endpoint

| Endpoint | 用途 | 输入 → 输出 |
|---|---|---|
| `POST /api/coach/onboard` | Coach 澄清需求 | user_message + history → followup_questions / user_model / recommended_config |
| `POST /api/profile/parse` | 项目材料 → 结构化项目画像 | raw_project_text → project_summary / keywords / weaknesses |
| `POST /api/coach/plan` | Coach 生成训练计划 | user_model + project_summary → training_plan + interview_packet |
| `POST /api/interviewer/start` | 第一问 | interview_packet → session_id + state + question |
| `POST /api/interviewer/next` | 用户回答后追问 | session_id + answer → InterviewTurn + should_continue + next_state |
| `POST /api/coach/review` | 最终复盘 | session_id + user_model + turns → EvaluationReport |
| `GET /api/healthz` | 部署检查（主办方 SSH 验证用） | → status / commit_hash / deploy_time / provider |

合成题库 endpoint（`POST /api/question-bank/synthesize`）**不暴露给运行时**，仅作为离线脚本调用入口。

---

## 13. P0 / P1 / P2 边界

### P0（必交）
- DeepSeek API 接入 + 统一 LLM 封装
- Coach 双场景 onboarding
- 项目材料文本输入
- Coach 生成 InterviewPacket
- Interviewer 多轮追问 + 状态机推进
- required slots 检查 + missing_slots 反馈
- **作弊模式**（最大 wow moment）
- 12 seed + DeepSeek 合成扩展到 ~60 题
- 最终报告
- **简历改写**
- **幽默卡片**
- 公网部署 + 主办方 SSH key 验证

### P1（有时间做）
- 浏览器语音输入 / 面试官 TTS 播报
- PDF / Word / 图片项目材料解析
- 报告导出 Markdown
- 题库命中可视化
- 一键重练薄弱项

### P2（不做，写进 Memo「刻意不做」）
- 完整登录系统
- 长期历史 dashboard
- 视频面试
- 多岗位覆盖
- 多 Agent 复杂协作框架（双 Agent 已经够）

---

## 14. Demo 路径与样例

### 14.1 wow moment（视频 0:00–0:30）

**故意触发用户答空 → 系统识别 missing slots → 追问 → 打开作弊模式**。这一段是 ProjectProbe vs ChatGPT 的核心差异化展示。

### 14.2 预置样例项目

首页"使用示例项目体验"按钮加载**财会 Agent 项目**（用户真实项目，已在 ChatGPT 设计文档 §21 展开）。Coach 默认 target=求职。Demo 视频走这条路径。

### 14.3 Demo 视频 3 分钟结构

| 时间 | 内容 |
|---|---|
| 0:00–0:30 | wow moment：用户答空 → 系统追问 + 作弊模式 |
| 0:30–1:00 | 目标用户 + 痛点（保研 + 求职双场景） |
| 1:00–1:50 | Coach 设置 + Interviewer 状态机推进 |
| 1:50–2:30 | 报告 + 简历改写 + 幽默卡片 |
| 2:30–3:00 | 取舍说明（刻意不做语音 / 视频 / 大题库爬虫）+ 下一步 |

---

## 15. 测试账号 + 部署

- **测试账号**：复用 v1 nginx Basic Auth（账号 `aiic` / 密码在服务器 `/etc/nginx/.htpasswd_aiic`）。提交时邮件附账号密码给主办方
- **systemd**：沿用 unit `aiic-chat.service`（v1 部署时已建），新代码替换业务模块即可
- **nginx**：`location /` 反代到 `127.0.0.1:8000`，`proxy_buffering off` 透传 SSE。配置无需改动
- **SSH key**：主办方 2 把 ed25519 key 已部署到 `~ubuntu/.ssh/authorized_keys`（v1 阶段已完成）
- **部署细节**：见 [`docs/deployment.md`](deployment.md)

---

## 16. 风险兜底

| 风险 | 兜底 |
|---|---|
| DeepSeek 输出非法 JSON | Pydantic 校验 → repair prompt 重试一次 → 降级模板 |
| 合成题库质量不稳 | 只用 `reviewed=true`；保留人工 12 seed；demo 路径走稳定样例 |
| 部署出问题 | 优先保 FastAPI + uvicorn 直起；nginx 不行临时开放 8000 端口 |
| 时间不够 | 砍单顺序：语音 → 文件上传 → 题库可视化 → 报告导出 → UI 动画 |
| 死保不能砍 | Coach / Interviewer / 项目追问 / 作弊模式 / 最终报告 / 公网部署 |

---

## 17. 子模块清单 / 里程碑地图

按 CLAUDE.md 项目文档约定，v2 计划生成的文档：

```
docs/
├── overview.md            (本文档；总纲；持续更新)
├── deployment.md          (服务器 / nginx / SSL / Basic Auth；持续更新)
├── specs/                 (v2 子方案设计；按需写)
│   └── (起草中按需添加)
├── plans/                 (v2 里程碑实施计划)
│   └── Plan1-aiic-v2-mvp.md         (待写：16h MVP 实施 plan)
├── progress/              (交付报告)
│   └── Plan1-report.md              (交付后写：实际花了多少时间 / 砍了什么 / 踩了什么坑)
└── archive/v1/            (v1 已冻结；不再修订)
    ├── plans/Plan1-mimo-web-chat.md
    └── specs/2026-05-08-mimo-web-chat-design.md
```

实现阶段（writing-plans skill 接手后）会产生 `plans/Plan1-aiic-v2-mvp.md`，里面会按时间窗 + AgentTeam 任务分发，把这份 overview 拆为可并行实施的 task。

---

## 18. 命名约定

| 名字 | 含义 | 用在哪 |
|---|---|---|
| **ProjectProbe** | 产品名 | UI / Demo 视频 / Memo / README 对外文案 |
| **AIIC-Project** | 仓库名 | GitHub / 工作目录路径 |
| **aiic.fomalhaut647.com** | 域名 | 公网访问 / 主办方验证 URL |
| **aiic-chat.service** | systemd unit | 服务器进程管理（沿用 v1 命名，避免改 nginx 反代和 unit） |

三者**故意不强求统一**：产品对外讲 ProjectProbe，基础设施沿用 AIIC（避免改部署成本）。任何文档 / 代码引用按当下语境用对名字即可。

---

## 19. 评分自检（每个设计决策必答）

> 「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」

每加 / 删一个功能时，回答这道题。无法回答 → 删。

最终产品口号：

> **不是再问你一堆八股题，而是把你的项目追问到讲明白。**
>
> Coach 懂你，Interviewer 不懂你，Report 救你。
