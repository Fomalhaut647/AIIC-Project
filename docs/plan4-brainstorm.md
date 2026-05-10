# Plan4 Brainstorm Draft

> 起草日期：2026-05-10
> 状态：**草稿**——给 Memo §下一步设计 + 答辩"再给一周怎么做"准备素材；不是正式 spec
> 上游：v2/Plan2/Plan3 已落地基础上的下一波扩展候选
> 编写时机：Plan2 已 ship + Plan3 实施进行中 (Q3)；用 maintainer 视角盘点未来一周值得做什么

---

## 0. 这份文档是什么 / 不是什么

**是**：
- Plan4 候选 feature 的 inventory + maintainer 取舍依据
- 答辩 "再给一周怎么做" 的可信回答素材
- Memo §下一步设计 段的填空原稿

**不是**：
- 正式 spec（决定实施时再 split 成 `docs/specs/G-xxx.md` / `H-xxx.md`）
- 实施 plan
- commit-to-deliver 承诺

---

## 1. 候选总览

按"来源"分四类：(a) Plan2 显式砍掉、(b) Plan3 显式砍掉、(c) 题面建议未做、(d) 新构思。每个候选下文有判定卡。

### 1.1 来源 a — Plan2 砍掉的

| 编号 | 名字 | spec D §1.2 砍掉理由 |
|---|---|---|
| **F3** | 跨 session 弱点演化趋势图 | "粗略 hero stats 已够" |
| **F6** | PDF/Word 项目材料解析 | "与长期训练主题不直接相关"——但 Plan3 G1 已实现 |
| **F8** | 多项目主推对比模式 | "需 vector search / RAG 等额外工程，过度" |
| **F7-stretch** | 训练计划时间线可视化（dashboard 之上） | "粗略 hero stats 已够" |

### 1.2 来源 b — Plan3 砍掉的

| 编号 | 名字 | spec E §1.2 砍掉理由 |
|---|---|---|
| **G6** | 跨浏览器 STT (Safari/Firefox) | "Chrome only" 第一步约束 |
| **G7** | 我的资料库 UI（曾上传文件回访） | YAGNI |
| **G8** | OCR 图片简历 / 手写笔记 | 加 OCR 大依赖 |
| **G9** | 视频项目介绍上传 | 视频处理工程量过大 |
| **G10** | TTS voice 多选 / 男女声 / 情感语调 | 默认 voice 一种就够 |
| **G11** | 实时打断面试官（用户开口 TTS 自动暂停） | turn-taking 工程门槛高 |
| **G12** | STT 多语言混合 explicit 切换 | 中文为主，混入英文自然识别 |
| **G13** | 上传文件版本管理 / 历史回看 | YAGNI |
| **G14** | F4 简历多轮迭代支持上传 PDF | "Plan2 维持 textarea 粘贴" |

### 1.3 来源 c — 题面建议未做

| 编号 | 名字 | 题面引用 |
|---|---|---|
| **H1** | 真实用户访谈（3-5 人，30min/人） | 题面 §主办方建议「找几个真实用户聊一聊」 |
| **H2** | 在 Memo / 答辩中沉淀访谈结论 | 评分维度 1「是否真正理解目标用户」直接证据 |

### 1.4 来源 d — 新构思（不在已有 spec/题面）

