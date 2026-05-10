"""离线合成题库脚本。一次性运行，结果落 data/question_bank.synthetic.json。"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# 让脚本无论从哪儿启动都能找到 services/（同 scripts/smoke_e2e.py 模式）
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from pydantic import BaseModel, Field

from services.interviewer import REQUIRED_SLOTS
from services.llm import call_deepseek
from services.schemas import InterviewStage, RiskLevel, Target


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
    # whitespace-only question slips past truthy check; reject explicitly
    # (LLM 合成偶尔输出 "  \n  " 这类白板 question)
    if not card["question"].strip():
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
5. 每题标注 related_slots（**只能从下面 slot 列表里选** — 用于和 InterviewerOS.missing_slots
   做名字对齐；自由发明的 slot 名会脱离系统语义）：{slot_list}
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
            slot_list=REQUIRED_SLOTS.get(state, []),
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
