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


def test_whitespace_only_question_rejected():
    # LLM 合成偶尔输出 "  \n  " 类白板 question；截留掉
    c = _base_card()
    c["question"] = "  \n  "
    assert is_card_valid(c) is False