| 编号 | 名字 | 一句话 |
|---|---|---|
| **I1** | 多面试官 panel 模式 | 同一项目召集 Researcher / Engineer / 老板 三视角循环追问 |
| **I2** | 面试录像 + 回放 | 把整轮面试（含 TTS 朗读 + 用户语音 + 文字 + 作弊模式）打包成可重播文件 |
| **I3** | 简历自动评分 + 改写质量评估 | 让 Coach 给 resume_rewrite 打分 + 量化改进幅度 |
| **I4** | Coach 风格定制（严厉/温和/苏格拉底） | 用户进 onboarding 选 Coach 性格，影响后续 prompt |
| **I5** | 答题模板提示（按 STAR / CAR） | 用户讲完一段，Coach 给"按 STAR 格式重组"建议 |
| **I6** | 项目-faculty 匹配（保研场景） | 输入目标导师/课题组，Coach 拉对方近期论文+方法论，引导用户对齐 |
| **I7** | 群组对练（多用户对同一项目互问） | 跨用户协作；社区 / 评分 / 留言 |
| **I8** | 答辩 PPT 自动生成 | 基于面试 transcript + 弱点报告生成"我应该如何讲这个项目"PPT 大纲 |
| **I9** | 教练建议执行追踪（结构化 to-do） | next_training_plan 拆成可勾选 todo，下次回来勾完成度 |
| **I10** | 英文面试模式 | 同一面试逻辑切英文 prompt + TTS / STT 切英文 |
| **I11** | 数据持久化升级（SQLite） | v2 §10 「不上 SQLite」边界放开，支持复杂查询（如 "我历史上 baseline 弱点的覆盖率演化"） |
| **I12** | 公网账号系统 | 走 OAuth 或 magic link；从 anonymous user_id 升级为可跨设备 |
| **I13** | 统计与运营 dashboard（maintainer 视角） | DAU / MAU / 平均 session 长度 / token cost / 弱点分布 |
| **I14** | 公开榜（社区评测真实学生用例） | 谁的项目最难讲明白 / 谁刷得最深 |

---

## 2. 每条候选的判定卡

格式：**编号** ｜ 一句话 ｜ 评分价值（哪个维度）｜ 工程量 ｜ 取舍

### F3 跨 session 弱点演化趋势图
- 一句话：用户主页加 sparkline / 折线图，展示 baseline 等 slot 在历次 session 的覆盖度变化
- 评分价值：维度 4（核心闭环加深）；视觉感强，Demo 好看
- 工程量：S（前端 SVG ~150 行；后端复用 UserProfile 已有 recurring_weaknesses）
- 取舍：✅ Plan4 P0 候选——已被 spec D §1.2 砍但理由"粗略 hero stats 已够"在用户多次回访场景下不成立

### F6 PDF 解析（Plan3 已部分覆盖）
- 一句话：上传 PDF/Word 项目材料 → 自动解析
- 评分价值：减低 friction
- 工程量：✅ Plan3 G1 已实现 PDF + .docx + MD + TXT
- 取舍：—（已交付）

### F8 多项目主推对比
- 一句话：用户准备多个项目时，Coach 评估"面试时主推哪个" + 理由
- 评分价值：维度 1（理解用户）；对应"用户多项目焦虑"真痛点
- 工程量：M（需新 endpoint + 多项目并行打分 + 排序逻辑 + 前端对比 view）
- 取舍：⚪ Plan4 P1——有真实痛点但实施成本中等；可在 H1 用户访谈后决定

### G6 跨浏览器 STT (Safari/Firefox)
- 一句话：Safari/Firefox 没有 webkitSpeechRecognition，走服务端 MiMo STT
- 评分价值：可访问性；让 Mac/iOS 用户也能用语音
- 工程量：M（后端封装 STT endpoint + 录音 buffer + 上传 + 流式或整段返回）
- 取舍：⚪ Plan4 P1——评分作用次于 wow feature；如果 maintainer 自己用 Safari 会优先级提升

### G7 我的资料库 UI
- 一句话：用户回访时能看到曾上传过的文件，一键再次"用这个开训练"
- 评分价值：长期训练维度的延伸（Plan2 主题）
- 工程量：S（前端 view + 后端 GET endpoint，复用 data/uploads/<user_id>/）
- 取舍：✅ Plan4 P0——与 Plan2 长期训练主题强契合，工程量小

### G8 OCR 图片简历 / 手写笔记
- 一句话：上传简历照片 → OCR 抽文本
- 评分价值：扩输入模态
- 工程量：M-L（PaddleOCR 大依赖 / 腾讯 OCR API 加 key + cost 控制）
- 取舍：❌ Plan4 P2——大依赖 + 实际场景占比小；除非 H1 访谈出"很多人只有打印简历照片"这个明确痛点

### G9 视频项目介绍上传
- 一句话：用户上传 demo 视频 → 后端抽帧 + 字幕 → 注入项目材料
- 评分价值：扩输入模态；很 wow
- 工程量：L（视频处理 + ASR 字幕 + 帧抽取 + 多模态送 LLM 的 prompt 设计）
- 取舍：❌ Plan4 P2——工程门槛高 vs 实际使用频率低（"用户给 AI 模拟面试官看视频"心智负担大）

