# Spec B — 合成题库

> 起草日期：2026-05-10
> 父文档：[../overview.md](../overview.md)
> 范围：题库 seed + DeepSeek 离线合成 + 抽检 + 运行时查询 API
> 上游依赖：[Spec A](A-backend-agents.md) 的 `QuestionCard` / `Target` / `InterviewStage`

---

## 1. 模块边界

```
scripts/
└── synthesize_questions.py    离线合成脚本（一次性运行，结果落盘）

services/
└── question_bank.py           运行时查询 API（被 interviewer 调用）

data/
├── question_bank.seed.json         12 个手写 seed (reviewed=true)
└── question_bank.synthetic.json    合成扩展后最终题库 (~60 条，混合 seed)
```

**离线 vs 运行时分离**：合成脚本不在 `server/main.py` 内调用，避免运行时 LLM 浪费 token。Demo 路径只读 `data/question_bank.synthetic.json`。

---

## 2. QuestionCard schema

定义在 `services/schemas.py`（与 [Spec A](A-backend-agents.md) 一起，避免循环依赖）：

```python
from pydantic import BaseModel, Field
from datetime import datetime

class QuestionCard(BaseModel):
    id: str  # e.g. "eval_baseline_001"
    category: str  # 自由文本类别，e.g. "实验验证"
    tags: list[str]  # 项目类型 tag，e.g. ["baseline", "evaluation", "agent_project"]
    applies_to: list[Target] = Field(min_length=1)  # [保研] / [求职] / [保研, 求职]
    related_state: InterviewStage  # 此题主要服务哪个状态
    trigger: str  # 何时适合提这道题（自由文本）
    question: str  # 主问题
    followups: list[str] = Field(min_length=1, max_length=5)
    good_answer_points: list[str] = Field(min_length=2)
    red_flags: list[str] = Field(min_length=2)
    related_slots: list[str]  # 与 REQUIRED_SLOTS 中的 slot 名对应
    difficulty: RiskLevel = RiskLevel.MEDIUM
    source: Literal["seed", "synthetic"] = "synthetic"
    generated_at: datetime | None = None  # synthetic 才有
    reviewed: bool = False  # 只有 reviewed=true 的进入运行时
```

**约定**：`id` 命名规则 `{category_slug}_{topic_slug}_{nnn}`，如 `motivation_user_value_001`、`tech_alternatives_002`。便于人工抽检时按 prefix 分组。

---

## 3. 12 个 seed questions（手写覆盖核心追问类型）

每个 state 写 2 题。保证 demo 路径任何 state 都有 BANK 选题兜底。

### S1 项目动机 ×2

```json
[
  {
    "id": "motivation_user_value_001",
    "category": "项目动机",
    "tags": ["motivation", "user_pain"],
    "applies_to": ["保研", "求职"],
    "related_state": "S1_motivation",
    "trigger": "用户项目涉及解决某类用户痛点",
    "question": "你是怎么发现这个痛点真实存在的？你访谈过几个真实用户吗？",
    "followups": [
      "他们当时具体说了什么？能回忆一句原话吗？",
      "如果只用现有工具（Excel / ChatGPT）能不能解决？为什么不行？",
      "你的目标用户群有多大？怎么估算的？"
    ],
    "good_answer_points": [
      "举出真实用户访谈例子",
      "解释为什么现有工具不够",
      "对用户群规模有量化估计"
    ],
    "red_flags": [
      "「我觉得这个需求是真的」无证据",
      "把竞品介绍当用户痛点",
      "用户群只是「所有 X 用户」无细分"
    ],
    "related_slots": ["pain_real", "target_user"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "motivation_timing_001",
    "category": "项目动机",
    "tags": ["motivation", "timing"],
    "applies_to": ["保研", "求职"],
    "related_state": "S1_motivation",
    "trigger": "用户项目用了某种新技术（LLM / Agent / 多模态等）",
    "question": "为什么是现在做这个项目？这件事 2 年前能做吗？2 年后还会有意义吗？",
    "followups": [
      "如果用 GPT-3 时代的能力做，会差在哪里？",
      "如果你是投资人，为什么应该投资现在做这件事？"
    ],
    "good_answer_points": [
      "指出某项关键技术 / 数据 / 政策刚刚成熟",
      "解释机会窗口（为什么现在 vs 之前 / 之后）"
    ],
    "red_flags": [
      "「最近 AI 很火所以做」",
      "完全没考虑时机"
    ],
    "related_slots": ["timing"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  }
]
```

