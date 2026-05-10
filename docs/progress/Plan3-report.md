# Plan3 — 多模态输入交付报告

> 起草日期：2026-05-10
> 对应 spec：[../specs/E-multimodal-input.md](../specs/E-multimodal-input.md)
> 对应 plan：[../plans/Plan3-multimodal-input.md](../plans/Plan3-multimodal-input.md)
> 实施模式：subagent-driven-development（worktree 并行 + PR review workflow，本项目首次）
> 部署 commit：`d94556e`（含 Plan3 5 features 全 ship + CLAUDE.md 同步）

---

## 实际交付的 features（与 Spec E §1 对齐）

- [x] **G1 文件上传（onboarding material）**
  - `services/file_parse.py::parse_file(path, file_type) → (text, warnings)` 分发：PyMuPDF (PDF, 图片 warnings 跳 OCR / 加密 raise) + python-docx (DOCX, 表格渲为 plain text rows + table warnings) + md/txt 直读 utf-8
  - PDF 异步 offload via `asyncio.to_thread`（Q2 followup commit `c47d248`，避免阻塞 event loop）
  - 端点 `POST /api/uploads` (multipart) 检：ext 白名单 .pdf/.docx/.md/.txt → 400；空 filename / 空文件 → 400；> 10MB → 413；user 配额 > 50MB → 413；解析失败 (`KeyError + zipfile.BadZipFile + opc.exceptions.PackageNotFoundError` 三类) → raw_path.unlink rollback + 422
  - 持久化 `data/uploads/<user_id>/<file_id>.{ext}` + `<file_id>.json` UploadedFile 元数据
  - 与 Plan2 共享 `_SAFE_ID_RE` regex 但 status 400 (POST body malformed) 不复用 main 的 `_validate_id_or_404` (GET path-arg 404)——spec-correct 不同语义
  - 前端 view-material 加 `📎 上传项目材料` 按钮 → XHR upload progress bar → 解析回填 `#material-input` textarea + `#upload-warnings` 显示

- [x] **G2 STT 语音输入（Chrome 原生）**
  - `class VoiceInput` 封装 `webkitSpeechRecognition`（lang=zh-CN, continuous=true, interimResults=true）
  - onresult: interim partial 实时塞 textarea 末尾，final commit
  - onend auto-restart（continuous=true 静音 30s 浏览器会触发 onend；只要 isRecording=true 就重启）—— Q7 spec re-review 抓回这条
  - onerror 区分 fatal (no-speech / network) → toast + stop()，非 fatal 不打断
  - 实例 swap race fix：`onstop` callback 检查 `VOICE_INPUT === this` 才 null instance（PR #4 round 1 reviewer 抓 score 85 真 bug）
  - 三 textarea (`#material-input` / `#interview-input` / `#resume-iterate-input`) 各加 mic 按钮，`mic-pulse` 红点动画
  - mic toggle off 时 disabled + active 录音 stop()

- [x] **G3 TTS 语音输出（MiMo `mimo-v2.5-tts`）**
  - `services/tts.py::synthesize_speech(text, voice="default") → bytes` (OpenAI 兼容 POST /v1/audio/speech)
  - retry once on `httpx.NetworkError`（4xx/5xx 不 retry → endpoint 503）
  - 缺 `MIMO_API_KEY` fail-fast `KeyError`
  - 端点 `POST /api/tts/synthesize`：empty/blank/>4000 → 422；上游异常 → 503（前端静默降级）；返 audio/mpeg 流
  - 前端 `fetchAndPlayTTS(text)` blob → `URL.createObjectURL` → `Audio.play()`；单实例 `CURRENT_TTS_AUDIO` 追踪（新调用前 `pause()` 老的）
  - speaker toggle on 时 view-interview 渲染 Interviewer 问题自动播；toggle off / 切 view 立即 pause

- [x] **G4 麦克风/扬声器双独立 toggle**
  - nav header 两个 icon button (`#toggle-mic` 🎤 + `#toggle-speaker` 🔈)，aria-pressed 状态
  - localStorage 持久化（`micOn` / `speakerOn`）；中途切换立即生效
  - mic off 时所有 mic-btn 置 disabled + 当前录音 stop；speaker off 时 audio.pause()
  - 默认 off（隐私 friendly + 不会预期外触发麦克风）

