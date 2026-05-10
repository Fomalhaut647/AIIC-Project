"use strict";

/* ProjectProbe v2 — single-page app driver.
   Spec C §5 (state machine) + §6 (5 views).

   No framework. Single global `state` object; views toggled via
   `.hidden` on `<section class="view">`. All API calls go through
   postJson() which surfaces structured error messages from FastAPI's
   HTTPException.detail. */

// ---------- global state ----------

const state = {
  history: [],            // onboarding 对话 [{role: "user"|"assistant", content}]
  user_model: null,
  packet: null,
  project_summary: null,
  session_id: null,
  current_state: null,    // InterviewStage enum string e.g. "S1_motivation"
  current_question: null,
  current_focus_slots: [],
  current_os: null,       // last InterviewerOS (for cheat panel)
  turns: [],              // accumulated InterviewTurn[]
  report: null,
  is_demo: false,
};

// Hard-coded demo project text — financial-AI assistant from overview.md §14.2.
// Used by the "使用示例项目" path so demo can run without users typing.
const DEMO_PROJECT_TEXT = `我做了一个面向中小企业财务部门的 AI 财务助理，
名为 LedgerCraft。它能解析 Excel 报表、PDF 合同、发票图片等多源凭证，自动完成数据清洗、
分类对账和报表生成。

系统采用"AI 生成公式 + 本地引擎核算"的脱敏架构：AI 只基于表头结构和业务描述生成计算
规则（公式串），不接触真实数值；公式串送回本地确定性引擎执行，从而降低数据泄露风险，
同时兼顾 LLM 的语义理解能力和企业的合规底线。

我个人负责架构设计与公式生成模块的 prompt 工程 / few-shot 优化，并设计了一套样例数据
来测试公式生成的正确性。系统目前部署在 3 家试点公司，平均每月处理约 5000 张凭证。`;

const DEMO_USER_MODEL = {
  id: "demo-user",
  goal: "求职 AI 算法实习",
  target: "求职",
  target_program: "字节跳动 AI Lab 算法实习",
  preferred_style: "直接",
  current_stage: "普通项目面",
  projects: [],
  strengths: [],
  recurring_weaknesses: [],
  resume_issues: [],
};

// ---------- Plan2 P11: anonymous user_id (Spec D §3) ----------

