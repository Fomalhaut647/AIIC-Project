# Plan2 — 长期训练闭环交付报告

> 起草日期：2026-05-10
> 对应 spec：[../specs/D-plan2-long-term-training.md](../specs/D-plan2-long-term-training.md)
> 对应 plan：[../plans/Plan2-long-term-training.md](../plans/Plan2-long-term-training.md)
> 实施模式：subagent-driven-development（每 task: implementer → spec reviewer + code quality reviewer 并行 → controller polish）

---

## 实际交付的 features（与 Spec D §1 对齐）

- [x] **F1 Session 持久化 + anonymous user_id**
  - 前端 `localStorage.userId` 启动生成 (crypto.randomUUID, private-mode 兜底 anon-{ts}-{rand})
  - 后端 6 个 v2 POST endpoint 加可选 `user_id: str = "anonymous"`
  - SessionStore 三方法: `load_user_profile / update_user_profile (atomic .tmp+rename, per-user asyncio.Lock) / list_user_sessions`
  - 持久化路径: `data/users/<user_id>.json` (双索引 + sessions/ 旁; .gitignore 屏蔽内容保留 .gitkeep)

- [x] **F2 一键重练薄弱项 + ReplayMiniReport**
  - `build_replay_packet` model_copy parent + 加 replay_mode/replay_focus_slots/parent_session_id (空 focus 早 fail ValueError → 400)
  - `should_advance_state` permission gate + `should_continue_replay` (covered ⊇ focus 或 ≥8 turn 硬截断)
  - INTERVIEWER_REPLAY_PROMPT_INJECT 注入 system prompt (start + next_turn 两处)
  - `compute_replay_coverage` 闭式 set 运算 + `_canon_slot` lowercase+strip canonicalization
  - `summarize_replay` LLM 调一次出 sample_good_answer + next_step (失败 fallback 带具体文案)
  - 端点 POST `/api/interviewer/replay` + POST `/api/interviewer/replay/finish` (404/400/200 全分支)
  - 前端 dashboard 时间线「重练 X」按钮 → interview 视图 banner → mini-report modal (Esc 关 / focus 移到 close / 自动跳回 dashboard refresh)

- [x] **F4 简历多轮迭代 + revision_history**
  - `iterate_resume(original, prior_missing, user_revised, iteration_index) → ResumeRevision`
  - 防 LLM 幻觉: 过滤 still_missing 仅保留 prior_missing 中的项; LLM 漏报项默认进 still_missing (`is_good_enough` 不会假阳性)
  - 退化保护: prior_missing 非空但 LLM 全空 → 走 fallback 文案 + still=prior_missing
  - 端点 POST `/api/coach/resume_iterate` (404/409/200) + per-session asyncio.Lock 防并发 RMW lost update
  - 前端报告页 textarea + 「让 Coach 看看」按钮 + 反馈卡片 (good 绿 / pending 橙) + 历次迭代折叠

- [x] **F5 报告导出 Markdown 8 段**
  - `services/export.py::render_markdown(session_dict)` 8 段固定模板
  - Evidence dict 友好渲染 (quote/problem/suggestion → 引用块 + 问题/建议 sub-bullets, 不暴露 Python repr)
  - TrainingPlan dict 渲染为可读 markdown (推荐下一步 / 原因 / 步骤列表), 不再是 `{'recommended_next_step': ...}` 字面量
  - 用户内容 brace-escape `{}` 防 KeyError 静默 fallback
  - `</details>` / `</summary>` literal 转义 zero-width-space 防 markdown injection
  - 端点 GET `/api/sessions/{session_id}/export.md` 200 + `Content-Type: text/markdown; charset=utf-8` + `Content-Disposition: attachment; filename="projectprobe-{prefix8}-{date}-score{N}.md"`
  - 前端报告页 + dashboard 时间线两处「下载 .md」按钮 (fetch+blob+createObjectURL, 409/404 alert)

- [x] **F7 个人主页 dashboard**
  - 第 6 视图 view-profile (HTML scaffold + 全局 floating 「我的训练」 nav button + 红点提示 total_sessions>0)
  - 4 个 sections: hero stats (总 session / 平均分 Math.round / 训练天数 distinct date count) / 弱点 top 5 横向柱状图 (纯 CSS, 无 Chart.js) / 时间线 (倒序前 20, replay-row 缩进) / 项目库 (去重 + N 次 + 再来一次)
  - XSS 防御: 全局 click 委托 (data-action) 替代 inline onclick; 所有 user-supplied 字符串走 escapeHtml
  - 端点 GET `/api/users/{user_id}/profile` (missing user 200 + empty default, NOT 404)

---

## 测试覆盖

