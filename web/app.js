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

// ---------- DOM helpers ----------

function $(sel) { return document.querySelector(sel); }
function show(sel) { $(sel).classList.remove("hidden"); }
function hide(sel) { $(sel).classList.add("hidden"); }

function switchView(name) {
  ["home", "onboarding", "material", "interview", "report"].forEach(v => {
    document.querySelector("#view-" + v).classList.add("hidden");
  });
  document.querySelector("#view-" + name).classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = await resp.text();
    try {
      const parsed = JSON.parse(detail);
      detail = typeof parsed.detail === "string"
        ? parsed.detail
        : JSON.stringify(parsed.detail || parsed);
    } catch (_) { /* keep raw text */ }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
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
    appendChat("coach", "（出错了）" + e.message);
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
    const start = await postJson("/api/interviewer/start", {
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
    setMaterialHint("出错：" + e.message, "warn");
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
  hide("#cheat-panel");
  if (state.current_os) {
    show("#btn-cheat-toggle");
    renderCheatPanel(state.current_os);
  } else {
    hide("#btn-cheat-toggle");
  }
  // ensure submit button visible / finish hidden at the start of each turn
  show("#btn-interview-submit");
  hide("#btn-finish");
  $("#btn-interview-submit").disabled = false;
  $("#btn-interview-submit").textContent = "提交回答";
}
