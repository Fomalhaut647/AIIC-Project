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
