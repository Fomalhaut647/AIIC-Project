from services.schemas import (
    InterviewStage, InterviewSession, InterviewTurn, InterviewerOS,
    InterviewPacket, UserModel, Target, RiskLevel, QuestionSource,
)
from services.interviewer import (
    REQUIRED_SLOTS, should_advance, is_vague, update_vague_counter,
    SLOT_COVERAGE_THRESHOLD, VAGUE_SCORE_THRESHOLD, VAGUE_DEGRADE_COUNT,
)


def _mk_session(state=InterviewStage.S1_MOTIVATION):
    return InterviewSession(
        session_id="s",
        user_model=UserModel(id="u", goal="g", target=Target.BAOYAN),
        packet=InterviewPacket(
            target=Target.BAOYAN, interviewer_style="x",
            project_summary="p", focus_slots=[],
        ),
        state=state,
    )


def _mk_turn(state, covered, score=80, missing=None):
    return InterviewTurn(
        id="t", session_id="s", state=state,
        question="q", answer="a", score=score,
        covered_slots=covered, missing_slots=missing or [],
        feedback="f", next_question="nq", source=QuestionSource.PROJECT,
        interviewer_os=InterviewerOS(
            hidden_concern="x", why_this_question="y",
            missing_slots=[], what_i_want_to_hear=[],
            risk_level=RiskLevel.LOW,
        ),
    )


def test_required_slots_has_all_six_states():
    for state in InterviewStage:
        if state == InterviewStage.DONE:
            continue
        assert state in REQUIRED_SLOTS
        assert len(REQUIRED_SLOTS[state]) >= 4


def test_should_advance_when_coverage_high():
    session = _mk_session()
    session.turns = [
        _mk_turn(InterviewStage.S1_MOTIVATION,
                 covered=REQUIRED_SLOTS[InterviewStage.S1_MOTIVATION][:4])
    ]
    # 4 / 5 = 0.8 → 满足 threshold
    assert should_advance(session, session.turns[-1]) is True


def test_should_not_advance_when_coverage_low():
    session = _mk_session()
    session.turns = [
        _mk_turn(InterviewStage.S1_MOTIVATION, covered=["why_do"])
    ]
    # 1 / 5 = 0.2 → 不够
    assert should_advance(session, session.turns[-1]) is False


def test_is_vague_below_threshold():
    turn = _mk_turn(InterviewStage.S1_MOTIVATION, covered=[], score=30)
    assert is_vague(turn) is True
    turn2 = _mk_turn(InterviewStage.S1_MOTIVATION, covered=[], score=60)
    assert is_vague(turn2) is False


def test_should_advance_counts_latest_turn_not_yet_appended():
    """Reviewer #1 fix: should_advance must count latest_turn.covered_slots
    even when latest_turn hasn't been appended to session.turns yet —
    matches production call order in next_turn (advance is decided BEFORE
    append_turn). Without this fix, coverage lags by one turn and a single
    fully-covering answer cannot trigger advance on its own turn."""
    session = _mk_session()
    # session.turns is empty — production call order: next_turn calls
    # should_advance with the brand-new turn before persisting it.
    latest = _mk_turn(
        InterviewStage.S1_MOTIVATION,
        covered=REQUIRED_SLOTS[InterviewStage.S1_MOTIVATION][:4],
    )
    # 4 / 5 = 0.8 → 满足 threshold；但 turn 还没在 session.turns 里
    assert should_advance(session, latest) is True


def test_should_advance_combines_prior_turns_and_latest_turn():
    """Latest turn covers some slots, prior turns cover others; union must hit threshold."""
    session = _mk_session()
    session.turns = [
        _mk_turn(InterviewStage.S1_MOTIVATION, covered=["why_do", "target_user"])
    ]
    latest = _mk_turn(
        InterviewStage.S1_MOTIVATION,
        covered=["pain_real", "timing"],  # 两个新 slot
    )
    # union = 4 / 5 = 0.8 → 满足
    assert should_advance(session, latest) is True


def test_vague_counter_increments_and_resets():
    session = _mk_session()
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, [], score=20))
    assert session.consecutive_vague_count == 1
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, [], score=20))
    assert session.consecutive_vague_count == 2
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, ["x"], score=80))
    assert session.consecutive_vague_count == 0