### G10 TTS voice 多选
- 一句话：UI 暴露 voice 选择，男声 / 女声 / 严肃 / 温和
- 评分价值：用户体验细节
- 工程量：S（前端 select + 后端 voice 参数已有，传 MiMo）
- 取舍：✅ Plan4 P0-stretch——若 MiMo 文档给清楚 voice 名单，工程量极小，可作为"细节品质"加分项

### G11 实时打断面试官（barge-in）
- 一句话：用户开口讲话时 TTS 朗读自动暂停
- 评分价值：沉浸感；接近真实视频面试
- 工程量：M（前端检测语音活动 / VAD + 中断 audio.pause()；后端无改动）
- 取舍：⚪ Plan4 P1——"沉浸感"维度有意义，工程量可控

### G12 STT 多语言混合切换
- 一句话：用户能在 zh-CN / en-US 之间切语音识别 lang
- 评分价值：英文面试场景
- 工程量：S（UI 加 lang select + VoiceInput 注入）
- 取舍：⚪ Plan4 P1——只有当 I10（英文面试模式）实施时才有意义；不单独做

### G13 上传文件版本管理
- 一句话：用户改了项目材料再上传，能看到 v1/v2 历史
- 评分价值：长期训练 + 进度可视化
- 工程量：S（后端 metadata 加 version 字段 + 前端 history list）
- 取舍：⚪ Plan4 P1——nice-to-have，与 G7 资料库 UI 配套实施

### G14 F4 简历多轮迭代支持上传 PDF
- 一句话：Plan2 F4 textarea 粘贴改成可上传 PDF
- 评分价值：F4 闭环增量改善
- 工程量：S（复用 Plan3 G1 上传 + 替换 F4 input）
- 取舍：✅ Plan4 P0——逻辑一致，工程量极小

### H1 真实用户访谈（3-5 人）
- 一句话：找 3-5 个准备保研复试 / 大厂实习面试的本科生，30min 微信聊天
- 评分价值：**维度 1 + 5 直接证据**——题面明示
- 工程量：S（人事工程：发问卷 / 约时间 / 整理记录）
- 取舍：✅ Plan4 P0——maintainer 早先 chose "不做"；但答辩前再补一轮强烈推荐

### H2 Memo / 答辩沉淀访谈
- 一句话：把 H1 访谈结论结构化写进 Memo + 答辩话术
- 评分价值：维度 1 直接拿分
- 工程量：S
- 取舍：✅ Plan4 P0（H1 配套）

### I1 多面试官 panel
- 一句话：同一项目召集 3 个不同视角的面试官（如"Researcher 视角问研究方法 / Engineer 视角问工程实现 / 老板视角问产品价值"），循环追问
- 评分价值：维度 4（核心闭环 stretch）+ wow
- 工程量：M-L（要扩 InterviewPacket schema 加 panelist[] / 状态机变多面试官 round-robin / UI 显示当前提问者）
- 取舍：❌ Plan4 P2——但作为答辩 stretch goal 提一句"如果有更多时间会做 multi-perspective"，体现长远思考；与 v2 设计哲学双 Agent 也有微冲突

### I2 面试录像 + 回放
- 一句话：把整轮面试（音频 + 文字 + 作弊模式 OS）打包成可重播 + 分享文件
- 评分价值：用户回访体验 + 社区分享传播
- 工程量：M（音频 buffer + 时间轴 + 回放 player）
- 取舍：⚪ Plan4 P1——与 I7 群组对练 + I14 公开榜组合时威力倍增；单独做意义中等

### I3 简历自动评分 + 改写质量量化
- 一句话：Coach 给 resume_rewrite.original / .rewritten / user_revised 各自打 0-100 分 + 用进度条展示"原 60 → Coach 78 → 用户改后 85"
- 评分价值：维度 4（量化反馈 = ChatGPT 做不到的具体性）
- 工程量：S（LLM 调用 + 前端 progress bar）
- 取舍：✅ Plan4 P0——工程量小、可视化效果强、对评分核心句"ChatGPT 经常抽象建议更具体"对话有力