| 维度 | 数量 | 备注 |
|---|---:|---|
| v2 baseline 测试 | 59 | 全部仍 pass (无回归) |
| Plan2 新增 unit 测试 | 8 (P1) + 6 (P2) + 10 (P3) + 7 (P4) + 8 (P5) + 8 (P6) | 总 47 |
| Plan2 新增 endpoint 测试 | 7 (P7) + 8 (P8) + 12 (P9) | 总 27 |
| Plan2 集成 smoke (P15) | 3 | full-loop + anonymous fallback + healthz baseline |
| **总计** | **136** | `pixi run test` GREEN |

---

## 砍了 / 改了什么（vs spec D / plan 字面）

### 必要的偏离（plan 字面与 v2 实际接口不一致）

- **`call_deepseek` API**: plan snippet 用 `response_schema={dict}` 但 v2 实际只接 Pydantic class. 改成所有 LLM 路径用 `_ReplaySummaryLLM` / `_IterateResumeLLM` 等 internal Pydantic 类. (P3 / P4)
- **`InterviewPacket` schema**: plan 假设 `intensity: int / constraints: dict / question_policy: dict` 但 v2 实际是 `RiskLevel / list[str] / str (with default)`. 测试 fixture 改为只传必填字段, 让默认值生效. (P1 / P5 / P9)
- **`InterviewTurn.score` + `source` enum**: plan fixture 缺 `score` 必填字段且用 `source="llm"` 不在 QuestionSource enum 内. 改为 `score=0 / source="project"`. (P3 / P5 / P9)
- **`SessionStore` API**: plan 用 `store.save(sid, dict) / store.load(sid) → dict` 都不存在 v2 actual. 真实接口是 `create(packet, user_model) / get(sid) → InterviewSession / append_turn / persist (P8 加的 public alias for _dump) / load_session_dict (P8 加, 给 export 用)`. 测试 fixture 全部用真 API. (P7 / P8 / P9)
- **`InterviewSession.evaluation_report`**: spec D §9.1 implicit 「reviewed」 status 假设 session JSON 含 evaluation_report, 但 v2 schema 没这字段. 在 P8 加 optional `evaluation_report: EvaluationReport | None = None` (向后兼容; 老 session JSON 缺字段 Pydantic 自动填 None).
- **server/main.py 没共享 header**: plan 假设有 nav 共享 header. v2 每 view 自带 .topbar. P10 改用全局 floating button (照 theme-toggle 模式).
- **CSS 变量名**: plan snippet 用 `--bg / --fg / --surface / --muted` 都不存在 v2. P10 全部映射到真实 v2 变量 `--bg-0/1/2 / --text-0/1/2 / --border / --accent / --bad / --shadow`.
- **请求模型命名**: v2 用 leading underscore `_OnboardReq / _ParseReq / ...` (plan 字面用 `OnboardRequest`). P7 直接用 v2 命名.
- **coach 函数 patch target**: plan 测试 `patch("server.main.coach_onboard", ...)` 默认 server.main 暴露 `coach_onboard / coach_plan / coach_review / iterate_resume / summarize_replay / compute_replay_coverage / interviewer_start / build_replay_packet` 别名. P7/P9 加这些 re-import.

### 主动加强（reviewer 反馈促成的 polish）

- **P3 / P4**: brace-escape 用户内容防 KeyError 静默 fallback; partition validation + 退化保护防 LLM 幻觉; empty-focus ValueError 防 0-turn replay
- **P5**: 8-turn 边界测试 (7/8/9) 防 cap 抬高一轮无 catch
- **P6**: markdown injection guard (`</details>` / `</summary>` 转义); helper rename `_format_evidence_item → _format_bullet_item` (它实际处理所有 list); `_format_training_plan` 渲染 dict 为可读 markdown; empty_revision_history_omits_section 测试用 strict `not in` 不是 OR 永真
- **P7**: review hook silent except 加 stderr log (生产 debug); profile_parse 测试 mock 严格匹配 _ParseResp shape
- **P8**: `SessionStore.persist(session)` public 别名替代跨模块 `_dump` 调用; filename pattern + UTF-8 charset 测试 pin
- **P9**: `register_session(session)` 把 disk-loaded session 写回 in-memory 防重复 parse; per-session asyncio.Lock 防并发 resume_iterate 丢条目; replay/finish parent missing 显式 404 (避免 silent coverage_before=0 假装全提升)
- **P11/P12**: postJson 自动注入 user_id 单点改 (10+ 现有调用一次性受益); click 委托 data-action 替代 inline onclick (XSS); _escHtml 转义 5 字符
- **P13**: finishReplay returns boolean, 失败时 submit 不 re-enable + question 改成「请回首页/重试」防 stuck-state 用户向已结束 session 提交; modal a11y (focus → close, Esc 关闭)
- **P14**: export-md-btn 下载期间 disabled + 「下载中...」防连点; dashboard timeline 下载也走 downloadMarkdown 让 409/404 surface