- [x] **G5 后端 TTS 封装**
  - 单独模块 `services/tts.py` 隔离 MiMo 调用（与 DeepSeek llm.py 同模式）
  - 接口契约稳定，UI 不暴露 voice 选择（schema 留字段为后续扩展）

---

## 测试覆盖

| 维度 | 数量 | 备注 |
|---|---:|---|
| v2 baseline + Plan2 增量 | 136 | 全部仍 pass，无回归 |
| Q1 schemas | 5 | UploadedFile / UploadResponse / TTSRequest 默认 + 字段验证 |
| Q2 file_parse | 7 | PDF/DOCX/MD/TXT happy + warnings + 加密 + 不支持 ext |
| Q3 tts module | 5 | happy / retry once / persistent fail / 4xx no-retry / missing API key |
| Q4 endpoints uploads | 16 | 4 ext happy + ext blacklist + size 413 + quota 413 + corrupt 422 + path traversal 400 + anonymous fallback + zip-without-content-types 422 |
| Q5 endpoints tts | 6 | happy + voice 透传 + empty/blank/long 422 + upstream 503 |
| Q6 web DOM contract | 5 | toggles + upload + mic-btns + mic-pulse class |
| Q7 web app behavior | 9 | userId / VoiceInput swap / TTS pause / toggle state |
| Q8 integration smoke | 2 | upload→onboard chain + tts endpoint 调用次数 |
| **Plan3 总增量** | **~62** | `pixi run test` 通过 200+ tests |

---

## 砍了 / 改了什么（vs spec / plan）

**Plan 字面 → 实际 implementer 主动修正 3 处**：
- Q4 `DATA_DIR` 改 per-request 而非 module-level（fixture isolation；env 变化时 server fixture 不会 stale）
- Q7 实际 textarea id `#material-input` / `#interview-input` / `#resume-iterate-input`（plan §Q7 step 5 写 `#onboarding-input` 但 Q6 扫描发现 plan2 实际命名）
- Q8 OnboardResult mock shape 调整（plan 里写的字段与 v2 实际 response 略不同）

**Spec → plan 简化**：
- spec E §9.5 per-user TTS 日 quota（默认 200 次）在 plan/code 阶段被 YAGNI 砍，仅做 4000 字 length check + 503 fallback（v3 单用户量小 + MiMo cost 上限不严；如有需要再加 in-memory counter）

**Spec § 13.5 实施前置硬约束被 maintainer 决定 override**：
- 原 spec 写 "Plan3 必须等 Plan2 P0-P16 全部 ship 才起跑"
- 实际走 worktree 并行 + frontend Sync point（`feat/plan3-multimodal-input` 从 `dd57c8e` 分出，与 Plan2 P9-P16 同步推进；Q6 frontend 起手前 rebase main + 解 C1 conflict 后再开工）

---

## 踩了什么坑

### 1. Q4 path traversal 实测 exploit（reviewer 实测发现）

reviewer subagent 实测 `user_id="../../escape"` 写到 `/tmp/escape/`——证明 `data_dir / "uploads" / user_id` pattern 不安全。fix：复用 main 的 `_SAFE_ID_RE` regex，status 保 400。**审 reviewer 实测 > 看 traceback** 第一次体感（已沉淀到用户级 CLAUDE.md）。

### 2. Q7 onend auto-restart + TTS user_id 漏（spec re-review 抓）

implementer 漏 plan §Q7 step 2 的 onend 重启 + step 3 的 TTS user_id 透传。spec reviewer 二审 catch。fix commit `238f54c`。

### 3. .docx 异常族三类（PR #4 三轮逐个发现）

python-docx 解析损坏文件抛三类异常，三轮 review 才完整覆盖：
- Round 1 reviewer 诊断 `BadZipFile`，implementer 实测发现实际是 `PackageNotFoundError` (OpcError 子类)，**方向对名错**——fix `(OpcError, BadZipFile)`
- Round 2 reviewer 实测 `Document(BytesIO(valid-zip-without-[Content_Types].xml))` 抛裸 `KeyError` from `zipfile.ZipFile.getinfo()`——前一轮的 catch tuple 漏 KeyError；fix `(OpcError, BadZipFile, KeyError)`
- Round 3 reviewer 实测验证 + 0 new findings → ✅ APPROVED

