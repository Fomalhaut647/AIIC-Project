"""Stub for services.question_bank — Plan1B Task B2 will replace with real impl.

Maintained at bootstrap to avoid race between impl-A (interviewer.start needs
import) and impl-B (real implementation). impl-A's Plan1A Task A10 should
detect this stub and skip recreating it.
"""
from __future__ import annotations

from services.schemas import (  # type: ignore[import-not-found]  # schemas added by impl-A Task A2
    InterviewStage,
    QuestionCard,
    Target,
)


class QuestionBankError(Exception):
    pass


class QuestionBank:
    """Stub. Always returns None from query. impl-B replaces in Plan1B Task B2."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN
        pass

    def query(
        self,
        target: Target,
        state: InterviewStage,
        project_tags: list[str] | None = None,
        exclude_ids: list[str] | None = None,
    ) -> QuestionCard | None:
        return None