### I4 Coach 风格定制（严厉/温和/苏格拉底）
- 一句话：onboarding 加 "Coach 性格" 选项，注入到所有 Coach prompt
- 评分价值：UX personalize；用户体验
- 工程量：S（schema 加字段 + prompts.py 模板分支）
- 取舍：⚪ Plan4 P1——nice-to-have；与 I10 英文模式同实施成本结构

### I5 答题模板提示（STAR / CAR）
- 一句话：用户讲完一段，Coach 提示"按 STAR 格式重组下" + 给具体重组建议
- 评分价值：维度 4（具体反馈）
- 工程量：S（Coach prompt 加 STAR 检测 + 重组指令）
- 取舍：✅ Plan4 P0——极轻量但 Demo 好看；与 v2「missing slots」检测在同一抽象层

### I6 项目-faculty 匹配（保研场景）
- 一句话：用户输入目标导师 / 课题组，Coach 拉对方近期 paper（abstract via web fetch）+ 方法论 → 引导用户在 S6 阶段对齐
- 评分价值：维度 1（保研场景深度）+ 维度 4（核心闭环 stretch）
- 工程量：M（web search / scholar API + abstract parsing + S6 prompt 注入）
- 取舍：⚪ Plan4 P1——保研场景独有但很硬核；H1 访谈中如果"导师匹配"成痛点，优先级提升

### I7 群组对练
- 一句话：多用户对同一项目互问 + 评论
- 评分价值：社区扩散
- 工程量：L（多用户隔离失效 / 实时通信 / moderation）
- 取舍：❌ Plan4 P2——v2-v4 范畴过大；写进 "Phase 2: 社区版" 章节作为长期愿景

### I8 答辩 PPT 自动生成
- 一句话：基于面试 transcript + 弱点报告 → 一键生成 PPT 大纲（每页 1 题 + 你的最强答案 + 风险点）
- 评分价值：用户拿走的可执行产物
- 工程量：M（LLM 生成 markdown ppt outline + 前端导出 .pptx via python-pptx 或 .md 给用户自己渲染）
- 取舍：⚪ Plan4 P1——与现有 Markdown 导出形成"complete report → action item"闭环

### I9 教练建议执行追踪（结构化 to-do）
- 一句话：next_training_plan 不再是一段文字，而是 [{description, slot, status}] 列表，用户能勾完成
- 评分价值：长期训练闭环 + 行为改变
- 工程量：S-M（schema 加字段 + UI 勾选 + 持久化）
- 取舍：✅ Plan4 P0——小投入大回报；evident "this product 真正能 帮你 准备" claim 加分

### I10 英文面试模式
- 一句话：UI 加 lang toggle，所有 Coach/Interviewer/Report prompt 切英文 + STT zh→en + TTS voice 切英文
- 评分价值：维度 1（求职大厂场景纯英文 round）
- 工程量：M（prompt 多语言 + voice 切换 + UI i18n）
- 取舍：⚪ Plan4 P1——求职大厂场景刚需，但工程量中等

### I11 数据持久化升级（SQLite）
- 一句话：v2 § 10 "不上 SQLite" 边界放开，支持复杂查询（如"我历史上 X 弱点演化"）
- 评分价值：维度 3（生产化）+ 工程基础设施
- 工程量：M（schema migration + 查询层重构）
- 取舍：❌ Plan4 P2——评分维度对接弱；除非用户量起来才必要

### I12 公网账号系统
- 一句话：从 anonymous user_id 升级到 OAuth / magic link
- 评分价值：维度 3（生产化）+ 跨设备
- 工程量：M（OAuth flow + session token + UI 改动）
- 取舍：❌ Plan4 P2——评分弱关联；spec D §3 明示"不做登录是设计意图"

### I13 maintainer dashboard
- 一句话：内部页面看 DAU / MAU / 平均 session 长度 / token cost / 弱点分布
- 评分价值：维度 3（生产化）+ 答辩素材
- 工程量：S-M（数据聚合 endpoint + 简单 chart UI）
- 取舍：⚪ Plan4 P1——maintainer 自己用，对答辩"产品演进数据"有支撑作用

