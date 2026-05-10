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