### S2 项目概述 ×2

```json
[
  {
    "id": "overview_personal_contribution_001",
    "category": "项目概述",
    "tags": ["personal_contribution", "team"],
    "applies_to": ["保研", "求职"],
    "related_state": "S2_overview",
    "trigger": "用户提到团队项目 / 多人合作",
    "question": "整个项目里，哪些部分是你独立完成的？哪些是团队其他人做的？",
    "followups": [
      "你独立完成的那部分，如果让团队其他人接手，他们能 1 天内上手吗？",
      "你贡献最大的一个技术决策是什么？为什么是你做的，不是别人？"
    ],
    "good_answer_points": [
      "清晰区分自己 vs 团队的工作边界",
      "举出 ≥1 个具体技术决策 + 自己的角色",
      "用「我设计 / 我实现 / 我调试」具体动词"
    ],
    "red_flags": [
      "全程「我们」无法区分个人贡献",
      "贡献描述只到「我也参与了」",
      "把团队成果包装成个人成果"
    ],
    "related_slots": ["personal_contribution"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "overview_architecture_001",
    "category": "项目概述",
    "tags": ["architecture", "system_design"],
    "applies_to": ["保研", "求职"],
    "related_state": "S2_overview",
    "trigger": "用户项目有 ≥2 个组件 / 模块 / Agent",
    "question": "请用 ≤30 秒描述系统架构。哪一个模块是你认为设计最巧妙的？",
    "followups": [
      "如果去掉那个最巧妙的模块，系统会怎样？",
      "数据从输入到输出经过几跳？每一跳都必要吗？"
    ],
    "good_answer_points": [
      "30 秒能讲完主架构（说明用户真懂）",
      "指出关键设计决策并解释 why",
      "能讲清「不要什么」（去除冗余）"
    ],
    "red_flags": [
      "讲 5 分钟还没讲到核心",
      "只能罗列模块名，讲不出关系",
      "无法回答「去掉某模块会怎样」"
    ],
    "related_slots": ["architecture", "user_flow"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  }
]
```

### S3 技术深挖 ×2

```json
[
  {
    "id": "tech_alternatives_001",
    "category": "技术深挖",
    "tags": ["alternatives", "method_choice"],
    "applies_to": ["保研", "求职"],
    "related_state": "S3_technical",
    "trigger": "用户项目用了某种 ML 方法 / 框架 / 算法",
    "question": "你为什么选了这个方法而不是 X？X 的优势在你这个场景里被什么 trade-off 否决了？",
    "followups": [
      "如果你的输入数据规模翻 10 倍，你的方法选择会变吗？",
      "如果让你重新做这个项目，会改方法吗？"
    ],
    "good_answer_points": [
      "明确说出考虑过的备选方案",
      "用具体 trade-off 解释（不是「这个更好」）",
      "承认当前方法的局限"
    ],
    "red_flags": [
      "「这是最常用的方法」无对比",
      "「这个方法效果好」无定量比较",
      "完全没考虑过备选"
    ],
    "related_slots": ["method_choice_reason", "alternatives"],
    "difficulty": "高",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "tech_engineering_001",
    "category": "技术深挖",
    "tags": ["engineering", "production"],
    "applies_to": ["求职"],
    "related_state": "S3_technical",
    "trigger": "用户项目部署到了真实环境 / 有实际用户",
    "question": "项目上线 / 给真实用户用过之后，你修过的最棘手的 1 个 bug 是什么？根因是什么？",
    "followups": [
      "你怎么发现这个 bug 的？有 monitoring 吗？",
      "修复后有什么 regression test 防止它复发？"
    ],
    "good_answer_points": [
      "讲出具体 bug 现象 + 根因",
      "讲清自己 debug 的步骤",
      "提到 monitoring / regression 等工程实践"
    ],
    "red_flags": [
      "讲不出具体 bug（说明项目其实没真跑）",
      "「调一调就好了」无根因分析"
    ],
    "related_slots": ["engineering_details"],
    "difficulty": "高",
    "source": "seed",
    "reviewed": true
  }
]
```

### S4 实验验证 ×2

