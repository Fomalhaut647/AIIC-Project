"""Markdown export for ProjectProbe replay reports — Spec D §9."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _neutralize_details_close(s: str) -> str:
    """防 markdown injection: 用户内容含 `</details>` / `</summary>` 会过早闭合 sec 8 折叠块。
    这里把闭合标签转义成 zero-width-prefixed 形式，渲染时仍可读但不再触发 HTML parser。"""
    return (
        s.replace("</details>", "<​/details>")
         .replace("</summary>", "<​/summary>")
    )


def _format_bullet_item(item: Any) -> str:
    """通用 bullet item 渲染. Evidence dict (quote/problem/suggestion) 友好展开;
    其它 dict 走 JSON 单行兜底; 字符串 / 数字 / None 等走 str()."""
    if isinstance(item, dict) and {"quote", "problem", "suggestion"} <= set(item.keys()):
        return (
            f"> {item.get('quote', '')}\n"
            f"  - 问题：{item.get('problem', '')}\n"
            f"  - 建议：{item.get('suggestion', '')}"
        )
    if isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _bullet_list(items: list[Any], empty_text: str = "（无）") -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {_format_bullet_item(item)}" for item in items)


def _format_dialog(turns: list[dict[str, Any]]) -> str:
    """渲染所有 turn 到一段折叠的 details 块（Spec D §9.3）."""
    parts: list[str] = []
    for i, t in enumerate(turns, start=1):
        os_ = t.get("interviewer_os") or {}
        # 只对会进 <details> 的字段做闭合标签转义；其它结构标签字面来自代码不会触发 injection。
        question = _neutralize_details_close(str(t.get("question", "")))
        answer = _neutralize_details_close(str(t.get("answer", "")))
        feedback = _neutralize_details_close(str(t.get("feedback", "（无）")))
        hidden = _neutralize_details_close(str(os_.get("hidden_concern", "")))
        why = _neutralize_details_close(str(os_.get("why_this_question", "")))
        parts.append(
            f"### 第 {i} 轮 · {t.get('state', '未知')}\n"
            f"**问题**：{question}\n\n"
            f"**回答**：{answer}\n\n"
            f"**反馈**：{feedback}\n\n"
            f"**面试官 OS（作弊模式）**：\n"
            f"- hidden_concern: {hidden}\n"
            f"- why_this_question: {why}\n"
            f"- missing_slots: {', '.join(os_.get('missing_slots', []) or []) or '（无）'}\n"
            f"- what_i_want_to_hear: {', '.join(os_.get('what_i_want_to_hear', []) or []) or '（无）'}\n"
            f"- risk_level: {os_.get('risk_level', '未标注')}"
        )
    body = "\n\n---\n\n".join(parts) if parts else "（无对话记录）"
    return (
        f"<details><summary>展开全部 {len(turns)} 轮（含面试官 OS）</summary>\n\n"
        f"{body}\n\n</details>"
    )


def _format_revision_history(revs: list[dict[str, Any]]) -> str:
    if not revs:
        return ""
    parts: list[str] = ["#### 历次迭代"]
    for r in revs:
        parts.append(
            f"\n**第 {r.get('iteration_index', '?')} 轮** · {r.get('timestamp', '')}\n\n"
            f"用户提交：\n```\n{r.get('user_text', '')}\n```\n\n"
            f"Coach 反馈：{r.get('coach_feedback', '')}\n\n"
            f"新覆盖：{', '.join(r.get('newly_covered', []) or []) or '（无）'}\n\n"
            f"仍差：{', '.join(r.get('still_missing', []) or []) or '（无）'}\n"
        )
    return "\n".join(parts)


def render_markdown(session: dict[str, Any]) -> str:
    """Spec D §9.3 — 8 段固定模板。"""
    pkt = session.get("packet", {})
    report = session.get("evaluation_report", {})
    rr = report.get("resume_rewrite", {})
    humor = report.get("humor_card", {})

    sec1 = (
        f"## 1. Session 元数据\n\n"
        f"- 训练目标：{pkt.get('target', '未设置')}\n"
        f"- 项目：{pkt.get('project_summary', '')[:200]}\n"
        f"- 训练时间：{session.get('created_at', '')} → {session.get('finished_at', '')}\n"
        f"- 总分：{report.get('overall_score', '—')} / 100\n"
    )

    sec2 = (
        f"## 2. 总体评估\n\n"
        f"{report.get('summary', '（无总结）')}\n\n"
        f"**优势**\n\n{_bullet_list(report.get('strengths', []) or [])}\n\n"
        f"**弱点**\n\n{_bullet_list(report.get('weaknesses', []) or [])}\n"
    )

    sec3 = f"## 3. 关键证据\n\n{_bullet_list(report.get('evidence', []) or [])}\n"

    sec4 = f"## 4. 最危险追问\n\n{_bullet_list(report.get('dangerous_questions', []) or [])}\n"

    sec5_main = (
        f"## 5. 简历改写\n\n"
        f"### 原始版本\n\n```\n{rr.get('original', '')}\n```\n\n"
        f"### Coach 改写版本\n\n```\n{rr.get('rewritten', '')}\n```\n\n"
        f"### 还差的证据\n\n{_bullet_list(rr.get('missing_evidence', []) or [])}\n"
    )
    revision_block = _format_revision_history(rr.get("revision_history", []) or [])
    sec5 = sec5_main + ("\n" + revision_block if revision_block else "")

    sec6 = f"## 6. 下一轮训练计划\n\n{report.get('next_training_plan', '（无）')}\n"

    sec7 = (
        f"## 7. 幽默卡片\n\n"
        f"**{humor.get('title', '（无标题）')}**\n\n"
        f"{humor.get('content', '（无内容）')}\n"
    )

    sec8 = f"## 8. 完整对话日志\n\n{_format_dialog(session.get('turns', []) or [])}\n"

    header = (
        f"# ProjectProbe 复盘报告\n\n"
        f"> 生成时间：{datetime.now().isoformat(timespec='seconds')}\n"
        f"> Session ID：{session.get('session_id', '')}\n\n"
    )

    return header + "\n".join([sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8])