### I14 公开榜
- 一句话：用户匿名分享自己的复盘报告 + 别人能看 + 评分
- 评分价值：社区扩散 + 病毒传播
- 工程量：L（匿名审核 / moderation / 隐私 / 排序）
- 取舍：❌ Plan4 P2——超出 4 周时间窗

---

## 3. 推荐分级

### Plan4 P0（4 周内做，按优先级）

1. **H1 + H2 用户访谈 + 沉淀**——题面明示 + 评分维度 1+5 直接得分（建议立刻起步，访谈本身耗时 1 周日历但只占 maintainer 几小时净工作）
2. **F3 弱点演化趋势图**——dashboard 视觉升级，工程量小
3. **G7 我的资料库 UI**——与 Plan2 长期训练主题契合，复用 data/uploads
4. **G14 F4 上传简历 PDF**——逻辑一致小补丁
5. **I3 简历评分量化**——Demo 好看 + 评分句对话有力
6. **I5 STAR 模板提示**——极轻量 Demo 加分
7. **I9 to-do 化训练计划**——长期闭环关键

合计：~7 个候选；估算 maintainer 净工作量 = 5-7 工作日（前端为主）

### Plan4 P1（值得做但 ROI 低于 P0）

- **F8 多项目对比**——访谈后决定
- **G6 跨浏览器 STT**——可访问性
- **G10 TTS voice 多选**——细节品质
- **G11 barge-in 打断**——沉浸感
- **G13 文件版本管理**——配套 G7
- **I2 录像回放**——配套 I7/I14 才有威力
- **I4 Coach 风格**——personalize
- **I6 faculty 匹配**——保研深度
- **I8 答辩 PPT 生成**——闭环延伸
- **I10 英文模式**——大厂场景刚需
- **I13 maintainer dashboard**——答辩素材

### Plan4 P2（明确不做 / 写进"刻意不做"）

- **G8 OCR**——大依赖 + 场景占比小
- **G9 视频上传**——心智负担大
- **G12 多语言独立**——只随 I10 一起
- **I1 多面试官 panel**——稀释 v2 双 Agent 设计哲学
- **I7 群组对练**——超出阶段
- **I11 SQLite 升级**——评分弱
- **I12 OAuth 账号**——v2 设计意图
- **I14 公开榜**——超阶段

---

## 4. Memo §下一步设计 草稿（直接用）

> ### 5. 下一步设计（再给一周怎么做）
>
> ProjectProbe 当前形态已闭环 (Coach + Interviewer + 状态机 + 作弊模式 + 长期训练 + 多模态)，下一周会沿三条主线深化：
>
> **(一) 把"理解用户"从假设变成证据。** 立即开展 3-5 人的本科生用户访谈，覆盖保研复试 + 大厂实习两类场景。访谈结论会直接重塑 [F3 弱点演化趋势图 / G7 资料库 UI / I9 to-do 化训练计划] 三条 P0 feature 的优先级。
>
> **(二) 把"长期训练"从可见变成可执行。** 现状是 Plan2 给了 dashboard 看见弱点，但用户拿到复盘后行为是否改变没追踪。下周加 [I9 to-do 化训练计划] 让 next_training_plan 从一段文字变成可勾选 todo，下次回访自动展示完成度。配合 [F3 趋势图]，闭环从"看见 → 重练"扩到"看见 → 重练 → 改简历 → 行为追踪"。
>
> **(三) 把"反馈具体性"再加一层。** 现状是 Coach 给 missing_evidence 文字反馈，但用户难以量化"我改进了多少"。下周加 [I3 简历评分量化]：Coach 给 resume_rewrite 各阶段打 0-100 分（原 60 → Coach 78 → 用户改后 85），进度条可视化。
>
> 这三条都直接服务"相比直接使用 ChatGPT，这个产品真的能更好地帮一个学生准备面试"——长期记忆 + 行为追踪 + 量化反馈，全部是 ChatGPT 单 session 无法做到的能力。
>
> **刻意不做**（与 v2-v3 设计哲学一致）：
> - 多面试官 panel（稀释双 Agent 信息不对称设计意图）
> - 完整登录系统 / OAuth（spec D 明示 anonymous + 本机 localStorage 是设计意图，不是工程妥协）
> - OCR / 视频面试（大依赖 + 实际场景占比低）
> - SQLite 升级（v2 §10 边界，mock 工具不需要数据库）
> - 跨用户社区 / 群组对练（超出阶段）

