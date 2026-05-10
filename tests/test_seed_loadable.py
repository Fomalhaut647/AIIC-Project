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
