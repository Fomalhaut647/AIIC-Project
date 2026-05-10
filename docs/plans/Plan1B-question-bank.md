# AIIC v2 Plan1B — Question Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 [Spec B](../specs/B-question-bank.md) 全部内容：12 个手写 seed → DeepSeek 合成扩展到 ~60 题 → 人工抽检 → 运行时查询 API。

**Architecture:** 离线合成（`scripts/synthesize_questions.py`，一次性运行）+ 运行时查询（`services/question_bank.py`，被 Interviewer 调用）。两者共享 `services/schemas.py:QuestionCard`（在 Plan1A Task A2 定义）。

**Tech Stack:** Python (Pixi) / Pydantic v2 / DeepSeek API（复用 services/llm.py）/ pytest

**Pre-conditions:**
- Plan1A Task A2 已完成（`services/schemas.py:QuestionCard` 等存在）
- Plan1A Task A5 已完成（`services/llm.py:call_deepseek` 可用）
- 本 plan 与 Plan1A 大部分任务可并行（仅 B2/B3/B4 需先有 schemas + llm）

**Spec coverage:**

| Spec B 节 | Plan task |
|---|---|
| §1 模块边界 | B1 (paths) |
| §2 QuestionCard schema | （Plan1A A2 已含） |
| §3 12 seed questions | B1 |
| §4 合成扩展脚本 | B3, B4 |
| §5 抽检流程（自动 + 人工） | B3 (auto), B6 (manual) |
| §6 运行时查询 API | B2 |
| §7 错误兜底 | B2, B4 |
| §8 实施顺序 | 任务编号即顺序 |

---

### Task B1: 写 12 个 seed → data/question_bank.seed.json

**Files:**
- Create: `data/question_bank.seed.json`
- Test: `tests/test_seed_loadable.py`