```json
[
  {
    "id": "eval_baseline_001",
    "category": "实验验证",
    "tags": ["baseline", "evaluation"],
    "applies_to": ["保研", "求职"],
    "related_state": "S4_validation",
    "trigger": "用户项目中提到模型 / Agent / 系统效果 / 自动化提升",
    "question": "你如何证明你的方案比一个更简单的 baseline 更好？",
    "followups": [
      "你的 baseline 具体是什么？",
      "你比较的是准确率、效率、成本，还是用户体验？",
      "如果没有量化实验，你如何让面试官相信这个提升是真实的？"
    ],
    "good_answer_points": [
      "明确 baseline（如「直接调 GPT-4」/「人工」）",
      "定义评估指标",
      "说明数据来源",
      "给出对比结果（量化或定性）"
    ],
    "red_flags": [
      "只说效果更好但没有证据",
      "没有 baseline",
      "没有指标",
      "把主观体验当唯一证明"
    ],
    "related_slots": ["baseline", "metric", "data_source", "control_experiment"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "eval_error_analysis_001",
    "category": "实验验证",
    "tags": ["error_analysis", "evaluation"],
    "applies_to": ["保研", "求职"],
    "related_state": "S4_validation",
    "trigger": "用户项目有评估实验",
    "question": "你的方案错的那些 case，你分析过原因吗？错误分布是什么？",
    "followups": [
      "错误中有多少是模型本身的问题，多少是数据 / 评估的问题？",
      "你有没有发现某一类错误特别集中？怎么解释？"
    ],
    "good_answer_points": [
      "做过错误分类",
      "区分模型错 / 数据错 / 评估错",
      "举出具体错误 case + 原因假设"
    ],
    "red_flags": [
      "「准确率 85%」但说不出错的那 15% 是什么",
      "把所有错都归因为「数据不够」"
    ],
    "related_slots": ["error_analysis"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  }
]
```

### S5 失败反思 ×2

```json
[
  {
    "id": "reflect_edge_case_001",
    "category": "失败反思",
    "tags": ["edge_case", "robustness"],
    "applies_to": ["保研", "求职"],
    "related_state": "S5_reflection",
    "trigger": "用户项目处理某种结构化或半结构化输入",
    "question": "举一个让你的系统当场出错 / 表现糟糕的具体输入。为什么会糟糕？",
    "followups": [
      "你发现这个 edge case 是在开发中、测试中还是真实使用中？",
      "如果让你重做，怎么从设计上避免这一类 edge case？"
    ],
    "good_answer_points": [
      "讲出具体 edge case 输入 + 现象",
      "解释根因",
      "讨论设计层面的改进方案"
    ],
    "red_flags": [
      "「我们没遇到过失败」（说明测试覆盖太薄）",
      "把 edge case 推给「用户用错了」"
    ],
    "related_slots": ["failure_case", "edge_condition"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "reflect_limit_001",
    "category": "失败反思",
    "tags": ["current_limit", "honesty"],
    "applies_to": ["保研", "求职"],
    "related_state": "S5_reflection",
    "trigger": "面试已进行 ≥4 轮",
    "question": "如果让你诚实评价：你这个项目目前最大的局限是什么？面试官最容易在哪里打你脸？",
    "followups": [
      "知道这个局限后，你下一步会怎么解决？",
      "为什么之前没解决？"
    ],
    "good_answer_points": [
      "诚实说出真实局限（不假装完美）",
      "对局限有思考 + 改进路线",
      "解释为什么暂未解决（资源 / 时间 / 数据 / 技术 trade-off）"
    ],
    "red_flags": [
      "「目前没什么局限」（致命）",
      "把局限说成「未来 work」逃避当下问题"
    ],
    "related_slots": ["current_limit", "improvement"],
    "difficulty": "高",
    "source": "seed",
    "reviewed": true
  }
]
```

### S6 匹配与总结 ×2（每场景 1 题）

