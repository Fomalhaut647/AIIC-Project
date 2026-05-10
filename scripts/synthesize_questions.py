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