教训：narrow except tuple 覆盖第三方库异常族时**必须 empirical** 列举每条故障路径，不能只信 docs / traceback 顶层 raise 行。

### 4. 服务器 deploy 漏 `pixi install`（this session catch）

plan3 teammate 跑 `git pull` 但**没**跑 `pixi install`，systemd 启 uvicorn → `ModuleNotFoundError: No module named 'docx'` → 死循环重启。修复：team-lead ssh + `/home/ubuntu/.pixi/bin/pixi install`（`pixi` 不在 ssh non-interactive PATH 内必须用绝对路径）+ `systemctl restart aiic-chat`。

教训沉淀到项目 CLAUDE.md 部署段：新依赖 deploy 必须含 `pixi install` 步骤；ssh non-interactive PATH 不含 `~/.pixi/bin`。

---

## worktree 并行 + PR review workflow 体感

**worktree 并行**：
- Plan3 实施时 Plan2 同步在 main 推进（P0 到 P16），互不打架
- Sync 1 (Q5 done 后 rebase main) 顺利；只有 1 conflict 在 server/main.py：resume_iterate 缩进——保留 main 的 lock 结构即可
- C1 整合（Plan2 milestone polish 加的 `_SAFE_ID_RE`）= 共享 regex 常量但**不共享 helper function**（status 400 vs 404 各 spec-correct）——这是"defense-in-depth 共享原料 + 上下文差异化适配"的好范例
- Q6/Q7 frontend 实施前等 Plan2 P10-P14 ship 到 main 后再 rebase——保证 view-profile 等已存在视图能被 Plan3 toggle / mic 按钮正确挂钩

**PR review workflow（项目首用）**：
- 3 rounds of review-fix（上面"踩了什么坑" #3）
- reviewer 用 `code-review:code-review` skill 内部派 5 并行 reviewer subagent + Haiku confidence scoring 过滤 < 80
- implementer 用 `superpowers:receiving-code-review` 五步流程评估每条
- maintainer 负责 `gh pr merge` 不让 implementer 自 merge——硬红线
- merge 用 `--rebase` 保留 22 commits + 2 review-fix 工程纪律 trace（CLAUDE.md global "PR 内多 commit 跨域且各自完整时改用 rebase"）
- GitHub 限制 `gh pr review --approve / --request-changes` 不能用在自己 PR 上；reviewer workaround `gh pr comment` 带 explicit header

体感：比 v2/Plan2 直接 main 节奏多了 review iteration overhead（约 3 轮 × 10min）但抓出 3 个真 bug + 留下完整 PR trace 给评委 / 答辩用，**值**。

---

## 下一步候选（指 docs/plan4-brainstorm.md 已分级）

**Plan4 P0 七条**（建议 4 周内做）：
1. **H1 用户访谈**——题面明示 + 评分维度 1+5 直接得分
2. **F3 弱点演化趋势图**——dashboard 视觉升级（Plan2 砍掉的）
3. **G7 我的资料库 UI**——回访已上传文件（Plan3 砍掉的）
4. **G14 F4 上传简历 PDF**——Plan2 简历多轮支持上传，复用 Plan3 G1
5. **I3 简历评分量化**——0-100 分进度条「原 60 → Coach 78 → 用户改后 85」
6. **I5 STAR/CAR 答题模板**——Coach 提示重组建议
7. **I9 to-do 化训练计划**——next_training_plan 拆 [{description, slot, status}] 可勾选

**Plan3.5 polish pass**（demo 视频前必做）：派 fresh teammate 激活 `frontend-design:frontend-design` 跑全 UI surface 视觉一致性（home / onboarding / material / interview / report / profile + Plan3 新 toggle / mic / upload / modal）。Plan2 P10-P14 是 controller-direct 实施，没起 frontend-design skill；Plan3 Q6/Q7 起了但仅服务新组件。统一 polish pass 把整体提到 demo-video 级别。

详见 [`docs/plan4-brainstorm.md`](../plan4-brainstorm.md)。