```json
[
  {
    "id": "match_research_direction_001",
    "category": "匹配与总结",
    "tags": ["research_direction", "fit"],
    "applies_to": ["保研"],
    "related_state": "S6_matching",
    "trigger": "保研场景，面试已到收尾",
    "question": "你这个项目和你想报考的实验室 / 老师的研究方向具体哪里 overlap？哪里不 overlap？",
    "followups": [
      "如果不 overlap 的部分让面试老师觉得你「不专一」，你怎么解释？",
      "未来研究方向里你最想往哪个 sub-direction 深挖？"
    ],
    "good_answer_points": [
      "具体说出实验室 / 老师近 2 年的工作",
      "诚实指出 overlap 与 gap",
      "把 gap 解释为「跨域优势」而非「不相关」"
    ],
    "red_flags": [
      "对目标实验室一无所知",
      "硬套「我也做 AI 你们也做 AI 所以匹配」"
    ],
    "related_slots": ["match_to_target", "future_direction", "fit_reason"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  },
  {
    "id": "match_job_role_001",
    "category": "匹配与总结",
    "tags": ["job_role", "fit"],
    "applies_to": ["求职"],
    "related_state": "S6_matching",
    "trigger": "求职场景，面试已到收尾",
    "question": "如果你今天加入这个团队，你能在 1 个月内交付什么？这个项目里哪些经验可以直接迁移？",
    "followups": [
      "你做不到的部分（团队需要你做但你没做过）会是什么？",
      "你打算如何快速补齐？"
    ],
    "good_answer_points": [
      "用项目经验对应到具体团队 deliverable",
      "诚实承认空缺",
      "给出可执行的补齐路线"
    ],
    "red_flags": [
      "「我什么都能学」无具体迁移路径",
      "把所有 JD 关键词照单全收"
    ],
    "related_slots": ["match_to_target", "personal_growth", "fit_reason"],
    "difficulty": "中",
    "source": "seed",
    "reviewed": true
  }
]
```

---

## 4. 合成扩展脚本（scripts/synthesize_questions.py）

### 4.1 输入 / 输出

```python
# 命令行运行（不在 server 里调）
$ pixi run python scripts/synthesize_questions.py \
    --seed data/question_bank.seed.json \
    --target-count 60 \
    --batch-size 6 \
    --out data/question_bank.synthetic.json
```

输入：`--seed` 12 个 seed
处理：分批调 DeepSeek（每批 ~6 题，避免单次输出过长 → 解析失败）
输出：`--out` 含 seed + 合成扩展，约 60 条；新合成的 `reviewed=false`

### 4.2 合成 prompt

```python
SYNTHESIZE_PROMPT = """
你是 AI 保研复试 / AI 岗位面试题库设计专家。请围绕 AI 本科生项目经历生成
高质量项目深挖问题。

【输入】
- category: {category}
- target_state: {state}
- target_audience: {applies_to}  # 保研 / 求职 / 两者
- existing_seed_questions: {seeds}  # 同类已有的题，用于避免重复

【任务】
生成 {batch_size} 道新题，要求：
1. 不与 existing_seed 重复（措辞 / 切入角度都要不同）
2. 必须能追问用户的真实项目细节（不要泛泛八股）
3. 每题包含 followups (1-5 题) + good_answer_points (≥2) + red_flags (≥2)
4. 每题标注 applies_to (从 [保研, 求职] 选一个或两个)
5. 每题标注 related_slots（从下面 slot 列表选）：{slot_list}
6. 不生成 「请介绍你的项目」 / 「你最大的优势是什么」 这类低质八股

【输出】
合法 JSON 数组，每个元素是 QuestionCard schema（去掉 id / source / reviewed
/ generated_at；脚本会自动补）。不要带 Markdown 代码块包裹。不要解释文字。

JSON Schema:
{schema_json}
"""
```

### 4.3 合成流程

```python
async def synthesize_for_state(state: InterviewStage, target_per_state: int = 8):
    seeds = load_seeds_for_state(state)
    batches = (target_per_state + BATCH_SIZE - 1) // BATCH_SIZE
    all_new = []
    for i in range(batches):
        batch = await call_deepseek(
            messages=[
                {"role": "system", "content": SYNTHESIZE_SYSTEM},
                {"role": "user", "content": SYNTHESIZE_PROMPT.format(...)},
            ],
            response_schema=list[QuestionCardDraft],  # 不含 id / source / reviewed
            temperature=0.9,  # 高 temperature 增加多样性
        )
        all_new.extend(batch)
    return all_new

async def main():
    final = load_seeds()  # 12 题
    for state in InterviewStage:
        if state == InterviewStage.DONE:
            continue
        new = await synthesize_for_state(state)
        for card in new:
            card.id = generate_id(card.category, card.tags)
            card.source = "synthetic"
            card.generated_at = datetime.utcnow()
            card.reviewed = False  # 待人工抽检
        final.extend(new)
    write_json("data/question_bank.synthetic.json", final)
```

---

## 5. 抽检流程

合成完毕后必须人工抽检，否则**低质题进入 demo 路径会拖累 wow moment**。

### 5.1 自动 sanity check（脚本内置）

合成时即时检查，未通过的直接丢弃：

