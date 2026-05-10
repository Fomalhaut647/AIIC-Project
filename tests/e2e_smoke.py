"""Demo e2e smoke — drives the full ProjectProbe path through the API.

Not part of the test suite (LLM hits cost tokens; pytest skips files without
a `test_` prefix). Used by C11 to validate the demo path before declaring
Plan1C complete.

Usage:
    PORT=8765 pixi run uvicorn server.main:app --host 127.0.0.1 --port 8765 &
    PORT=8765 pixi run python tests/e2e_smoke.py

Requires: server running at 127.0.0.1:$PORT (default 8000) with .env loaded.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

PORT = int(os.environ.get("PORT", 8000))
BASE = f"http://127.0.0.1:{PORT}"

DEMO_PROJECT = """我做了一个面向中小企业财务部门的 AI 财务助理，名为 LedgerCraft。它能解析 Excel 报表、PDF 合同、发票图片等多源凭证，自动完成数据清洗、分类对账和报表生成。系统采用"AI 生成公式 + 本地引擎核算"的脱敏架构：AI 只基于表头结构和业务描述生成计算规则（公式串），不接触真实数值；公式串送回本地确定性引擎执行，从而降低数据泄露风险。我个人负责架构设计与公式生成模块的 prompt 工程 / few-shot 优化，并设计了一套样例数据来测试公式生成的正确性。系统目前部署在 3 家试点公司，平均每月处理约 5000 张凭证。"""

DEMO_USER_MODEL = {
    "id": "demo-user",
    "goal": "求职 AI 算法实习",
    "target": "求职",
    "target_program": "字节跳动 AI Lab 算法实习",
    "preferred_style": "直接",
    "current_stage": "普通项目面",
    "projects": [],
    "strengths": [],
    "recurring_weaknesses": [],
    "resume_issues": [],
}


def step(name):
    print(f"\n{'='*60}\n{name}\n{'='*60}")


def main():
    timeout = httpx.Timeout(120.0)
    with httpx.Client(base_url=BASE, timeout=timeout) as c:
        step("1. healthz")
        r = c.get("/api/healthz").json()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        assert r["status"] == "ok"

        step("2. /api/profile/parse")
        t0 = time.time()
        parsed = c.post("/api/profile/parse",
                        json={"raw_project_text": DEMO_PROJECT}).json()
        print(f"  ({time.time()-t0:.1f}s)")
        print(f"  summary head: {parsed['project_summary'][:60]}…")
        print(f"  keywords: {parsed['technical_keywords'][:3]}")
        assert parsed["project_summary"]

        step("3. /api/coach/plan")
        t0 = time.time()
        plan = c.post("/api/coach/plan", json={
            "user_model": DEMO_USER_MODEL,
            "project_summary": parsed["project_summary"],
        }).json()
        print(f"  ({time.time()-t0:.1f}s)")
        print(f"  recommended: {plan['training_plan']['recommended_next_step']}")
        print(f"  focus_slots: {plan['interview_packet']['focus_slots']}")
        packet = plan["interview_packet"]

        step("4. /api/interviewer/start")
        t0 = time.time()
        start = c.post("/api/interviewer/start", json={
            "interview_packet": packet,
            "user_model": DEMO_USER_MODEL,
        }).json()
        print(f"  ({time.time()-t0:.1f}s)")
        sid = start["session_id"]
        print(f"  session_id: {sid}")
        print(f"  state:      {start['state']}")
        print(f"  question:   {start['question'][:120]}…")
        os_ = start["interviewer_os"]
        print(f"  os.risk_level: {os_['risk_level']}")
        print(f"  os.hidden_concern: {os_['hidden_concern'][:80]}…")
        assert start["question"]
        assert "hidden_concern" in os_

        step("5. /api/interviewer/next — DELIBERATELY VAGUE answer")
        t0 = time.time()
        vague = c.post("/api/interviewer/next", json={
            "session_id": sid,
            "answer": "这个项目挺有意义的，做得还行。",  # purposely empty content
        }).json()
        print(f"  ({time.time()-t0:.1f}s)")
        turn = vague["turn"]
        print(f"  score:          {turn['score']}")
        print(f"  missing_slots:  {turn['missing_slots']}")
        print(f"  feedback:       {turn['feedback'][:120]}…")
        print(f"  next_question:  {turn['next_question'][:120]}…")
        print(f"  next_state:     {vague['next_state']}")
        print(f"  should_continue:{vague['should_continue']}")
        # WoW MOMENT: vague answer must produce missing_slots
        assert turn["missing_slots"], "vague answer should yield missing_slots"
        assert turn["score"] < 60, f"vague answer should score <60, got {turn['score']}"

        step("6. /api/interviewer/next — REAL answer")
        t0 = time.time()
        real = c.post("/api/interviewer/next", json={
            "session_id": sid,
            "answer": (
                "我们用了一个简单 baseline 做对照：用纯规则引擎（无 LLM）按"
                "财务科目硬编码计算规则。对比结果：LLM 公式生成在结构灵活度上明显胜出"
                "（baseline 覆盖率 32% vs ours 87%），但准确率持平 (~95%)。"
                "我们构造了 200 条样例，包括跨币种、税种异常、跨年度合并等 5 类边界 case，"
                "其中跨币种这一类 baseline 完全无法处理，我们额外加了 currency-context "
                "few-shot 样例提示，使准确率从 60% 提升到 92%。"
            ),
        }).json()
        print(f"  ({time.time()-t0:.1f}s)")
        turn = real["turn"]
        print(f"  score:          {turn['score']}")
        print(f"  missing_slots:  {turn['missing_slots']}")
        print(f"  feedback:       {turn['feedback'][:120]}…")
        print(f"  next_state:     {real['next_state']}")

        step("7. /api/coach/review")
        t0 = time.time()
        report = c.post("/api/coach/review", json={"session_id": sid}).json()
        print(f"  ({time.time()-t0:.1f}s)")
        print(f"  overall_score: {report['overall_score']}")
        print(f"  summary head:  {report['summary'][:120]}…")
        print(f"  strengths:     {report.get('strengths', [])[:2]}")
        print(f"  weaknesses:    {report.get('weaknesses', [])[:2]}")
        print(f"  evidence n:    {len(report['evidence'])}")
        print(f"  dangerous_qs:  {len(report['dangerous_questions'])}")
        print(f"  resume orig:   {report['resume_rewrite']['original'][:60]}…")
        print(f"  resume new :   {report['resume_rewrite']['rewritten'][:60]}…")
        print(f"  next plan:     {report['next_training_plan']['recommended_next_step']}")
        print(f"  humor title:   {report['humor_card']['title']}")
        print(f"  humor head:    {report['humor_card']['content'][:80]}…")
        for required in ["overall_score", "summary", "evidence",
                         "dangerous_questions", "resume_rewrite",
                         "next_training_plan", "humor_card"]:
            assert required in report, f"missing report.{required}"

        print("\n" + "="*60)
        print("ALL E2E STEPS PASSED")
        print("="*60)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n!! ASSERTION FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n!! ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