---

## 踩了什么坑

1. **plan 字面 vs v2 实际接口大量不一致** — 列表见上节. 这次 SDD controller 在每个 implementer prompt 里显式列出所有「critical adaptations」让 implementer 不被 plan 的 stale snippet 误导. 教训: writing-plans 阶段如果实际接口已变 (v2 演进过), spec 字面 snippet 必须先 grep 实际再写, 否则 implementation 阶段会反复跳出 schema 不匹配的 PR review.

2. **WIP 文件管理** — 4 个 in-progress modified files 贯穿整个实施 (services/coach.py 1-line timeout, services/llm.py default model bump, web/app.js + web/index.html UI polish). 处理模式:
   - coach.py 1-line WIP: 每次 P3/P4 implementer 先 revert WIP 行, commit P3/P4, 再 re-apply WIP. 5 次循环 0 出错.
   - web/app.js + web/index.html WIP: P10 之前先 commit 为「polish(web): interview exit + report regen + cheat panel auto-show」单独故事 (不与 view-profile scaffold 混合). 之后 P11-P14 直接编辑.
   - llm.py: 没动到, 保留 unstaged.

3. **Pydantic forward-ref**: P1 实施时 `ResumeRewrite.revision_history: list[ResumeRevision]` 在 ResumeRevision 之前定义, 需要 `model_rebuild()`. Code quality reviewer 提出 reorder 更稳健 (避免未来重构误删 model_rebuild). polish 后清理。

4. **TestClient + lifespan**: CLAUDE.md 已记的 v1 教训仍适用于 v2. 所有 endpoint 测试都用 `with TestClient(app) as c: yield c` pattern + monkeypatch DATA_DIR 让 lifespan 重新读 env 拿到 tmp_path.

5. **跨模块私有访问**: P8 实施时 server/main.py 直接调 `app.state.store._dump(session)`. Code quality reviewer 提示 "consenting adults" 仅限同一文件; 跨文件应用 public API. polish 加 `SessionStore.persist(session)` 别名后切换。

6. **markdown injection / `.format()` brace 注入**: 用户回答含 literal `{x}` 或 `</details>` 都会破坏渲染. P3/P4 用 `_escape_braces`, P6 用 `_neutralize_details_close` 防御. 都靠 reviewer 提出后加, 没在 spec 里预见.

7. **5-reviewer 模式不是这里用的**: 本任务全程用 SDD 默认两阶段 (spec compliance + code quality), 没用 plan/spec 的 5-reviewer + Haiku confidence scoring. 但 receiving-code-review 五步流程在每次 review feedback 上都走过 — controller 不凭直觉 push back 也不盲目 apply, 都先 read → understand → verify → evaluate → respond.

---

## 下一步候选（Plan3 之外的 future）

- F3 跨 session 弱点演化趋势图 (timeline + 弱点占比折线)
- F6 PDF / Word / 图片项目材料解析 (Plan3 已在 worktree 并行实施)
- F8 多项目主推对比模式
- 跨设备 user_id 导出 / 导入 (二维码 / 短链)
- 完整登录系统 (现在是 anonymous-only, 故意 YAGNI)
- 真实创建时间字段 thread 进 SessionStore.create() (现在 SessionMeta.created_at 用 datetime.now() 近似为 review 时间, 不是 session 真实开始时间)
- web/app.js 拆 (~1100 行, 逼近单文件阈值; 拆 profile.js / replay.js / iterate.js)
- 重复 escape helper 整合 (`_escHtml` from P12 + `escapeHtml` from v2 line 392 同体, 维护陷阱)

---

## 评分自检 (Spec D §15 / 主办方核心评分句)

> 「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」

| feature | ChatGPT 做不到 | ProjectProbe 实现 |
|---|---|---|
| F1 持久化 | 跨 session 不记得你 | localStorage user_id + UserProfile 聚合 + dashboard 一眼看见历史 |
| F2 重练 | 弱点暴露后无下一轮 | 时间线点「重练 X」立刻 fork 新 session, prompt 注入只追问该 slot, 结束给 coverage 提升量化 |
| F4 简历多轮 | 改完不验证 | iterate_resume 评估 missing_evidence 是否被覆盖, 不限轮次自然收敛 |
| F5 Markdown 导出 | 输出无结构 | 8 段固定模板含面试官 OS (差异化证据), 用户拿走离线对照 |
| F7 个人主页 | 无 dashboard | hero stats + 弱点柱状图 + 时间线 + 项目库; 看见「我在哪里弱」+ 弱点演化 |

每条都过关; 答辩材料可逐 feature 点击演示。