```python
def is_card_valid(card: dict) -> bool:
    # 必填字段
    required = ["question", "followups", "good_answer_points", "red_flags",
                "applies_to", "related_state", "related_slots"]
    if not all(card.get(k) for k in required):
        return False
    # 长度约束
    if len(card["followups"]) < 1 or len(card["followups"]) > 5: return False
    if len(card["good_answer_points"]) < 2: return False
    if len(card["red_flags"]) < 2: return False
    # 反「请介绍你的项目」黑名单
    BANNED_PATTERNS = ["介绍你的项目", "你最大的优势", "你最大的缺点", "你的职业规划"]
    if any(p in card["question"] for p in BANNED_PATTERNS):
        return False
    return True
```

### 5.2 人工抽检 checklist

打开 `data/question_bank.synthetic.json`，遍历 `reviewed=false` 的卡，对每张回答：

- [ ] 这道题是否在追问**项目具体细节**（vs 泛泛八股）？
- [ ] followups 是否能继续追问（vs 重复主问题）？
- [ ] good_answer_points 是否具体可验证？
- [ ] red_flags 是否能识别真实空泛回答？
- [ ] applies_to 标注是否合理？
- [ ] related_slots 是否对得上 [Spec A §5.1](A-backend-agents.md#51) 的 slot 名？

通过 → `reviewed: true`；不通过 → 删除。

**Demo 时间紧 fallback**：抽检至少前 18 题（每 state 3 题）。其余可后续补，运行时只查 `reviewed=true`。

---

## 6. 运行时查询 API（services/question_bank.py）

```python
from collections import Counter

class QuestionBank:
    def __init__(self, path: Path = Path("data/question_bank.synthetic.json")):
        self._cards: list[QuestionCard] = []
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            # fallback to seed-only
            path = Path("data/question_bank.seed.json")
        if not path.exists():
            raise QuestionBankError("题库文件缺失，请先运行 scripts/synthesize_questions.py")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._cards = [QuestionCard(**d) for d in data if d.get("reviewed")]

    def query(
        self,
        target: Target,
        state: InterviewStage,
        project_tags: list[str] = [],
        exclude_ids: list[str] = [],
    ) -> QuestionCard | None:
        candidates = [
            c for c in self._cards
            if c.related_state == state
            and target in c.applies_to
            and c.id not in exclude_ids
        ]
        if not candidates:
            return None
        # 排序：tag 重叠数 desc → difficulty 升序 → reviewed=true 优先
        def score(c: QuestionCard) -> tuple:
            tag_overlap = len(set(c.tags) & set(project_tags))
            diff_rank = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}[c.difficulty]
            return (-tag_overlap, diff_rank)
        candidates.sort(key=score)
        return candidates[0]
```

**注意**：`applies_to` 含 `Target.HUNHE` 时，HUNHE 用户两套题都能取（query 时 target=HUNHE 应当 match 含 BAOYAN 或 QIUZHI 的题）。修正：

```python
def _matches_target(card: QuestionCard, target: Target) -> bool:
    if target == Target.HUNHE:
        return True  # 混合用户全部可取
    return target in card.applies_to
```

---

## 7. 错误兜底

| 错误 | 处理 |
|---|---|
| `data/question_bank.synthetic.json` 缺失 | 启动时 fallback 到 `data/question_bank.seed.json`（12 题足够 demo） |
| 两个文件都缺失 | 启动失败 + 明确报错 + 提示运行合成脚本 |
| query 无匹配 | 返回 `None`，由调用方（`interviewer.select_next_question`）回退到 LLM 现场生成 |
| 合成脚本运行中网络中断 | 已合成的写入文件（不要等全部完成才写）；下次运行从已有数检测断点续传 |

---

## 8. 实施顺序

```
Step 1: 写 12 个 seed → data/question_bank.seed.json    （手写，~30min）
Step 2: 写 services/question_bank.py + 单元测试         （~30min）
Step 3: 写 scripts/synthesize_questions.py              （~45min）
Step 4: 跑合成脚本生成 data/question_bank.synthetic.json （LLM 调用 ~15min）
Step 5: 人工抽检至少 18 题，标 reviewed=true            （~30min）
```

总耗时 ~2.5h；可由 1 个 implementer 独立完成（与 [Spec A](A-backend-agents.md) 主流程并行）。

**关键：Step 1 必须在 Step 4 之前完成**——合成脚本要把 seed 作为 prompt 上下文（避免重复）。

