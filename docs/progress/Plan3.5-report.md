# Plan3.5 — polish pass 交付报告

> 起草日期：2026-05-10
> 实施模式：teammate 协作 + 双 reviewer subagent per task + PR review workflow
> 对应 brief：team-lead spawn `impl-controller-plan3-5` (frontend) + `impl-controller-plan3-5-stt` (backend STT) 拆 Bug 3 并行
> PR 拆分：**frontend PR `#6`** + backend PR `#5`（独立 review，maintainer 按 backend → frontend 顺序 merge）
> 部署 commit：`<TBD merge 后填>`

---

## 实际交付的 fixes & improvements（与 brief 11 项对齐）

### 5 Bugs

- [x] **Bug 1 — mic 按钮被压扁成椭圆 + 挡住 Cmd+Enter 提示**
  - Root cause: `.composer button` 通配 cascade `min-width: 120px` 喂进 nested `.textarea-with-mic > .mic-btn`，把 36×36 圆撑成 120+×36 椭圆
  - Fix: `.composer button` → `.composer > button`（直接子选择器收窄）+ `.mic-btn` 加 `min-width: 0` + `flex: 0 0 36px` + `box-sizing: border-box` 防御性钉死正方形
  - Commit: `dd2c960`

- [x] **Bug 2 — 用户气泡贴右但内文也右对齐 + 单行也吃满 88%**
  - Root cause: `.chat .msg.user { text-align: right }` + `.chat .msg { max-width: 88% }` 但没 `width: fit-content`
  - Fix: `.chat .msg` 加 `width: fit-content` 让单行短气泡按文字宽度收紧 + `text-align: left` 统一所有气泡内文左对齐；`.chat .msg.user` 删 `text-align: right`（margin-left:auto 已贴右）
  - Commit: `dd2c960`

- [x] **Bug 4 — 听不到 TTS 朗读**
  - 三层叠加 root cause（systematic-debugging Phase 1 诊断）：
    - **A (UX 主因)**: toggle-speaker click handler 只翻 state，不立即朗读。用户翻 ON 时如果当前已显示问题，要等下一轮 renderInterviewView 才会触发 `_maybeSpeakCurrentQuestion`
    - **B (页面加载场景)**: localStorage `speakerOn=true` 持久化，重开页面首次 auto-speak 在 user gesture activation 之前触发 → `audio.play()` reject → 原代码静默吞掉
    - **C (visual 反馈缺失)**: 即便 play() 成功也没视觉确认 TTS 真在播
  - Fix: toggle ON 立即 fetchAndPlayTTS（click 本身是 user gesture）+ catch 调 `_plan3Toast` 给明确出路 + `#toggle-speaker.tts-playing` CSS 脉冲（play()/ended/error/pause 四处管理 class）
  - Commit: `3a216d4`

- [x] **Bug 5 — 面试官内心 OS 错配 (perception)**
  - systematic-debugging 结论：**数据流正确**，OS 由 LLM 在评估「刚答的 A_n」+ 推荐「下一问 Q_{n+1}」时一并生成，绑定在 new_turn 上。前端 `state.current_os = result.turn.interviewer_os` 与 `state.current_question = result.turn.next_question` 索引对齐
  - **但**：`interviewer_os` 是混合时间戳对象（`missing_slots` retrospective 同步 eval missing；`why_this_question` / `what_i_want_to_hear` prospective 关于下一问）。LLM 实测有 retrospective bias，用户看到「OS 在 Q_{n+1} 旁但内容像 Q_n 反思」就误判错位
  - Fix: 跟 Imp 4 联动——OS 改右侧推拉抽屉默认 collapsed，物理隔开 OS 与 next question card，错位感消失
  - Commit: `f1c951d`（layout 重构含此修法）