字数粗估：~360 字，可压缩到 1-2 页 Memo 中的 1 段。

---

## 5. 答辩话术化版本（直接背）

**Q："如果再给你一周，你会做什么？"**

> "再给一周，我会做三件事，每件都直接对应一个我现在产品里相对薄弱的评分维度。
>
> **第一件，访谈 5 个真实本科生。** 题面建议早就写了'找几个真实用户聊一聊'，但 16 小时挑战时我的判断是优先把核心闭环跑通而不是先做需求调研，承担了'我猜的痛点'风险。下一周访谈结果会重塑我对'保研 vs 求职'两个场景的相对权重，可能让我重新分配 Coach 双场景模板的复杂度。
>
> **第二件，把长期训练从可见做到可执行。** 现在 Plan2 的 dashboard 让用户'看见'弱点，但下一步训练计划还是一段文字。我会把 next_training_plan 重构成 [{description, slot, status}] 结构化 to-do，用户回访时自动展示完成度，让"复盘 → 重练 → 改简历 → 行为追踪"闭环完整。
>
> **第三件，给反馈加量化层。** 现在 Coach 给 missing_evidence 文字反馈，但'我改进了多少'用户感知不到。我会让 Coach 对 resume_rewrite 的 original / rewritten / user_revised 各打 0-100 分，进度条展示'原 60 → Coach 78 → 用户改后 85'。这与作弊模式同样是'让 ChatGPT 不能给的具体性变得可见'。
>
> **我刻意不做的**：多面试官 panel——会稀释我 v2 设计的双 Agent 信息不对称（Coach 懂你 / Interviewer 不懂你）哲学；完整登录系统——anonymous + localStorage 是 spec D §3 写明的设计意图，不是工程妥协；OCR / 视频上传——大依赖 + 实际场景占比低；SQLite 升级——v2 §10 边界，这是 mock 工具不是数据库系统。
>
> 我对自己的判断标准始终是核心评分句：'相比直接使用 ChatGPT，这个产品真的能更好地帮一个学生准备面试'。每个我加的功能都要回答这个问题，每个我砍的也都要回答这个问题。"

字数粗估：~580 字 / 约 2-2.5 分钟语速。

---

## 6. 答辩衍生准备（与本文档关联）

每个 P0/P1 候选可能被评委追问"为什么不做" / "怎么实现" / "工程难点是什么"。建议另起一份 `docs/talking-points.md` 整理：
- v2 设计取舍 12 条 (双 Agent / 状态机 / 不上 SQLite / anonymous / 单页 vanilla JS / ...)
- Plan2 长期训练设计取舍 6 条 (双索引存储 / 重练 mini-report 而非完整 EvaluationReport / 简历不限轮次自然收敛 / ...)
- Plan3 多模态设计取舍 5 条 (Chrome 原生 STT 而非服务端 / 双独立 toggle 默认 off / 文件白名单不做 OCR / TTS 默认 voice / ...)
- Plan4 候选取舍 (本文档 §3)

每条取舍 2-3 句故事化版本，便于答辩自然引用。

---

## 7. maintainer 决策需要的下一步

读完本文档后，maintainer 需要决定：

1. **H1 用户访谈：做不做？** 时间窗 1 周，maintainer 净工作 4-6 小时（约 5 人 × 30min + 整理）。如果做，立即起步。
2. **Plan4 P0 七条 + 一条 H1，是否同意分级？** 有调整建议直接 edit 本文档。
3. **是否要把 P0 七条单拆成正式 spec G/H/I/...?** 还是写一个统一 Plan4 spec？我倾向后者：spec F-plan4-overview.md（统一边界 + 模块清单），plan 拆 Plan4-A/B/C 子模块。
4. **Memo §下一步段直接用本 §4 草稿，还是另起？**
5. **答辩 talking points 文档是否要我现在起草？**