完整 12 个 seed 的内容来自 [Spec B §3](../specs/B-question-bank.md#3-12-个-seed-questions手写覆盖核心追问类型)。直接拷贝。

- [ ] **Step 1: 创建 data/question_bank.seed.json**

把 Spec B §3 的 6 段 JSON 数组合并成一个大数组（12 个对象），写入 `data/question_bank.seed.json`。

注意：每条卡片必须含完整字段（id / category / tags / applies_to / related_state / trigger / question / followups / good_answer_points / red_flags / related_slots / difficulty / source="seed" / reviewed=true）。

完整 12 题对应：
- S1: `motivation_user_value_001`, `motivation_timing_001`
- S2: `overview_personal_contribution_001`, `overview_architecture_001`
- S3: `tech_alternatives_001`, `tech_engineering_001`
- S4: `eval_baseline_001`, `eval_error_analysis_001`
- S5: `reflect_edge_case_001`, `reflect_limit_001`
- S6: `match_research_direction_001` (applies_to=[保研]), `match_job_role_001` (applies_to=[求职])

直接照抄 [Spec B §3](../specs/B-question-bank.md#3-12-个-seed-questions手写覆盖核心追问类型) 的内容；不要改写或简化。

- [ ] **Step 2: 写 tests/test_seed_loadable.py**

```python
import json
from pathlib import Path
from services.schemas import QuestionCard, InterviewStage


def test_seed_file_exists():
    assert Path("data/question_bank.seed.json").exists()


def test_seed_has_12_cards():
    data = json.loads(Path("data/question_bank.seed.json").read_text(encoding="utf-8"))
    assert len(data) == 12


def test_seed_all_pydantic_loadable():
    data = json.loads(Path("data/question_bank.seed.json").read_text(encoding="utf-8"))
    cards = [QuestionCard(**d) for d in data]
    # 全部 reviewed=true
    assert all(c.reviewed for c in cards)
    # 全部 source=seed
    assert all(c.source == "seed" for c in cards)


def test_seed_covers_all_states():
    data = json.loads(Path("data/question_bank.seed.json").read_text(encoding="utf-8"))
    states = {d["related_state"] for d in data}
    expected = {
        InterviewStage.S1_MOTIVATION.value,
        InterviewStage.S2_OVERVIEW.value,
        InterviewStage.S3_TECHNICAL.value,
        InterviewStage.S4_VALIDATION.value,
        InterviewStage.S5_REFLECTION.value,
        InterviewStage.S6_MATCHING.value,
    }
    assert states == expected
```

- [ ] **Step 3: Run tests**

```bash
pixi run pytest tests/test_seed_loadable.py -v
```

Expected: 4 PASS.

- [ ] **Step 4: Commit**

```bash
git add data/question_bank.seed.json tests/test_seed_loadable.py
git commit -m "feat(question-bank): add 12 hand-written seed questions covering S1-S6"
```

---

### Task B2: services/question_bank.py — QuestionBank 类 + query

**Files:**
- Modify: `services/question_bank.py`（替换 Plan1A Task A10 的 stub）
- Test: `tests/test_question_bank.py`

- [ ] **Step 1: 写 tests/test_question_bank.py（先写测试）**

```python
import json
from pathlib import Path
import pytest
from services.schemas import (
    Target, InterviewStage, RiskLevel, QuestionCard,
)
from services.question_bank import QuestionBank, QuestionBankError


@pytest.fixture
def bank_with_seed():
    return QuestionBank(path=Path("data/question_bank.seed.json"))


def test_load_seed_and_query_s1_baoyan(bank_with_seed):
    card = bank_with_seed.query(target=Target.BAOYAN, state=InterviewStage.S1_MOTIVATION)
    assert card is not None
    assert Target.BAOYAN in card.applies_to


def test_query_qiuzhi_s4(bank_with_seed):
    card = bank_with_seed.query(target=Target.QIUZHI, state=InterviewStage.S4_VALIDATION)
    assert card is not None
    assert Target.QIUZHI in card.applies_to


def test_query_excludes_used(bank_with_seed):
    first = bank_with_seed.query(target=Target.BAOYAN, state=InterviewStage.S1_MOTIVATION)
    second = bank_with_seed.query(
        target=Target.BAOYAN, state=InterviewStage.S1_MOTIVATION,
        exclude_ids=[first.id],
    )
    if second is not None:  # S1 有 2 题，第二查应得到另一题
        assert second.id != first.id


def test_query_no_match_returns_none(bank_with_seed):
    card = bank_with_seed.query(target=Target.QIUZHI, state=InterviewStage.S6_MATCHING)
    # match_job_role_001 only applies_to=[求职]; 应该有结果
    assert card is not None


def test_hunhe_target_matches_all(bank_with_seed):
    # HUNHE 用户应该能取到任何 applies_to 的题
    card = bank_with_seed.query(target=Target.HUNHE, state=InterviewStage.S6_MATCHING)
    assert card is not None


def test_query_prefers_tag_overlap(bank_with_seed):
    # 给 project_tags 包含 "baseline"
    card = bank_with_seed.query(
        target=Target.QIUZHI,
        state=InterviewStage.S4_VALIDATION,
        project_tags=["baseline"],
    )
    assert card is not None
    # eval_baseline_001 的 tags 含 baseline，应优先选中
    assert "baseline" in card.tags


def test_missing_file_raises():
    with pytest.raises(QuestionBankError):
        QuestionBank(path=Path("/nonexistent/path.json"))
```

- [ ] **Step 2: Run test → 应失败**

```bash
pixi run pytest tests/test_question_bank.py -v
```

Expected: stub `QuestionBank` 总返回 None，多数 test 失败。

- [ ] **Step 3: 实现 services/question_bank.py（替换 stub）**

```python
"""QuestionBank — 运行时题库查询。从 data/*.json 加载 reviewed 题。"""
from __future__ import annotations
import json
from pathlib import Path

from services.schemas import (
    InterviewStage, QuestionCard, RiskLevel, Target,
)


class QuestionBankError(Exception):
    pass


class QuestionBank:
    def __init__(self, path: Path | None = None):
        if path is None:
            # 默认优先用合成版，缺失则 fallback 到 seed
            primary = Path("data/question_bank.synthetic.json")
            seed = Path("data/question_bank.seed.json")
            path = primary if primary.exists() else seed
        path = Path(path)
        if not path.exists():
            raise QuestionBankError(
                f"题库文件缺失: {path}。请先运行 scripts/synthesize_questions.py，"
                f"或确认 data/question_bank.seed.json 存在。"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise QuestionBankError(f"题库文件 {path} JSON 解析失败: {e}")
        self._cards: list[QuestionCard] = [
            QuestionCard(**d) for d in data if d.get("reviewed")
        ]
        if not self._cards:
            raise QuestionBankError(
                f"题库文件 {path} 没有 reviewed=true 的卡片，请先抽检。"
            )

    def _matches_target(self, card: QuestionCard, target: Target) -> bool:
        if target == Target.HUNHE:
            return True
        return target in card.applies_to

    def query(
        self,
        target: Target,
        state: InterviewStage,
        project_tags: list[str] | None = None,
        exclude_ids: list[str] | None = None,
    ) -> QuestionCard | None:
        project_tags = project_tags or []
        exclude_ids = exclude_ids or []
        candidates = [
            c for c in self._cards
            if c.related_state == state
            and self._matches_target(c, target)
            and c.id not in exclude_ids
        ]
        if not candidates:
            return None

        diff_rank = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

        def score_key(c: QuestionCard) -> tuple:
            tag_overlap = len(set(c.tags) & set(project_tags))
            return (-tag_overlap, diff_rank[c.difficulty])

        candidates.sort(key=score_key)
        return candidates[0]
```

- [ ] **Step 4: Run test → 应通过**

```bash
pixi run pytest tests/test_question_bank.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/question_bank.py tests/test_question_bank.py
git commit -m "feat(question-bank): implement QuestionBank.query with target/state/tag filters"
```

---

### Task B3: scripts/synthesize_questions.py — sanity check + 框架

**Files:**
- Create: `scripts/synthesize_questions.py`
- Test: `tests/test_synthesize_sanity.py`

- [ ] **Step 1: 写 tests/test_synthesize_sanity.py**

```python
from scripts.synthesize_questions import is_card_valid


def _base_card():
    return {
        "question": "你的 baseline 是什么？",
        "followups": ["怎么对比？"],
        "good_answer_points": ["明确 baseline", "对比方法"],
        "red_flags": ["没有 baseline", "无对比"],
        "applies_to": ["保研"],
        "related_state": "S4_validation",
        "related_slots": ["baseline"],
    }


def test_valid_card():
    assert is_card_valid(_base_card()) is True


def test_missing_required_field():
    c = _base_card()
    del c["question"]
    assert is_card_valid(c) is False


def test_followups_too_few():
    c = _base_card()
    c["followups"] = []
    assert is_card_valid(c) is False


def test_followups_too_many():
    c = _base_card()
    c["followups"] = ["q"] * 6
    assert is_card_valid(c) is False


def test_good_answer_points_too_few():
    c = _base_card()
    c["good_answer_points"] = ["only one"]
    assert is_card_valid(c) is False


def test_red_flags_too_few():
    c = _base_card()
    c["red_flags"] = ["only one"]
    assert is_card_valid(c) is False


def test_banned_pattern():
    c = _base_card()
    c["question"] = "请介绍你的项目。"
    assert is_card_valid(c) is False
```

- [ ] **Step 2: Run test → 应失败**

```bash
pixi run pytest tests/test_synthesize_sanity.py -v
```

Expected: ImportError.

- [ ] **Step 3: 写 scripts/synthesize_questions.py 的 sanity 部分**

```python
"""离线合成题库脚本。一次性运行，结果落 data/question_bank.synthetic.json。"""
from __future__ import annotations

BANNED_PATTERNS = [
    "介绍你的项目", "你最大的优势", "你最大的缺点", "你的职业规划",
]


def is_card_valid(card: dict) -> bool:
    """Sanity check 单张合成题卡。返回 False 即丢弃。"""
    required = [
        "question", "followups", "good_answer_points", "red_flags",
        "applies_to", "related_state", "related_slots",
    ]
    if not all(card.get(k) for k in required):
        return False
    if not (1 <= len(card["followups"]) <= 5):
        return False
    if len(card["good_answer_points"]) < 2:
        return False
    if len(card["red_flags"]) < 2:
        return False
    if any(p in card["question"] for p in BANNED_PATTERNS):
        return False
    return True
```

- [ ] **Step 4: Run test → 应通过**

```bash
pixi run pytest tests/test_synthesize_sanity.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/synthesize_questions.py tests/test_synthesize_sanity.py
git commit -m "feat(synthesize): add is_card_valid sanity check + banned pattern blocklist"
```

---

### Task B4: scripts/synthesize_questions.py — main 流程

**Files:**
- Modify: `scripts/synthesize_questions.py`

- [ ] **Step 1: 在 scripts/synthesize_questions.py 末尾追加**

```python
import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from services.llm import call_deepseek
from services.schemas import (
    InterviewStage, QuestionCard, RiskLevel, Target,
)


SYNTHESIZE_SYSTEM = """\
你是 AI 保研复试 / AI 岗位面试题库设计专家。请围绕 AI 本科生项目经历生成
高质量项目深挖问题。
"""

SYNTHESIZE_USER_TEMPLATE = """\
【输入】
- category: {category}
- target_state: {state}
- target_audience: {applies_to}
- existing_seed_questions: {seeds_json}

【任务】
生成 {batch_size} 道新题，要求：
1. 不与 existing_seed 重复（措辞 / 切入角度都要不同）
2. 必须能追问用户的真实项目细节（不要泛泛八股）
3. 每题包含 followups (1-5 题) + good_answer_points (≥2) + red_flags (≥2)
4. 每题标注 applies_to (从 [保研, 求职] 选一个或两个)
5. 每题标注 related_slots（自由文本，对应 InterviewerOS.missing_slots 用法）
6. 不生成 「请介绍你的项目」 / 「你最大的优势是什么」 等低质八股
"""


class _CardDraft(BaseModel):
    """合成 LLM 输出的卡片草案（不含 id / source / generated_at / reviewed）。"""
    category: str
    tags: list[str]
    applies_to: list[Target] = Field(min_length=1)
    related_state: InterviewStage
    trigger: str
    question: str
    followups: list[str] = Field(min_length=1, max_length=5)
    good_answer_points: list[str] = Field(min_length=2)
    red_flags: list[str] = Field(min_length=2)
    related_slots: list[str]
    difficulty: RiskLevel = RiskLevel.MEDIUM


class _CardBatch(BaseModel):
    cards: list[_CardDraft]


def _generate_id(category: str, idx: int) -> str:
    slug = category.replace(" ", "_").replace("/", "_")
    return f"syn_{slug}_{idx:03d}_{uuid.uuid4().hex[:6]}"


def _load_seeds_for_state(seeds: list[dict], state: InterviewStage) -> list[dict]:
    return [s for s in seeds if s.get("related_state") == state.value]


async def _synthesize_batch(
    state: InterviewStage,
    seeds_for_state: list[dict],
    batch_size: int,
) -> list[_CardDraft]:
    seeds_json = json.dumps([{
        "question": s["question"],
        "applies_to": s["applies_to"],
    } for s in seeds_for_state], ensure_ascii=False)
    msgs = [
        {"role": "system", "content": SYNTHESIZE_SYSTEM},
        {"role": "user", "content": SYNTHESIZE_USER_TEMPLATE.format(
            category=seeds_for_state[0]["category"] if seeds_for_state else "项目深挖",
            state=state.value,
            applies_to=["保研", "求职"],
            seeds_json=seeds_json,
            batch_size=batch_size,
        )},
    ]
    fallback = _CardBatch(cards=[])  # 失败 = 空批次（不阻塞）
    batch = await call_deepseek(
        msgs, response_schema=_CardBatch,
        temperature=0.9, max_tokens=4000, fallback=fallback,
    )
    return batch.cards


async def _main(seed_path: Path, out_path: Path, target_per_state: int, batch_size: int):
    seeds = json.loads(seed_path.read_text(encoding="utf-8"))
    final = list(seeds)  # 包含 12 seed
    next_idx = 1

    for state in InterviewStage:
        if state == InterviewStage.DONE:
            continue
        seeds_for_state = _load_seeds_for_state(seeds, state)
        batches = (target_per_state + batch_size - 1) // batch_size
        accumulated: list[_CardDraft] = []
        for b in range(batches):
            print(f"[{state.value}] batch {b+1}/{batches}...")
            new = await _synthesize_batch(state, seeds_for_state, batch_size)
            accumulated.extend(new)
        # 转 dict + 加 id / source / generated_at / reviewed=False
        for card in accumulated:
            d = card.model_dump(mode="json")
            if not is_card_valid(d):
                continue
            d["id"] = _generate_id(d["category"], next_idx)
            d["source"] = "synthetic"
            d["generated_at"] = datetime.now(timezone.utc).isoformat()
            d["reviewed"] = False
            final.append(d)
            next_idx += 1

    out_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(final)} cards to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=Path("data/question_bank.seed.json"))
    parser.add_argument("--out", type=Path, default=Path("data/question_bank.synthetic.json"))
    parser.add_argument("--target-count", type=int, default=60,
                        help="总目标 ~60 (除 12 seed 外约 48 合成)")
    parser.add_argument("--batch-size", type=int, default=6)
    args = parser.parse_args()
    per_state = (args.target_count - 12) // 6  # 6 个 state（除 DONE）
    asyncio.run(_main(args.seed, args.out, per_state, args.batch_size))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 在 pixi.toml [tasks] 节加入合成 task**

```toml
[tasks]
# ... 已有 task ...
synthesize-questions = "python scripts/synthesize_questions.py"
```

- [ ] **Step 3: Smoke import**

```bash
pixi run python -c "from scripts.synthesize_questions import main; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add scripts/synthesize_questions.py pixi.toml pixi.lock
git commit -m "feat(synthesize): add main flow with deepseek batch synthesis + sanity filter"
```

---

### Task B5: 跑合成脚本生成 ~60 题

**Files:**
- Create: `data/question_bank.synthetic.json`

- [ ] **Step 1: 运行合成脚本**

```bash
pixi run synthesize-questions
```

Expected output:
```
[S1_motivation] batch 1/2...
[S1_motivation] batch 2/2...
[S2_overview] batch 1/2...
...
Wrote 60 cards to data/question_bank.synthetic.json
```

约 12-15 分钟（DeepSeek 串行调用 12 批；时间窗紧时可降 batch_size 或并行批次）.

- [ ] **Step 2: 验证 JSON 合法 + 卡数 ≥ 50**

```bash
pixi run python -c "
import json
data = json.loads(open('data/question_bank.synthetic.json').read())
print(f'total: {len(data)}, seed: {sum(1 for c in data if c[\"source\"]==\"seed\")}, synthetic: {sum(1 for c in data if c[\"source\"]==\"synthetic\")}')
print(f'reviewed: {sum(1 for c in data if c.get(\"reviewed\"))}')
"
```

Expected: `total: ~60, seed: 12, synthetic: ~48, reviewed: 12`（仅 seed 自动 reviewed=true）.

- [ ] **Step 3: 注意：不要 commit `data/question_bank.synthetic.json` 进 git**

题库内容是 LLM 合成 + 人工抽检后的中间产物。考虑到：
- 文件大（可能 100KB+）
- 内容会随 review 调整
- 可重新生成（但会浪费 token）

**决策**：暂时 commit（便于评委 GitHub 上看到完整题库）。如需排除，将 `data/question_bank.synthetic.json` 加入 `.gitignore`。

本 plan 默认 commit。

- [ ] **Step 4: Commit**

```bash
git add data/question_bank.synthetic.json
git commit -m "data(question-bank): synthesize ~60 cards via deepseek (reviewed=false pending)"
```

---

### Task B6: 人工抽检 ≥ 18 题，标 reviewed=true

**Files:**
- Modify: `data/question_bank.synthetic.json`

按 [Spec B §5.2 抽检 checklist](../specs/B-question-bank.md#52-人工抽检-checklist) 走。

- [ ] **Step 1: 列出待抽检卡片（按 state 分组取前 3）**

```bash
pixi run python -c "
import json
from collections import defaultdict
data = json.loads(open('data/question_bank.synthetic.json').read())
groups = defaultdict(list)
for c in data:
    if c.get('source') == 'synthetic' and not c.get('reviewed'):
        groups[c['related_state']].append(c)
for st, cards in groups.items():
    print(f'\\n=== {st} ({len(cards)} cards) ===')
    for c in cards[:3]:
        print(f'  [{c[\"id\"]}] {c[\"question\"][:60]}...')
"
```

- [ ] **Step 2: 对每张待 review 的卡，回答 6 个问题**

打开 `data/question_bank.synthetic.json` 在编辑器里。对前 18 张（每 state 至少 3 张）回答：

- 这道题是否在追问**项目具体细节**（vs 泛泛八股）？
- followups 是否能继续追问（vs 重复主问题）？
- good_answer_points 是否具体可验证？
- red_flags 是否能识别真实空泛回答？
- applies_to 标注是否合理？
- related_slots 是否对得上 [Spec A §5.1](../specs/A-backend-agents.md#51-状态机定义) 的 slot 名（如 baseline / personal_contribution / failure_case 等）？

**通过** → `"reviewed": true`；**不通过** → 删除该对象。

- [ ] **Step 3: 验证 reviewed 卡数 ≥ 30（12 seed + ≥18 抽检）**

```bash
pixi run python -c "
import json
data = json.loads(open('data/question_bank.synthetic.json').read())
print(f'reviewed: {sum(1 for c in data if c.get(\"reviewed\"))}')
"
```

Expected: ≥ 30.

- [ ] **Step 4: 验证 QuestionBank 能从 synthetic 加载**

```bash
pixi run python -c "
from services.question_bank import QuestionBank
b = QuestionBank()  # 默认走 synthetic
print('loaded reviewed cards count:', len(b._cards))
"
```

Expected: 与 Step 3 一致.

- [ ] **Step 5: Commit**

```bash
git add data/question_bank.synthetic.json
git commit -m "data(question-bank): manually review first 18+ synthetic cards (reviewed=true)"
```

---

## Self-review

**Spec coverage**：
- §1 模块边界 ✓ 文件路径在 B1/B2/B3
- §2 QuestionCard schema ✓（在 Plan1A A2 已含；本 plan B1/B2 验证使用）
- §3 12 seed questions ✓ B1
- §4 合成脚本 ✓ B3 (sanity) + B4 (main)
- §5 抽检流程 ✓ B3 (auto banned-pattern) + B6 (manual)
- §6 运行时查询 API ✓ B2（含 HUNHE 修正、tag overlap 排序、exclude_ids）
- §7 错误兜底 ✓ B2 (QuestionBankError) + B4 (合成失败 fallback 空批次)
- §8 实施顺序 ✓ B1→B2→B3→B4→B5→B6

**Placeholder scan**：无 TBD / TODO；每步骤含具体命令或代码。

**Type consistency**：
- `QuestionCard` 字段在 B1/B2/B3/B4/B6 一致（id/category/tags/applies_to/related_state/trigger/question/followups/good_answer_points/red_flags/related_slots/difficulty/source/generated_at/reviewed）
- `QuestionBank.query` 签名在 B2 与 Plan1A A10/A11 对齐
- `_CardDraft` 在 B4 严格是 `QuestionCard` 减去 `id/source/generated_at/reviewed`，合成后由脚本补充

**实施依赖外部**：
- Plan1A Task A2 必须先于 B1（schemas.QuestionCard 等）
- Plan1A Task A5 必须先于 B4（call_deepseek）
- Plan1A Task A10 在 B2 完成前可用 stub QuestionBank（A10 已说明）