- [x] **Bug 3 — STT 识别错误率太高 → 改 server-side API** (frontend 侧, backend 由 PR #5 ship)
  - **Provider 选型故事**: frontend teammate 最初 PoC 用 silent.wav 试 mimo-v2-omni `chat/completions + input_audio` → 模型回答「无法处理音频」误判 MiMo 完全无 ASR 能力 → escalation 给 maintainer。team-lead 单方决定走 B 变种 faster-whisper 自部署。**backend teammate 二轮 PoC 翻盘**: 用真实音频测 `mimo-v2-omni` 真支持中文转录，前 PoC 是用例错（model 看到无声 audio 给的语义回复）而非能力错。最终省 faster-whisper 470MB 模型 + CPU 峰值 + 冷启 30s
  - **Backend 由 PR #5 独立 ship**: `services/stt.py` + `POST /api/stt/transcribe` (mimo-v2-omni + ffmpeg 转码 webm/opus → wav + 5MB cap + 错误分流 400/413/422/503)。详见 PR #5 + `impl-controller-plan3-5-stt` commit
  - **本 PR (frontend)**: VoiceInput 内核重写（preserve external API surface）。getUserMedia + MediaRecorder + MIME_PRIORITY 探链 (webm/opus 首选) + multipart fetch + AbortController **70s timeout** + **60s 客户端 auto-stop** (memory safety) + 5MB pre-check + 错误状态码 → toast 分流 (NotAllowedError 给特定提示 + 503 fallback「请改键盘输入」+ 422「音频解码失败」+ 空 transcript「没听清」)
  - **测试 mock 化**: frontend 测试用 string-presence contract 而非 fetch mock，独立于 backend 真实现。本 PR 测试 GREEN 不依赖 backend ship
  - Commits: `33bfa4e` (frontend rewrite) + `21c49a0` (review round 1: race + timeout + cap)

### 5 Improvements

- [x] **Imp 1 — 阶段标识左侧 outline + 当前进度高亮**
  - HTML 加 `<ol id="interview-stage-outline" class="stage-outline">` 在 `.interview-sidebar`
  - JS 加 `STAGES` 数组（对齐 `services/interviewer.py:_STAGE_ORDER`）+ `renderStageOutline()`，三处 callsite 调用
  - 三态: `done` (全 ✓) / 已知 enum / null 或未知 (全 pending 占位 ·)。round 1 review 抓出 null 时误算 allDone 的真 bug，已 fix
  - Commit: `f1c951d` + `652e2ef`

- [x] **Imp 2 — textarea 加高**
  - `#interview-input min-height: 140px`，`#onboarding-input min-height: 96px`，`#resume-iterate-input min-height: 110px`，max-height: 60vh 防吃满屏。`resize: vertical` 由全局 textarea rule (line ~259) inherit
  - Commit: `f1c951d`

- [x] **Imp 3 — 反馈 + 缺失/已覆盖槽位 + 上轮分数 → 左 sidebar**
  - `showFeedback()` 渲染目标改 sidebar `.sidebar-feedback`（id 不变 `#interview-feedback`，class 改）
  - 缺失槽位橙色 chip / 已覆盖绿色 chip
  - 删 `scrollIntoView`——sidebar `position: sticky` 已让反馈始终可见
  - empty-hint「回答后会显示评分 / 槽位 / 反馈」CSS 同级选择器 auto-hide
  - Commit: `f1c951d`

- [x] **Imp 4 — 内心 OS 改右侧推拉抽屉**
  - `#cheat-panel` `position: fixed` 右侧抽屉（380px / 100vw mobile），从 `translateX(100%)` 滑入；240ms cubic-bezier transition
  - `#btn-cheat-toggle` 复用既有 id，class 加 `.cheat-drawer-tab` 切换为 fixed 右缘竖排 tab（`writing-mode: vertical-rl`）
  - 抽屉默认 collapsed（renderInterviewView / submitAnswer 不再 auto-open）
  - 关闭方式：再点 tab / drawer 内 X / Esc 三选一；focus 归还 tab 按钮（a11y）
  - `.hidden` 全局 `display:none !important` 对 cheat-panel override 成 `display:block !important` 让 transform 动画播完
  - a11y: `role="dialog"` + `aria-modal="true"` + `aria-hidden` 同步 toggle + `aria-pressed` on tab
  - Commit: `f1c951d` + `652e2ef`

- [x] **Imp 5 — 幽默卡片改用固定模板**
  - `services/coach.py` 加 `_HUMOR_CARD_CONSTANT` 模块常量（"高价值 bug：薄弱项是真痛点"+ 1.01^30 / 1.2^2 数学梗）
  - `services/prompts.py` 删 `humor_card 强约束 #6 + #7`，改成「humor_card 字段如存在，由后端注入固定文案——LLM 无需关心」
  - `services/schemas.py` `EvaluationReport.humor_card: HumorCard` → `HumorCard | None = None`
  - `coach.review()` 末尾 unconditional override + fallback humor_card 同步换成常量
  - 节省 LLM token 抖动 + 保 demo 一致性
  - Commit: `103f99a`

---

## 测试覆盖（本 PR frontend-only 范围）

| 维度 | 数量 | 备注 |
|---|---:|---|
| baseline (Plan3 ship 后) | 198 | 全部仍 pass，无回归 |
| Imp 5 (humor_card 常量) | 3 | LLM garbage 被覆盖 / fallback 路径 / Optional schema 默认 None |
| Bug 4 (TTS 听不到) | 4 | toggle inline call / catch toast / playing class / CSS keyframe |
| Bug 3 frontend (MediaRecorder contract) | 7 | uses_media_recorder / get_user_media / posts_to_endpoint / prefers_webm_opus / no_more_webkit / permission_denied / 503 |
| Bug 3 review round 1 (race/timeout/cap) | 3 | _starting flag race fix / fetch AbortController / MAX_RECORD_MS auto-stop |
| **本 PR 总增量** | **17** | `pixi run test` **213 全 pass** (198 baseline + 17 增量) |

> Backend STT 38 测试 (services/stt.py 23 + endpoint 15) 在 PR #5 内独立 review。

---

## 砍了 / 改了什么（vs brief）

**Bug 5 改 fix 方向**：brief 假设可能是 schema 字段绑定错或前端 index 错；systematic-debugging 实测确认是混合时间戳的 perception 问题，最小代码改动。fix 通过 Imp 4 OS 改抽屉物理隔开，**不需要单独 commit**（合进 layout 重构）

**Bug 3 PR 拆分**：原 brief 让 frontend teammate 独包 backend + frontend；team-lead 中途改决策拆 backend 给新 teammate 并行 + frontend 这边 mock 化测试 + 各自独立 PR。本 PR scope 因此变窄到 frontend MediaRecorder 重写 + contract test，backend 由 PR #5 独立 review。**集成 e2e 验证留给 maintainer 部署后跑**。

**Bug 3 provider 调整**：frontend teammate 最初 PoC 误判 mimo-v2-omni 不支持音频 → escalation。team-lead 决定走 faster-whisper 自部署。**backend teammate 二轮 PoC 翻盘**: mimo-v2-omni 实际支持音频, 前 PoC 是用例错。最终用 mimo-v2-omni + ffmpeg 转码省了 faster-whisper 部署风险。教训: **PoC 一次失败 ≠ 能力不存在；reviewer 实测 > 静态分析** 体感再加深一层（已沉淀到用户级 CLAUDE.md "reviewer 实测 > traceback 表面" 段）

**Imp 5 schema 改优化**：brief 写「直接塞这个常量字符串」；实施时把 `humor_card: HumorCard` 改 `HumorCard | None = None` 让 LLM 不必生成（节省 prompt + JSON 字段），但保留 schema 兼容（fallback 仍 set 常量）

---

## 双 reviewer subagent 体感（per-task 同 message 多 Agent 并行）

按 brief 硬约束：每个 task ship 后派 spec-compliance + code-quality 双 reviewer 并行。

**Phase 3 (Imp 1-4 layout 重构) 体感**：
- spec-compliance reviewer: APPROVED + 5 硬约束齐 + FYI dead code
- code-quality reviewer: NEEDS_FIX → 1 MED real bug (`renderStageOutline` null 误算) + 2 LOW dead code + a11y gaps
- round 1 fix commit `652e2ef`：null-state 三态 + aria-current/role=dialog/focus-return + 删 .feedback / .interview-banner 死代码

**Phase 5 (Bug 3 frontend) 体感**：
- spec-compliance reviewer: APPROVED + 5 硬约束齐 + USER_ID guard 验证 OK
- code-quality reviewer: NEEDS_FIX → 1 HIGH async start() race (用户在 await getUserMedia 期间双击 mic-btn 双开 MediaRecorder + 双 stream 资源泄漏) + 1 MED 缺 fetch timeout (brief 明示 70s) + 1 LOW MediaRecorder 长录无 cap 风险 (用户 30 分钟录音 200MB+ 浏览器 RAM)
- round 1 fix commit `21c49a0`：`_starting` flag + `_cancelled` 取消机制 + AbortController 70s + MAX_RECORD_MS 60_000 auto-stop

**push back（FYI / non-actionable）**：
- sibling-selector brittleness: 当前 DOM order 正确，FYI not defect
- `.cheat-panel.hidden` scope-leak: 已 inline 注释，single-instance，fine
- hardcoded accent rgba: 与 line 349/362 既有 pattern 一致，改 var() 反破坏一致性
- _plan3Toast typeof guard: 与 Bug 4 既有 pattern (commit 3a216d4) 一致, 保留
- string-presence test 限制: harness 限制 (无 JSDOM); 已 contract test 锁 arch decision

教训：双 reviewer 抓出 2 真 MED+ bug + 多条 a11y improvements，对单一 reviewer 是有 net positive；overhead 约 5 分钟 × 2 但抓 bug 价值 > overhead。

---

## 踩了什么坑

### 1. MiMo Omni audio block PoC 误判（Bug 3 BLOCKER 翻盘）

frontend teammate PoC 用 silent.wav 试 `mimo-v2-omni` `chat/completions + input_audio` → 模型语义回复「无法处理音频文件」→ 误判 MiMo 完全无 ASR 能力 → escalation。backend teammate 二轮 PoC 用真实音频测试，发现 mimo-v2-omni 真支持中文转录。**用例错而非能力错**。

教训：**PoC 一次失败 ≠ 能力不存在**；模型对 silent / corrupt 输入的语义回复可能误导你「这条路不通」。empirical PoC 必须用真实代表性输入。这条 + 「reviewer 实测 > traceback 表面」加固沉淀。

### 2. `.composer button` 通配 cascade 喂 `min-width: 120px` 进 .mic-btn (Bug 1)

CSS 通配选择器是 silent killer——`.composer button` 不直接 child 修饰会 match 任意嵌套。fix `.composer > button`。

教训：嵌套场景下默认用 child combinator (`>`) 比通配安全，尤其当外层规则本就是给 primary button 量身定制时。

### 3. `state.current_state == null` 时 `findIndex(...) === -1` 误算 allDone (Imp 1 round 1)

renderStageOutline 第一版把 curIdx === -1 当成 "stage advanced past 6" → allDone。实际 null 时应该全 pending。reviewer 抓出真 MED bug。fix 三态判定。

教训：JS findIndex 返 -1 在不同语义下意思不同——「未到」vs「未知」vs「错位 enum」。defensive coding 显式 null check 比依赖 -1 magic number 更稳。

### 4. `.hidden` 全局 `display:none !important` 与 transform 动画冲突 (Imp 4)

drawer slide-out 需要 transform 在 element 仍 display:block 时 animate；全局 .hidden 强制 display:none 让动画一帧不播。fix: `.cheat-panel.hidden { display: block !important }` override 全局 .hidden + visibility:hidden + transition delay。

教训：global `.hidden` 是 styled-components / Tailwind 之前的常用 pattern，但与 transform 动画对抗。需要场景化 override 时记得用 visibility/pointer-events 兜底而非纯 display 切换。

### 5. Async start() race 在 await getUserMedia 期间双击 (Bug 3 frontend round 1)

reviewer 抓真 HIGH bug：`start()` 是 async 但 `isRecording=true` 在 `recorder.onstart` event 才置（getUserMedia await + recorder 构造之后）。中间窗口 click handler 只检 `isRecording` 通行无阻，创建第 2 个 newVI → 双 MediaRecorder + 双 stream 资源泄漏。

教训：async fn 入口必须**同步**置 pending 标记 (我加 `_starting` flag)，否则 race window 内 caller 可双开。这条沉淀到 frontend async/await pattern 的体感库。

### 6. workflow 中途变更（最后阶段 git history 重写）

frontend teammate 已按 team-lead 早先指令把 backend branch merge 进自己 branch（commit `f27a14a`），开 PR #6 含合并 backend 代码。team-lead 后改决策拆独立 PR → frontend `git reset --hard` 退回 merge 之前 + cherry-pick 自己后续 commit + force-push。

教训：teammate 间 workflow 共享指令应早期定锁；中途变更代价是 history rewrite + force-push。新 commit hash 要同步更新 docs / PR description。

---

## 下一步候选

Plan3.5 frontend polish pass 已 ship（待 reviewer + maintainer merge）。剩余 follow-up 工作：

1. **a11y 完善**: drawer tab-trap / focus 锁 / aria-live for stage advance announcements
2. **demo 视频前再过一遍 UI**: 用真实数据走 demo path 检查 visual cohesion
3. **集成 e2e**: 部署 + backend PR #5 merge 后真录音 → 真转录链路 hands-on 验证

详见 `docs/plan4-brainstorm.md` 已分级清单。
