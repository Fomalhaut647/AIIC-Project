"""Markdown export tests — Spec D §9."""
from datetime import datetime

import pytest

from services.export import render_markdown


def _full_session() -> dict:
    """构造一个 reviewed session 的最小 dict（覆盖 8 段需要的字段）。"""
    return {
        "session_id": "abcdef123456",
        "created_at": "2026-05-12T18:30:00",
        "finished_at": "2026-05-12T19:15:00",
        "user_id": "anon",
        "packet": {
            "target": "保研",
            "project_summary": "财会 Agent 项目：AI 生成公式 + 本地引擎核算...",
        },
        "turns": [
            {
                "id": "t1", "state": "S1_motivation",
                "question": "为什么做这个？",
                "answer": "用户说账难对",
                "covered_slots": ["项目动机"],
                "missing_slots": ["痛点真实性"],
                "feedback": "动机讲了但缺痛点验证。",
                "interviewer_os": {
                    "hidden_concern": "可能没真实验证过痛点",
                    "why_this_question": "动机是项目立项基石",
                    "missing_slots": ["痛点真实性"],
                    "what_i_want_to_hear": ["访谈过 N 个用户的具体反馈"],
                    "risk_level": "高",
                },
            },
        ],
        "evaluation_report": {
            "overall_score": 68,
            "summary": "整体讲清了愿景但缺验证。",
            "strengths": ["架构设计清晰"],
            "weaknesses": ["baseline", "错误分析"],
            "evidence": ["S2 个人贡献讲得最具体"],
            "dangerous_questions": ["如何证明你的方案比一个简单 baseline 好？"],
            "resume_rewrite": {
                "original": "我做了一个 AI 财务助理...",
                "rewritten": "我设计并实现了一个面向中小企业的 AI 财务助理...",
                "missing_evidence": ["baseline 对比", "异常 case 覆盖率"],
                "revision_history": [
                    {
                        "iteration_index": 1,
                        "timestamp": "2026-05-12T19:30:00",
                        "user_text": "改后版本 1",
                        "coach_feedback": "baseline 部分讲清了。",
                        "newly_covered": ["baseline 对比"],
                        "still_missing": ["异常 case 覆盖率"],
                        "is_good_enough": False,
                    },
                ],
            },
            "next_training_plan": "下一轮重练：补 baseline 对比 + 错误分析 case。",
            "humor_card": {
                "title": "高价值 Bug：未做 baseline",
                "content": "你的项目是个 99% complete 的 PR，缺的是 baseline 这个 1%。",
            },
        },
    }


def test_render_markdown_has_8_sections():
    md = render_markdown(_full_session())
    for i in range(1, 9):
        assert f"## {i}." in md, f"missing section {i}"


def test_render_markdown_includes_interviewer_os():
    """作弊模式 OS 默认带上（Spec D §9.3 模板）。"""
    md = render_markdown(_full_session())
    assert "面试官 OS" in md or "interviewer_os" in md or "hidden_concern" in md
    assert "可能没真实验证过痛点" in md
    assert "高" in md  # risk_level


def test_render_markdown_includes_revision_history():
    md = render_markdown(_full_session())
    assert "改后版本 1" in md
    assert "baseline 部分讲清了" in md


def test_render_markdown_utf8_chinese_roundtrip():
    """中文字符不转义。"""
    md = render_markdown(_full_session())
    assert "财会 Agent" in md
    assert "面试" in md or "训练" in md or "复盘" in md


def test_render_markdown_uses_details_fold_for_dialog():
    md = render_markdown(_full_session())
    assert "<details>" in md
    assert "</details>" in md


def test_render_markdown_empty_revision_history_omits_section():
    """没有 revision_history 时不应出现空的 #### 历次迭代 标题。"""
    session = _full_session()
    session["evaluation_report"]["resume_rewrite"]["revision_history"] = []
    md = render_markdown(session)
    # 仍有第 5 段（简历改写主体）
    assert "## 5." in md
    # 不应出现 "历次迭代" subsection（之前 assertion 用 OR 总是真，等于没断言）
    assert "历次迭代" not in md


def test_render_markdown_neutralizes_details_close_in_user_answer():
    """防 markdown injection: 用户回答含 `</details>` literal 不应过早闭合 sec 8 折叠块。"""
    session = _full_session()
    session["turns"][0]["answer"] = "我答完了 </details> 然后继续编"
    md = render_markdown(session)
    # 整段 sec 8 仍应保有完整折叠：恰好一对 <details>...</details>
    assert md.count("<details>") == 1
    assert md.count("</details>") == 1
    # 用户原内容仍应可读（zero-width 不影响阅读）
    assert "继续编" in md


def test_render_markdown_evidence_as_dict_renders_readable():
    """实际生产 EvaluationReport.evidence 是 Evidence dict (quote/problem/suggestion)；
    渲染应能识别 dict 形式而不是 Python repr。"""
    session = _full_session()
    session["evaluation_report"]["evidence"] = [
        {"quote": "我用 zero-shot 作 baseline",
         "problem": "未给出对比指标",
         "suggestion": "补一个 random / few-shot baseline 对比"},
    ]
    md = render_markdown(session)
    assert "我用 zero-shot 作 baseline" in md
    assert "未给出对比指标" in md
    assert "补一个 random" in md
    # 不应是 Python dict repr
    assert "{'quote'" not in md