const USER_ID = (() => {
  let id = null;
  try {
    id = localStorage.getItem("userId");
  } catch (_) { /* private mode */ }
  if (!id) {
    id = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : `anon-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try { localStorage.setItem("userId", id); } catch (_) {}
  }
  return id;
})();

// ---------- DOM helpers ----------

function $(sel) { return document.querySelector(sel); }
function show(sel) { $(sel).classList.remove("hidden"); }
function hide(sel) { $(sel).classList.add("hidden"); }

// ---------- theme toggle ----------
// Initial data-theme is set by inline script in <head> (avoids FOUC).
// Here we only sync the button icon and wire click → toggle + persist.

function syncThemeIcon() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  $("#btn-theme-toggle").textContent = cur === "dark" ? "☾" : "☀";
}

$("#btn-theme-toggle").addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("theme", next); } catch (_) { /* private mode */ }
  syncThemeIcon();
});

syncThemeIcon();

function switchView(name) {
  // Plan2 P10/P11: profile is the 6th view
  ["home", "onboarding", "material", "interview", "report", "profile"].forEach(v => {
    document.querySelector("#view-" + v).classList.add("hidden");
  });
  document.querySelector("#view-" + name).classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function postJson(url, body) {
  // Plan2 P11: 自动注入 user_id 字段（v2 endpoints 都接受可选 user_id, fallback "anonymous"）。
  // 调用方仍按业务字段传 body, 不需要每次手写 user_id。
  const bodyWithUser = { ...(body || {}), user_id: USER_ID };
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodyWithUser),
  });
  if (!resp.ok) {
    let detail = await resp.text();
    try {
      const parsed = JSON.parse(detail);
      // FastAPI HTTPException.detail can be a string OR an object. Spec C
      // §2.6 returns {error: "session_expired", message: "请重新开始训练"}.
      // Prefer the human-readable .message field; fall back through reasonable
      // shapes; only stringify whole detail as last resort.
      if (typeof parsed.detail === "string") {
        detail = parsed.detail;
      } else if (parsed.detail && typeof parsed.detail.message === "string") {
        detail = parsed.detail.message;
      } else if (parsed.detail) {
        detail = JSON.stringify(parsed.detail);
      } else {
        detail = JSON.stringify(parsed);
      }
    } catch (_) { /* keep raw text */ }
    const err = new Error(`${resp.status}: ${detail}`);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  return resp.json();
}

async function apiGet(url) {
  // Plan2 P11: GET helper, 与 postJson 错误格式一致, 调用方决定 .json() / .text()
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = await resp.text();
    try {
      const parsed = JSON.parse(detail);
      if (typeof parsed.detail === "string") detail = parsed.detail;
      else if (parsed.detail && typeof parsed.detail.message === "string") detail = parsed.detail.message;
      else if (parsed.detail) detail = JSON.stringify(parsed.detail);
      else detail = JSON.stringify(parsed);
    } catch (_) {}
    const err = new Error(`${resp.status}: ${detail}`);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  return resp;  // 调用方决定 .json() / .text() / .blob()
}

// ---------- HOME → ONBOARDING / DEMO ----------

$("#btn-start").addEventListener("click", () => {
  state.history = [];
  state.is_demo = false;
  $("#onboarding-history").innerHTML = "";
  switchView("onboarding");
  appendChat(
    "coach",
    "你好。我是训练组长 Coach。请告诉我：你这次主要是为了准备 \n" +
    "  ① 保研复试，  ② AI 岗位面试，  还是  ③ 都准备？\n" +
    "另外，方便描述一下你想深挖的项目大致是什么方向吗？"
  );
});

$("#btn-demo").addEventListener("click", () => {
  state.is_demo = true;
  state.user_model = { ...DEMO_USER_MODEL };
  $("#material-input").value = DEMO_PROJECT_TEXT;
  switchView("material");
});

$("#btn-onboarding-back").addEventListener("click", () => switchView("home"));
$("#btn-material-back").addEventListener("click", () => switchView("home"));
$("#btn-home").addEventListener("click", () => switchView("home"));

// ---------- Plan2 P11: profile nav + dot ----------

$("#nav-profile").addEventListener("click", async () => {
  switchView("profile");
  await loadProfile();
});

const _btnProfileBack = document.getElementById("btn-profile-back");
if (_btnProfileBack) _btnProfileBack.addEventListener("click", () => switchView("home"));

async function refreshProfileDot() {
  // Show red dot on nav-profile if user has any persisted sessions.
  // Best-effort: silently skip on network / 5xx so home view stays clean.
  try {
    const resp = await apiGet(`/api/users/${encodeURIComponent(USER_ID)}/profile`);
    const profile = await resp.json();
    const dot = document.getElementById("nav-profile-dot");
    if (!dot) return;
    if ((profile.total_sessions || 0) > 0) dot.classList.remove("hidden");
    else dot.classList.add("hidden");
  } catch (e) {
    console.warn("refreshProfileDot failed", e);
  }
}

// stub — full impl in P12
async function loadProfile() {
  const display = document.getElementById("profile-userid-display");
  if (display) display.textContent = USER_ID.slice(0, 8);
  // P12 will fetch + render. For now show empty state so the view isn't blank.
  const empty = document.getElementById("profile-empty");
  const content = document.getElementById("profile-content");
  if (empty) empty.classList.remove("hidden");
  if (content) content.classList.add("hidden");
}

// 启动后立刻探一次
refreshProfileDot();

// ---------- chat helper (used by onboarding wiring in C8) ----------

function appendChat(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  const whoLabel = who === "coach" ? "Coach" : "你";
  // text rendered as plain text via textContent (no HTML injection)
  const whoEl = document.createElement("span");
  whoEl.className = "who";
  whoEl.textContent = whoLabel;
  const bodyEl = document.createElement("div");
  bodyEl.textContent = text;
  div.appendChild(whoEl);
  div.appendChild(bodyEl);
  const hist = $("#onboarding-history");
  hist.appendChild(div);
  hist.scrollTop = hist.scrollHeight;
}

// ---------- xss-safe HTML escape (used by C10 report rendering) ----------

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ============================================================
// ONBOARDING — wires chat to /api/coach/onboard
// ============================================================

$("#btn-onboarding-send").addEventListener("click", sendOnboarding);
$("#onboarding-input").addEventListener("keydown", (e) => {
  // Cmd/Ctrl+Enter sends
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    sendOnboarding();
  }
});

async function sendOnboarding() {
  const input = $("#onboarding-input");
  const msg = input.value.trim();
  if (!msg) return;

  appendChat("user", msg);
  input.value = "";
  state.history.push({ role: "user", content: msg });
  setOnboardingBusy(true, "Coach 正在思考...");

  try {
    const result = await postJson("/api/coach/onboard", {
      user_message: msg,
      // history excludes the message we just pushed (sent as user_message)
      history: state.history.slice(0, -1),
    });

    if (result.need_more_info) {
      const reply = (result.followup_questions || []).join("\n") ||
                    "我还需要再了解一些信息，能再多说两句吗？";
      appendChat("coach", reply);
      state.history.push({ role: "assistant", content: reply });
    } else {
      state.user_model = result.user_model;
      state.packet = result.recommended_packet;
      const target = result.user_model && result.user_model.target;
      const targetLabel = target ? `（target=${target}）` : "";
      appendChat(
        "coach",
        `好。我已经记下你的目标 ${targetLabel}。接下来请把你的项目经历粘贴进来。`,
      );
      // brief pause so user can read the confirmation
      setTimeout(() => switchView("material"), 1200);
    }
  } catch (e) {
    // Demo-video safety: never spit raw HTTP status / network error in the
    // coach bubble — it breaks the "polished assistant" voice on stage.
    // Keep technical detail in console.error for debug (`F12 → Console` still
    // shows the underlying e.message + stack).
    console.error("coach.onboard failed:", e);
    appendChat(
      "coach",
      "（Coach 暂时无法回应，可能是网络或后端波动。请重试上一句话。）",
    );
  } finally {
    setOnboardingBusy(false);
  }
}

function setOnboardingBusy(busy, label) {
  const btn = $("#btn-onboarding-send");
  btn.disabled = busy;
  btn.textContent = busy ? (label || "...") : "发送";
}

// ============================================================
// MATERIAL — parse → plan → start interview
// ============================================================

$("#btn-material-start").addEventListener("click", startInterviewFromMaterial);
$("#material-input").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    startInterviewFromMaterial();
  }
});

async function startInterviewFromMaterial() {
  const text = $("#material-input").value.trim();
  if (text.length < 50) {
    setMaterialHint("请粘贴至少 50 字符的项目经历", "warn");
    return;
  }
  if (!state.user_model) {
    // user reached MATERIAL without onboarding (e.g. direct nav) — fall back
    state.user_model = { ...DEMO_USER_MODEL, id: "fallback-user" };
  }

  setMaterialBusy(true, "Coach 正在解析项目...");
  try {
    const parsed = await postJson("/api/profile/parse", {
      raw_project_text: text,
    });
    state.project_summary = parsed.project_summary;

    setMaterialBusy(true, "Coach 正在制订训练计划...");
    const plan = await postJson("/api/coach/plan", {
      user_model: state.user_model,
      project_summary: parsed.project_summary,
    });
    state.packet = plan.interview_packet;

    setMaterialBusy(true, "Interviewer 正在准备第一问...");
    // Spec C §8.2: demo path appends ?demo=1 so server returns the
    // hardcoded high-quality S1 question instead of risking an LLM抽风
    // in the first 30s of the demo video. Subsequent /next calls are
    // unaffected (still real LLM).
    const startUrl = state.is_demo
      ? "/api/interviewer/start?demo=1"
      : "/api/interviewer/start";
    const start = await postJson(startUrl, {
      interview_packet: state.packet,
      user_model: state.user_model,
    });
    state.session_id = start.session_id;
    state.current_state = start.state;
    state.current_question = start.question;
    state.current_focus_slots = start.focus_slots || [];
    state.current_os = start.interviewer_os;
    state.turns = [];

    renderInterviewView();
    switchView("interview");
  } catch (e) {
    console.error("material → start chain failed:", e);
    setMaterialHint(
      "Coach 暂时无法开始这场训练，请稍后重试或缩短项目原文。",
      "warn",
    );
  } finally {
    setMaterialBusy(false);
  }
}

function setMaterialBusy(busy, label) {
  const btn = $("#btn-material-start");
  btn.disabled = busy;
  btn.textContent = busy ? (label || "处理中...") : "开始面试";
  if (busy && label) setMaterialHint(label, "info");
}

function setMaterialHint(text, kind /* 'info' | 'warn' */) {
  const el = $("#material-hint");
  el.textContent = text;
  el.style.color = kind === "warn" ? "var(--warn)" : "var(--text-2)";
}

function renderInterviewView() {
  const stageMap = {
    "S1_motivation":  "S1 项目动机",
    "S2_overview":    "S2 项目概述",
    "S3_technical":   "S3 技术深挖",
    "S4_validation":  "S4 实验验证",
    "S5_reflection":  "S5 失败反思",
    "S6_matching":    "S6 匹配与总结",
    "done":           "面试结束",
  };
  $("#interview-stage").textContent =
    stageMap[state.current_state] || state.current_state || "—";
  $("#interview-focus").textContent =
    (state.current_focus_slots || []).join(" / ") || "—";
  $("#interview-question").textContent = state.current_question || "";
  $("#interview-input").value = "";
  hide("#interview-feedback");
  if (state.current_os) {
    show("#btn-cheat-toggle");
    renderCheatPanel(state.current_os);
    show("#cheat-panel");
    $("#btn-cheat-toggle").textContent = "▼ 收起作弊模式";
  } else {
    hide("#btn-cheat-toggle");
    hide("#cheat-panel");
  }
  // ensure submit button visible / finish hidden at the start of each turn
  show("#btn-interview-submit");
  hide("#btn-finish");
  $("#btn-interview-submit").disabled = false;
  $("#btn-interview-submit").textContent = "提交回答";
  renderTranscript();
}

// ============================================================
// INTERVIEW multi-turn — submit answer → next turn
// ============================================================

$("#btn-interview-submit").addEventListener("click", submitAnswer);
$("#interview-input").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    submitAnswer();
  }
});

async function submitAnswer() {
  const answer = $("#interview-input").value.trim();
  if (!answer) return;
  const submit = $("#btn-interview-submit");
  submit.disabled = true;
  submit.textContent = "面试官在评估...";

  try {
    const result = await postJson("/api/interviewer/next", {
      session_id: state.session_id,
      answer: answer,
    });
    state.turns.push(result.turn);

    // Show feedback for the just-answered turn
    showFeedback(result.turn);

    // Advance question state for the NEXT turn.
    // focus_slots is the *session-level* training focus from the InterviewPacket
    // (set once at /interviewer/start) — it should NOT mutate per turn. The
    // per-turn 'missing_slots' lives in turn.missing_slots and is rendered
    // inside the feedback panel, not the banner.
    state.current_state = result.next_state;
    state.current_question = result.turn.next_question;
    state.current_os = result.turn.interviewer_os;

    if (!result.should_continue) {
      // Interview ended — keep the feedback visible, swap submit→finish
      hide("#btn-interview-submit");
      show("#btn-finish");
      $("#interview-stage").textContent = "面试结束";
      $("#interview-question").textContent =
        "本轮面试结束。点 [结束面试 → 看报告] 让 Coach 写复盘。";
    } else {
      // Re-render banner / question / cheat panel for next turn
      $("#interview-stage").textContent = formatStage(state.current_state);
      $("#interview-focus").textContent =
        (state.current_focus_slots || []).join(" / ") || "—";
      $("#interview-question").textContent = state.current_question || "";
      $("#interview-input").value = "";
      renderCheatPanel(state.current_os);
      show("#cheat-panel");
      show("#btn-cheat-toggle");
      $("#btn-cheat-toggle").textContent = "▼ 收起作弊模式";
    }
    renderTranscript();
    submit.disabled = false;
    submit.textContent = "提交回答";
  } catch (e) {
    console.error("interviewer.next failed:", e);
    if (e.status === 404) {
      // Spec C §2.6 session_expired — restart the whole flow rather than
      // letting the user keep typing into a dead session.
      showError("训练 session 已过期，请回到首页重新开始。");
    } else {
      showError("提交失败：网络或服务波动，请稍后重试。");
    }
    submit.disabled = false;
    submit.textContent = "重试提交";
  }
}

function formatStage(stage) {
  const stageMap = {
    "S1_motivation":  "S1 项目动机",
    "S2_overview":    "S2 项目概述",
    "S3_technical":   "S3 技术深挖",
    "S4_validation":  "S4 实验验证",
    "S5_reflection":  "S5 失败反思",
    "S6_matching":    "S6 匹配与总结",
    "done":           "面试结束",
  };
  return stageMap[stage] || stage || "—";
}

function showFeedback(turn) {
  const div = $("#interview-feedback");
  const missList = (turn.missing_slots || []).map(s =>
    `<span class="miss">${escapeHtml(s)}</span>`
  ).join(" ");
  const coveredList = (turn.covered_slots || []).map(s =>
    escapeHtml(s)
  ).join("、");
  div.innerHTML = `
    <div><b>面试官反馈：</b>${escapeHtml(turn.feedback || "（无反馈）")}</div>
    ${missList ? `<div style="margin-top:10px"><b>缺失槽位：</b>${missList}</div>` : ""}
    ${coveredList ? `<div style="margin-top:6px;color:var(--good)"><b>已覆盖：</b>${coveredList}</div>` : ""}
    <div class="score">本轮 score: ${turn.score} / 100 · source: ${escapeHtml(turn.source)}</div>
  `;
  show("#interview-feedback");
  // Make sure the user sees the score + missing slots — they're below the
  // question card and easy to miss otherwise.
  div.scrollIntoView({ behavior: "smooth", block: "center" });
}

function showError(text) {
  const div = $("#interview-feedback");
  div.innerHTML = `<div style="color:var(--bad)"><b>${escapeHtml(text)}</b></div>`;
  show("#interview-feedback");
}

// ----- cheat panel toggle + render -----

$("#btn-cheat-toggle").addEventListener("click", () => {
  const panel = $("#cheat-panel");
  const visible = !panel.classList.contains("hidden");
  if (visible) {
    panel.classList.add("hidden");
    $("#btn-cheat-toggle").textContent = "▶ 偷看面试官脑回路（作弊模式）";
  } else {
    panel.classList.remove("hidden");
    $("#btn-cheat-toggle").textContent = "▼ 收起作弊模式";
  }
});

function renderCheatPanel(os) {
  if (!os) return;
  const panel = $("#cheat-panel");
  const riskClass = ({ "低": "risk-low", "中": "risk-mid", "高": "risk-high" })
                    [os.risk_level] || "risk-mid";
  panel.className = "cheat-panel hidden " + riskClass;
  panel.innerHTML = `
    <h3>🔍 面试官内心 OS <span class="risk-badge">风险: ${escapeHtml(os.risk_level || "中")}</span></h3>
    <p><b>真正担心：</b>${escapeHtml(os.hidden_concern)}</p>
    <p><b>为什么追问：</b>${escapeHtml(os.why_this_question)}</p>
    ${(os.missing_slots && os.missing_slots.length) ? `
      <p><b>缺失槽位：</b></p>
      <ul>${os.missing_slots.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : ""}
    ${(os.what_i_want_to_hear && os.what_i_want_to_hear.length) ? `
      <p><b>想听到的：</b></p>
      <ul>${os.what_i_want_to_hear.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : ""}
  `;
}

// ----- transcript -----

function renderTranscript() {
  const div = $("#interview-transcript");
  if (!state.turns.length) {
    div.innerHTML = "";
    return;
  }
  div.innerHTML = `
    <h4>本场对话回顾（${state.turns.length} 轮）</h4>
    ${state.turns.map((t, i) => `
      <div class="turn">
        <div class="q"><b>Q${i + 1}（${escapeHtml(formatStage(t.state))}）：</b>${escapeHtml(t.question)}</div>
        <div class="a"><b>A：</b>${escapeHtml(t.answer)}</div>
      </div>
    `).join("")}
  `;
}

// ============================================================
// FINISH → REPORT
// ============================================================

$("#btn-finish").addEventListener("click", finishInterview);

async function finishInterview() {
  const btn = $("#btn-finish");
  btn.disabled = true;
  btn.textContent = "Coach 正在写报告...";
  try {
    const report = await postJson("/api/coach/review", {
      session_id: state.session_id,
    });
    state.report = report;
    renderReport(report);
    switchView("report");
  } catch (e) {
    console.error("coach.review failed:", e);
    if (e.status === 400) {
      // Spec C §2.7 gate: state != DONE AND turns < 6
      showError("本场训练还没回答足够多的问题，无法生成有效报告。请继续答题。");
    } else {
      showError("生成报告失败：Coach 暂时不可用，请稍后重试。");
    }
    btn.disabled = false;
    btn.textContent = "重试生成报告";
  }
}

function renderReport(r) {
  const evidence = (r.evidence || []).map(e => `
    <div class="evidence-card">
      <div class="quote">"${escapeHtml(e.quote)}"</div>
      <div class="problem"><b>问题：</b>${escapeHtml(e.problem)}</div>
      <div class="suggestion"><b>建议：</b>${escapeHtml(e.suggestion)}</div>
    </div>`).join("");

  const danger = (r.dangerous_questions || []).map(q =>
    `<li>${escapeHtml(q)}</li>`).join("");

  const strengths = (r.strengths || []).map(s =>
    `<li>${escapeHtml(s)}</li>`).join("");
  const weaknesses = (r.weaknesses || []).map(s =>
    `<li>${escapeHtml(s)}</li>`).join("");

  const rr = r.resume_rewrite || {};
  const missing = (rr.missing_evidence || []).length
    ? `<div class="missing">仍缺：${rr.missing_evidence.map(escapeHtml).join("、")}</div>`
    : "";

  const planSteps = ((r.next_training_plan || {}).steps || []).map(s => `
    <div class="plan-step">
      <b>${escapeHtml(s.name)}</b>: ${escapeHtml(s.goal)}
      <span class="why-now">${escapeHtml(s.why_now)}</span>
    </div>`).join("");

  $("#report-content").innerHTML = `
    <section>
      <h3>总分</h3>
      <div class="score">${r.overall_score}<span class="score-suffix"> / 100</span></div>
      <p>${escapeHtml(r.summary)}</p>
      ${strengths ? `<p><b style="color:var(--good)">优点：</b></p><ul>${strengths}</ul>` : ""}
      ${weaknesses ? `<p><b style="color:var(--warn)">短板：</b></p><ul>${weaknesses}</ul>` : ""}
    </section>

    <section>
      <h3>关键证据（${(r.evidence || []).length} 处）</h3>
      ${evidence || "<p>（本场无关键证据）</p>"}
    </section>

    <section>
      <h3>最危险的追问</h3>
      <ol>${danger}</ol>
    </section>

    <section class="resume-rewrite">
      <h3>简历改写</h3>
      <div class="original"><b>原文：</b>${escapeHtml(rr.original || "")}</div>
      <div class="rewritten"><b>改写：</b>${escapeHtml(rr.rewritten || "")}</div>
      ${missing}
    </section>

    <section>
      <h3>下一轮训练计划 — 推荐 ${escapeHtml((r.next_training_plan || {}).recommended_next_step || "")}</h3>
      <p>${escapeHtml((r.next_training_plan || {}).reason || "")}</p>
      ${planSteps}
    </section>

    <section class="humor">
      <h3>${escapeHtml((r.humor_card || {}).title || "今日 bug 报告")}</h3>
      <pre>${escapeHtml((r.humor_card || {}).content || "")}</pre>
    </section>
  `;
}

// ----- post-interview controls (exit / regen / replay) -----

$("#btn-interview-exit").addEventListener("click", () => {
  if (state.turns.length > 0 && !confirm("退出将丢失本场面试进度，确认退出？")) return;
  state.session_id = null;
  state.turns = [];
  state.current_state = null;
  state.current_question = null;
  state.current_os = null;
  state.report = null;
  switchView("home");
});

$("#btn-regen-report").addEventListener("click", async () => {
  const btn = $("#btn-regen-report");
  if (!state.session_id) {
    btn.textContent = "session 失效，请回到首页重新开始";
    setTimeout(() => { btn.textContent = "重新生成报告"; }, 3000);
    return;
  }
  btn.disabled = true;
  btn.textContent = "Coach 正在重写报告...";
  try {
    const report = await postJson("/api/coach/review", { session_id: state.session_id });
    state.report = report;
    renderReport(report);
    window.scrollTo({ top: 0, behavior: "smooth" });
    btn.textContent = "重新生成报告";
    btn.disabled = false;
  } catch (e) {
    console.error("regen report failed:", e);
    btn.textContent = "重新生成失败，稍后再试";
    btn.disabled = false;
    setTimeout(() => { btn.textContent = "重新生成报告"; }, 3000);
  }
});

$("#btn-replay").addEventListener("click", () => {
  // Keep user_model + packet (so they don't redo onboarding); fresh session.
  state.session_id = null;
  state.turns = [];
  state.current_state = null;
  state.current_question = null;
  state.current_os = null;
  state.report = null;
  // Re-fill the demo text if previously demo-ed; else leave whatever they typed
  if (state.is_demo && !$("#material-input").value.trim()) {
    $("#material-input").value = DEMO_PROJECT_TEXT;
  }
  switchView("material");
});
