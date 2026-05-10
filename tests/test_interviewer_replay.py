"""Interviewer replay-mode tests — Spec D §7.2 / §7.3 / §7.6."""
import pytest

from services.interviewer import (
    build_replay_packet,
    should_advance_state,
    should_continue_replay,
)
from services.prompts import INTERVIEWER_REPLAY_PROMPT_INJECT
from services.schemas import (
    InterviewPacket,
    InterviewStage,
    InterviewTurn,
    Target,
)


def _packet(focus_slots: list[str] = None) -> InterviewPacket:
    return InterviewPacket(
        target=Target.BAOYAN,
        interviewer_style="strict",
        project_summary="P",
        focus_slots=focus_slots or ["baseline"],
    )


def _turn(covered: list[str]) -> InterviewTurn:
    return InterviewTurn(
        id="t", session_id="s",
        state=InterviewStage.S4_VALIDATION,
        question="q", answer="a",
        score=0,
        covered_slots=covered, missing_slots=[],
        feedback="", next_question="",
        source="project",
        interviewer_os={
            "hidden_concern": "", "why_this_question": "",
            "missing_slots": [], "what_i_want_to_hear": [],
            "risk_level": "低",
        },
    )


def test_build_replay_packet_preserves_parent_fields():
    parent = _packet(focus_slots=["baseline", "评估"])
    parent.interviewer_style = "strict-research"

    replay = build_replay_packet(
        parent_packet=parent,
        focus_slots=["baseline"],
        parent_session_id="parent-1",
    )

    assert replay.replay_mode is True
    assert replay.replay_focus_slots == ["baseline"]
    assert replay.parent_session_id == "parent-1"
    # 其它字段保留
    assert replay.target == parent.target
    assert replay.interviewer_style == "strict-research"
    assert replay.focus_slots == ["baseline", "评估"]


def test_replay_prompt_inject_renders_focus_slots():
    txt = INTERVIEWER_REPLAY_PROMPT_INJECT.format(
        replay_focus_slots="baseline, 评估",
        state="S4_validation",
    )
    assert "baseline" in txt
    assert "S4_validation" in txt
    assert "重练模式" in txt


def test_should_advance_state_blocked_in_replay():
    """replay_mode=True 时状态机不前进."""
    pkt = _packet()
    pkt.replay_mode = True
    pkt.replay_focus_slots = ["baseline"]

    turn = _turn(covered=["项目动机", "目标用户"])
    assert should_advance_state(packet=pkt, latest_turn=turn) is False


def test_should_advance_state_returns_true_for_normal_packet():
    """非 replay 模式 packet → 不该被该 helper 阻止 (返回 True)."""
    pkt = _packet()  # replay_mode=False default
    turn = _turn(covered=[])
    assert should_advance_state(packet=pkt, latest_turn=turn) is True


def test_should_continue_replay_until_focus_covered():
    """covered ⊇ focus → 终止；否则继续."""
    focus = ["baseline", "评估"]
    assert should_continue_replay(turns=[_turn(["baseline"])], focus_slots=focus) is True
    assert should_continue_replay(
        turns=[_turn(["baseline", "评估"])], focus_slots=focus,
    ) is False


def test_should_continue_replay_8_turn_hard_cap():
    """超过 8 轮强制终止 (Spec D §7.6)."""
    turns = [_turn(["unrelated"])] * 9
    assert should_continue_replay(turns=turns, focus_slots=["baseline"]) is False


def test_should_continue_replay_canonicalizes_slots():
    """slot 大小写/空白不一致也应触发覆盖判定."""
    focus = ["Baseline"]
    assert should_continue_replay(turns=[_turn([" baseline "])], focus_slots=focus) is False
