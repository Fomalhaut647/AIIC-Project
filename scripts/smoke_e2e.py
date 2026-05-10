"""一次性 e2e smoke：onboard → plan → start → next ×3 → review。

跑法（任一）：
  pixi run python scripts/smoke_e2e.py        # 直接跑
  PYTHONPATH=. pixi run python scripts/smoke_e2e.py
"""
import asyncio
import sys
from pathlib import Path

# 让脚本无论从哪儿启动都能找到 services/
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from services.coach import onboard, plan, review
from services.interviewer import start, next_turn
from services.store import SessionStore
from services.question_bank import QuestionBank


async def main():
    store = SessionStore()
    bank = QuestionBank()

    # onboard
    o = await onboard("我准备保研人工智能创新中心，项目是 AI 财会助理")
    print("onboard need_more_info:", o.need_more_info)
    if o.need_more_info:
        o = await onboard(
            "target=保研，program=人工智能创新中心，最怕被问 baseline",
            history=[
                {"role": "user", "content": "我准备保研..."},
                {"role": "assistant", "content": str(o.followup_questions)},
            ],
        )
    user_model = o.user_model
    if user_model is None:
        print("⚠ onboarding fallback path; using minimal user_model")
        from services.schemas import UserModel, Target
        user_model = UserModel(id="u1", goal="保研", target=Target.BAOYAN)

    # plan
    p = await plan(user_model, "AI 财会助理：解析 Excel 自动算公式")
    print("plan focus_slots:", p.interview_packet.focus_slots)

    # interview
    sid, t = await start(p.interview_packet, user_model, bank, store)
    print("Q1:", t.question[:80])
    answers = [
        "我们做了用户访谈，痛点确实存在",
        "用 GPT-4 + 规则引擎，输入是 Excel，输出是公式",
        "我们用样例数据测，结果符合预期",
    ]
    for a in answers:
        nt, cont, st = await next_turn(sid, a, bank, store)
        print(f"  state={st.value} score={nt.score} miss={nt.missing_slots}")
        if not cont:
            break

    # review
    session = store.get(sid)
    rep = await review(user_model, p.interview_packet, session.turns)
    print("Report score:", rep.overall_score)
    print("Resume rewrite preview:", rep.resume_rewrite.rewritten[:100])
    print("Humor card:", rep.humor_card.title, "—", rep.humor_card.content[:80])


asyncio.run(main())
