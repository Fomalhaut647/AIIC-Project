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
  // Plan2 P13 replay flow
  is_replay: false,
  parent_session_id: null,
  replay_focus_slots: [],
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
  // Plan3 G3 hook: 切走任何视图都停掉正在播的 TTS audio（避免下一视图还能听到上一问）
  if (typeof CURRENT_TTS_AUDIO !== "undefined" && CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (_) {}
    CURRENT_TTS_AUDIO = null;
  }
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

// ---------- Plan2 P12: dashboard render ----------

function _escHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]
  ));
}

async function loadProfile() {
  const display = document.getElementById("profile-userid-display");
  if (display) display.textContent = USER_ID.slice(0, 8);

  const emptyEl = document.getElementById("profile-empty");
  const contentEl = document.getElementById("profile-content");

  let profile;
  try {
    const resp = await apiGet(`/api/users/${encodeURIComponent(USER_ID)}/profile`);
    profile = await resp.json();
  } catch (e) {
    console.error("loadProfile failed", e);
    if (emptyEl) {
      emptyEl.classList.remove("hidden");
      const msg = emptyEl.querySelector(".profile-empty-msg");
      if (msg) msg.textContent = "加载个人主页失败：" + (e.detail || e.message);
    }
    if (contentEl) contentEl.classList.add("hidden");
    return;
  }

  if ((profile.total_sessions || 0) === 0) {
    if (emptyEl) emptyEl.classList.remove("hidden");
    if (contentEl) contentEl.classList.add("hidden");
    return;
  }

  if (emptyEl) emptyEl.classList.add("hidden");
  if (contentEl) contentEl.classList.remove("hidden");
  renderProfile(profile);
}

function renderProfile(profile) {
  // 1. Hero stats
  document.getElementById("stat-total").textContent = profile.total_sessions || 0;
  document.getElementById("stat-avg").textContent =
    (profile.average_score == null ? "—" : Math.round(profile.average_score)) + " / 100";

  const dates = new Set(
    (profile.sessions || []).map(s => (s.created_at || "").slice(0, 10)).filter(Boolean)
  );
  document.getElementById("stat-days").textContent = dates.size;

  // 2. 弱点柱状图（top 5）
  const weak = Object.entries(profile.recurring_weaknesses || {})
    .sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxCount = Math.max(1, ...weak.map(([, c]) => c));
  const weakUl = document.getElementById("profile-weakness-bars");
  weakUl.innerHTML = "";
  if (weak.length === 0) {
    weakUl.innerHTML = '<li><span class="label">（暂无累计弱点）</span></li>';
  } else {
    for (const [slot, count] of weak) {
      const li = document.createElement("li");
      const widthPx = Math.max(4, Math.round(count / maxCount * 240));
      li.innerHTML = `
        <span class="label">${_escHtml(slot)}</span>
        <span class="bar" style="width: ${widthPx}px"></span>
        <span class="count">${count} 次</span>
      `;
      weakUl.appendChild(li);
    }
  }

  // 3. 时间线（倒序：最新在最上；前 20 条）
  const timeline = document.getElementById("profile-timeline");
  timeline.innerHTML = "";
  const sortedSessions = [...(profile.sessions || [])]
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .slice(0, 20);

  for (const s of sortedSessions) {
    const li = document.createElement("li");
    if (s.is_replay) li.classList.add("replay-row");

    const dateStr = (s.created_at || "").replace("T", " ").slice(0, 16) || "—";
    const weaknessTags = s.weakness_tags || [];
    const replayBtns = weaknessTags.map(t => (
      `<button data-action="replay" data-parent="${_escHtml(s.session_id)}" data-slot="${_escHtml(t)}">重练 ${_escHtml(t)}</button>`
    )).join(" ");
    const downloadBtn = `<a class="dl-link" data-action="download" data-sid="${_escHtml(s.session_id)}" href="/api/sessions/${encodeURIComponent(s.session_id)}/export.md" download>下载 .md</a>`;

    li.innerHTML = `
      <div class="timeline-meta">${s.is_replay ? "↳ 重练 · " : ""}${_escHtml(dateStr)}　<strong>[${_escHtml(s.target)}]</strong></div>
      <div class="timeline-title">${_escHtml(s.project_summary_short || "(无项目摘要)")}</div>
      <div class="timeline-weak">总分 ${s.overall_score == null ? "—" : s.overall_score} ／ 弱点：${_escHtml(weaknessTags.join("、") || "（无）")}</div>
      <div class="actions">
        ${replayBtns}
        ${downloadBtn}
      </div>
    `;
    timeline.appendChild(li);
  }

  // 4. 项目库 (去重 + count)
  const projUl = document.getElementById("profile-projects");
  projUl.innerHTML = "";
  const counts = {};
  for (const s of profile.sessions || []) {
    const name = s.project_summary_short;
    if (!name) continue;
    counts[name] = (counts[name] || 0) + 1;
  }
  const projEntries = Object.entries(counts);
  if (projEntries.length === 0) {
    projUl.innerHTML = '<li>（暂无）</li>';
  } else {
    for (const [name, n] of projEntries) {
      const li = document.createElement("li");
      li.innerHTML = `${_escHtml(name)}<span class="proj-count">（${n} 次）</span>　— <button data-action="reuse" data-name="${_escHtml(name)}">再来一次</button>`;
      projUl.appendChild(li);
    }
  }
}

// 全局 click 委托：dashboard 上动态生成的按钮统一在这里 dispatch (避免 inline onclick)
// Polish: null guard 保护 — 若 index.html 因模板降级 (error fallback page 等)
// 没渲 view-profile DOM, 不应让整个 app.js 在加载时就 crash on null deref。
const _viewProfileEl = document.getElementById("view-profile");
if (_viewProfileEl) {
  _viewProfileEl.addEventListener("click", (e) => {
    const t = e.target.closest("[data-action]");
    if (!t) return;
    const action = t.dataset.action;
    if (action === "replay") {
      e.preventDefault();
      startReplay(t.dataset.parent, t.dataset.slot);  // P13
    } else if (action === "download") {
      // 走 downloadMarkdown 让 409/404 错误能 surface 给用户而不是浏览器静默
      e.preventDefault();
      downloadMarkdown(t.dataset.sid);  // P14
    } else if (action === "reuse") {
      e.preventDefault();
      reuseProject(t.dataset.name);  // P14
    }
  });
}

// 空 state link
const _emptyLink = document.getElementById("profile-empty-link");
if (_emptyLink) {
  _emptyLink.addEventListener("click", (e) => {
    e.preventDefault();
    switchView("home");
  });
}

// ---------- Plan2 P13: replay flow ----------

async function startReplay(parentSessionId, focusSlot) {
  let result;
  try {
    result = await postJson("/api/interviewer/replay", {
      parent_session_id: parentSessionId,
      focus_slots: [focusSlot],
    });
  } catch (e) {
    console.error("startReplay failed", e);
    alert("启动重练失败：" + (e.detail || e.message));
    return;
  }

  // Inject replay state for the interview view
  state.session_id = result.session_id;
  state.is_replay = true;
  state.parent_session_id = parentSessionId;
  state.replay_focus_slots = [focusSlot];
  state.current_question = result.question;
  state.current_state = result.state;
  state.current_focus_slots = result.focus_slots || [focusSlot];
  state.current_os = result.interviewer_os;
  state.turns = [];
  state.report = null;

  switchView("interview");
  _showReplayBanner(`重练模式：只追问「${focusSlot}」`);

  // Mirror v2 renderInterviewView logic to populate the interview view
  $("#interview-stage").textContent = formatStage(state.current_state);
  $("#interview-focus").textContent = state.current_focus_slots.join(" / ") || "—";
  $("#interview-question").textContent = state.current_question || "";
  $("#interview-input").value = "";
  hide("#interview-feedback");
  hide("#btn-finish");
  show("#btn-interview-submit");
  renderStageOutline();  // Plan3.5 Imp 1
  if (state.current_os) {
    show("#btn-cheat-toggle");
    renderCheatPanel(state.current_os);
    // Plan3.5 Imp 4: 抽屉默认 collapsed
    hide("#cheat-panel");
  } else {
    hide("#btn-cheat-toggle");
    hide("#cheat-panel");
  }
  $("#interview-transcript").innerHTML = "";
  // Plan3 G3: replay 模式同样自动朗读首问
  _maybeSpeakCurrentQuestion();
}

function _showReplayBanner(text) {
  const view = document.getElementById("view-interview");
  let banner = document.getElementById("replay-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "replay-banner";
    banner.className = "replay-banner";
    // Insert AFTER the topbar exit button (so banner sits above interview-banner)
    const topbar = view.querySelector(".topbar");
    if (topbar && topbar.nextSibling) view.insertBefore(banner, topbar.nextSibling);
    else view.insertBefore(banner, view.firstChild);
  }
  banner.textContent = text;
  banner.classList.remove("hidden");
}

function _hideReplayBanner() {
  const banner = document.getElementById("replay-banner");
  if (banner) banner.classList.add("hidden");
}

/** Returns true if mini-report shown; false if failed (caller should display fallback UI). */
async function finishReplay() {
  let mini;
  try {
    mini = await postJson("/api/interviewer/replay/finish", {
      session_id: state.session_id,
    });
  } catch (e) {
    console.error("finishReplay failed", e);
    alert("生成重练 mini-report 失败：" + (e.detail || e.message));
    return false;
  }

  document.getElementById("mini-focus").textContent = (mini.focus_slots || []).join("、");
  document.getElementById("mini-cov-before").textContent = Math.round((mini.coverage_before || 0) * 100);
  document.getElementById("mini-cov-after").textContent = Math.round((mini.coverage_after || 0) * 100);
  const deltaEl = document.getElementById("mini-delta");
  const deltaPP = mini.delta_pp || 0;
  deltaEl.textContent = (deltaPP >= 0 ? "+" : "") + Math.round(deltaPP) + "pp";
  deltaEl.classList.remove("positive", "negative");
  if (deltaPP > 0) deltaEl.classList.add("positive");
  else if (deltaPP < 0) deltaEl.classList.add("negative");

  document.getElementById("mini-sample").textContent = mini.sample_good_answer || "—";
  document.getElementById("mini-next").textContent = mini.next_step || "—";
  const modal = document.getElementById("replay-mini-modal");
  modal.classList.remove("hidden");
  // a11y: 焦点移到 close 按钮 + Esc 关闭
  const closeBtn = document.getElementById("mini-close");
  if (closeBtn) closeBtn.focus();
  return true;
}

// Esc 关闭 mini-report modal (a11y, P13 polish)
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const modal = document.getElementById("replay-mini-modal");
  if (modal && !modal.classList.contains("hidden")) {
    document.getElementById("mini-close").click();
  }
});

document.getElementById("mini-close").addEventListener("click", () => {
  document.getElementById("replay-mini-modal").classList.add("hidden");
  // Clear replay state and return to dashboard so timeline now shows the replay row
  state.is_replay = false;
  state.replay_focus_slots = [];
  state.parent_session_id = null;
  state.session_id = null;
  state.turns = [];
  _hideReplayBanner();
  refreshProfileDot();  // dot may newly appear if first session
  switchView("profile");
  loadProfile();
});

// ---------- Plan2 P14: resume iterate UI + Markdown export ----------

document.getElementById("resume-iterate-btn").addEventListener("click", async () => {
  const ta = document.getElementById("resume-iterate-input");
  const text = ta.value.trim();
  if (!text) {
    alert("先粘贴改后的简历段落");
    return;
  }
  if (!state.session_id) {
    alert("当前没有 session（可能已过期）。回到首页重新开始。");
    return;
  }

  const btn = document.getElementById("resume-iterate-btn");
  btn.disabled = true;
  btn.textContent = "Coach 评估中...";

  let rev;
  try {
    rev = await postJson("/api/coach/resume_iterate", {
      session_id: state.session_id,
      user_revised_resume: text,
    });
  } catch (e) {
    console.error("resume_iterate failed", e);
    alert("Coach 评估失败：" + (e.detail || e.message));
    btn.disabled = false;
    btn.textContent = "让 Coach 看看";
    return;
  }

  const fb = document.getElementById("resume-iterate-feedback");
  fb.classList.remove("hidden", "feedback-good", "feedback-pending");
  fb.classList.add(rev.is_good_enough ? "feedback-good" : "feedback-pending");
  fb.innerHTML = `
    <p class="iter-banner">${rev.is_good_enough ? "差不多可以了 ✨" : "还差一点"}</p>
    <p>${escapeHtml(rev.coach_feedback || "")}</p>
    <p>新覆盖：${escapeHtml((rev.newly_covered || []).join("、") || "（无）")}</p>
    <p>仍差：${escapeHtml((rev.still_missing || []).join("、") || "（无）")}</p>
  `;

  const hist = document.getElementById("resume-iterate-history");
  const list = document.getElementById("resume-iterate-history-list");
  hist.classList.remove("hidden");
  const li = document.createElement("li");
  const ts = (rev.timestamp || "").replace("T", " ").slice(0, 16);
  li.innerHTML = `
    <strong>第 ${rev.iteration_index} 轮</strong>
    <span style="color: var(--text-2); font-size: 0.85em;">· ${escapeHtml(ts)}</span>
    <pre>${escapeHtml(rev.user_text || text)}</pre>
    <p>${escapeHtml(rev.coach_feedback || "")}</p>
  `;
  list.appendChild(li);

  ta.value = "";
  btn.disabled = false;
  btn.textContent = "让 Coach 看看";
});

async function downloadMarkdown(sessionId) {
  // Browser-native download via fetch + blob (避免直接用 <a download> 失去错误处理)
  try {
    const resp = await apiGet(`/api/sessions/${encodeURIComponent(sessionId)}/export.md`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const cd = resp.headers.get("content-disposition") || "";
    const m = cd.match(/filename="([^"]+)"/);
    a.download = m ? m[1] : `projectprobe-${sessionId.slice(0, 8)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("downloadMarkdown failed", e);
    if (e.status === 409) {
      alert("该 session 还没有完成 review，无法导出");
    } else if (e.status === 404) {
      alert("Session 不存在");
    } else {
      alert("导出失败：" + (e.detail || e.message));
    }
  }
}

// Polish: null guard mirrors view-profile pattern — view-report 在某些 fallback
// template 下可能也缺，避免 module load 阶段 null deref 让整个 app 哑火。
const _exportMdBtn = document.getElementById("export-md-btn");
if (_exportMdBtn) {
  _exportMdBtn.addEventListener("click", async (e) => {
    if (!state.session_id) {
      alert("当前没有可导出的 session");
      return;
    }
    const btn = e.currentTarget;
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "下载中...";
    try {
      await downloadMarkdown(state.session_id);
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
}

function reuseProject(name) {
  if (!name) return;
  // 跳到 material 视图并预填项目名（用户可在此基础上编辑）
  switchView("material");
  const ta = document.getElementById("material-input");
  if (ta) {
    ta.value = name;
    ta.focus();
  }
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

    // 顺序: switchView 先 (pause 任何残留 TTS audio) → renderInterviewView (可能启动新 TTS)
    // 与项目其他 5 处 callsite 一致；让 TTS hook 顺序确定 (pause → maybe-start) 不靠 race
    switchView("interview");
    renderInterviewView();
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

// Plan3.5 Imp 1: 6 阶段 outline (state-machine 顺序对齐 InterviewStage enum + interviewer.py _STAGE_ORDER)
const STAGES = [
  { key: "S1_motivation", label: "S1 项目动机" },
  { key: "S2_overview",   label: "S2 项目概述" },
  { key: "S3_technical",  label: "S3 技术深挖" },
  { key: "S4_validation", label: "S4 实验验证" },
  { key: "S5_reflection", label: "S5 失败反思" },
  { key: "S6_matching",   label: "S6 匹配与总结" },
];

function renderStageOutline() {
  // 渲染左侧 sidebar 的 stage 进度 outline。当前阶段高亮、已过阶段灰勾、未到阶段 ·
  // 三态: "done" (全部 ✓) / 已知 enum (i<cur ✓, i===cur ▸, i>cur ·) / null/未知 (全部 ·)
  // 不要把 null 和 "done" 混为一谈——会让首次渲染前 6 阶段都假装完成。
  const el = document.getElementById("interview-stage-outline");
  if (!el) return;
  const cur = state.current_state;
  const allDone = cur === "done";
  const curIdx = STAGES.findIndex(s => s.key === cur);
  const unknownOrNull = !allDone && curIdx === -1;  // null / undefined / 错位 enum
  el.innerHTML = STAGES.map((s, i) => {
    let cls, icon, ariaCurrent = "";
    if (allDone) {
      cls = "stage-done"; icon = "✓";
    } else if (unknownOrNull) {
      cls = "stage-pending"; icon = "·";  // 未知 / 未启动 → 全部 pending,不假装 done
    } else if (i < curIdx) {
      cls = "stage-done"; icon = "✓";
    } else if (i === curIdx) {
      cls = "stage-current"; icon = "▸"; ariaCurrent = ' aria-current="step"';
    } else {
      cls = "stage-pending"; icon = "·";
    }
    return `<li class="${cls}"${ariaCurrent}><span class="stage-icon">${icon}</span><span class="stage-label">${escapeHtml(s.label)}</span></li>`;
  }).join("");
}

function renderInterviewView() {
  $("#interview-stage").textContent = formatStage(state.current_state);
  $("#interview-focus").textContent =
    (state.current_focus_slots || []).join(" / ") || "—";
  $("#interview-question").textContent = state.current_question || "";
  $("#interview-input").value = "";
  hide("#interview-feedback");
  if (state.current_os) {
    show("#btn-cheat-toggle");
    renderCheatPanel(state.current_os);
    // Plan3.5 Imp 4: 抽屉默认 collapsed (不 auto-open)，让 OS 不再贴近 next question
    // 用户主动点 tab 才展开。
    hide("#cheat-panel");
  } else {
    hide("#btn-cheat-toggle");
    hide("#cheat-panel");
  }
  // ensure submit button visible / finish hidden at the start of each turn
  show("#btn-interview-submit");
  hide("#btn-finish");
  $("#btn-interview-submit").disabled = false;
  $("#btn-interview-submit").textContent = "提交回答";
  renderStageOutline();  // Plan3.5 Imp 1
  renderTranscript();
  // Plan3 G3: 若 speaker toggle 已开, 自动朗读当前问题
  _maybeSpeakCurrentQuestion();
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
      $("#interview-stage").textContent = "面试结束";
      if (state.is_replay) {
        // Plan2 P13: replay session 自动跳到 mini-report (不走 review/coach)
        $("#interview-question").textContent = "重练完成。正在生成 mini-report...";
        renderTranscript();
        // 关键: 不在这里 re-enable submit。如果 finishReplay 失败，alert 后保持
        // submit 隐藏 + 把 question 改成「失败请回首页/重试」让用户有明确出路;
        // 否则 state.is_replay=true 时再点 submit 会向已结束的 session 提交答案。
        const ok = await finishReplay();
        if (!ok) {
          $("#interview-question").textContent =
            "生成 mini-report 失败。请回到首页重试 (退出面试按钮在左上角)。";
        }
        return;
      } else {
        show("#btn-finish");
        $("#interview-question").textContent =
          "本轮面试结束。点 [结束面试 → 看报告] 让 Coach 写复盘。";
      }
    } else {
      // Re-render sidebar / question / cheat panel for next turn
      $("#interview-stage").textContent = formatStage(state.current_state);
      $("#interview-focus").textContent =
        (state.current_focus_slots || []).join(" / ") || "—";
      $("#interview-question").textContent = state.current_question || "";
      $("#interview-input").value = "";
      renderStageOutline();  // Plan3.5 Imp 1
      renderCheatPanel(state.current_os);  // 重填 drawer body 但维持当前开/合状态
      show("#btn-cheat-toggle");
      // Plan3 G3: 自动朗读 next-turn 的新问题
      _maybeSpeakCurrentQuestion();
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
  // Plan3.5 Imp 3: 反馈渲染到左侧 sidebar (而非主流下方)。槽位用 chip 样式区分
  // 缺失 (橙) / 已覆盖 (绿)，让用户一眼看到 missing。score 上轮分数底排。
  const div = $("#interview-feedback");
  const missList = (turn.missing_slots || []).map(s =>
    `<span class="miss">${escapeHtml(s)}</span>`
  ).join(" ");
  const coveredList = (turn.covered_slots || []).map(s =>
    `<span class="covered-chip">${escapeHtml(s)}</span>`
  ).join(" ");
  div.innerHTML = `
    <div><b>反馈：</b>${escapeHtml(turn.feedback || "（无反馈）")}</div>
    ${missList ? `<div><b>缺失槽位：</b><br>${missList}</div>` : ""}
    ${coveredList ? `<div><b>已覆盖：</b><br>${coveredList}</div>` : ""}
    <div class="score">本轮 score: ${turn.score} / 100 · source: ${escapeHtml(turn.source)}</div>
  `;
  show("#interview-feedback");
  // Plan3.5: 不再 scrollIntoView — sidebar position:sticky 已让反馈始终可见 +
  // 主流 question card 不会被滚走，用户看 next question 不丢上下文。
}

function showError(text) {
  const div = $("#interview-feedback");
  div.innerHTML = `<div style="color:var(--bad)"><b>${escapeHtml(text)}</b></div>`;
  show("#interview-feedback");
}

// ----- cheat drawer toggle + render (Plan3.5 Imp 4) -----
// 抽屉默认 closed (.hidden). 点击 tab → toggle. 关闭方式: 再点 tab / drawer 内 X /
// Esc. drawer body innerHTML 由 renderCheatPanel 注入并含一颗 .cheat-drawer-close.

$("#btn-cheat-toggle").addEventListener("click", () => {
  const panel = $("#cheat-panel");
  panel.classList.toggle("hidden");
  // tab 文字保持静态 ("🧠 偷看面试官脑回路")，不再随 open/close 切换
  // a11y: 同步 aria-hidden / aria-pressed 给屏读用户
  const isOpen = !panel.classList.contains("hidden");
  panel.setAttribute("aria-hidden", isOpen ? "false" : "true");
  $("#btn-cheat-toggle").setAttribute("aria-pressed", isOpen ? "true" : "false");
});

// 抽屉内 X 关闭 (event delegation; renderCheatPanel 注入的 .cheat-drawer-close)
// 关闭时把焦点归还 tab 按钮 (a11y: focus management)
document.getElementById("cheat-panel")?.addEventListener("click", (e) => {
  if (e.target.closest(".cheat-drawer-close")) {
    const panel = document.getElementById("cheat-panel");
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    const tab = document.getElementById("btn-cheat-toggle");
    if (tab) {
      tab.setAttribute("aria-pressed", "false");
      tab.focus();
    }
  }
});

// Esc 关闭抽屉 (a11y; 与 replay-mini-modal Esc 不互踩——分别 match 自己 modal)
// 命中后 return 不再 fall-through; 防御性: 万一两 modal 同开 (理论 view 互斥不该发生)
// 也只关一个,用户再按 Esc 关下一个,符合栈式 modal 行为预期。
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const panel = document.getElementById("cheat-panel");
  if (panel && !panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    const tab = document.getElementById("btn-cheat-toggle");
    if (tab) {
      tab.setAttribute("aria-pressed", "false");
      tab.focus();
    }
    return;  // 命中 cheat-drawer 后停, 不再处理 mini-modal Esc
  }
});

function renderCheatPanel(os) {
  if (!os) return;
  const panel = $("#cheat-panel");
  const riskClass = ({ "低": "risk-low", "中": "risk-mid", "高": "risk-high" })
                    [os.risk_level] || "risk-mid";
  // 保留 .hidden 状态：renderCheatPanel 只填 body, 不强制 open/close (上层调用方决定)
  const wasHidden = panel.classList.contains("hidden");
  panel.className = "cheat-panel " + riskClass + (wasHidden ? " hidden" : "");
  // Plan3.5 Imp 4: 抽屉里加 X 关闭按钮
  panel.innerHTML = `
    <button class="cheat-drawer-close" type="button" aria-label="关闭抽屉" title="关闭 (Esc)">×</button>
    <h3>🧠 面试官内心 OS <span class="risk-badge">风险: ${escapeHtml(os.risk_level || "中")}</span></h3>
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

// ============================================================
// PLAN3 MULTIMODAL — G2 STT (mic) + G3 TTS (speaker) + G4 toggles + upload
// Spec E §7.4 (upload) / §8 (STT VoiceInput) / §9.3 (TTS frontend) / §10 (toggles).
// 5 硬约束: 不动既有 DOM id / 不动 API 数据流 / vanilla JS / CSS 变量主题 / 0 npm dep.
// ============================================================

// ---------- Plan3 toggle state (localStorage 持久化) ----------

state.mic_on = (() => {
  try { return localStorage.getItem("micOn") === "true"; }
  catch (_) { return false; }
})();
state.speaker_on = (() => {
  try { return localStorage.getItem("speakerOn") === "true"; }
  catch (_) { return false; }
})();

// 当前激活的 VoiceInput instance (mic-btn click 时单例切换)
let VOICE_INPUT = null;
// 当前正在播的 TTS Audio (用于 speaker off / switchView 时 pause)
let CURRENT_TTS_AUDIO = null;

// ---------- Plan3 toast (轻量替代 alert; 与 nav-toggle 风格对齐) ----------

function _plan3Toast(msg, kind /* 'info'|'warn'|'error' */) {
  let el = document.getElementById("plan3-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "plan3-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.style.cssText = [
      "position:fixed", "top:60px", "left:50%", "transform:translateX(-50%)",
      "background:var(--bg-2,#1f1f22)", "color:var(--text-1,#fff)",
      "padding:10px 16px", "border-radius:8px", "z-index:9999",
      "box-shadow:0 4px 12px rgba(0,0,0,0.3)", "font-size:14px",
      "max-width:80vw", "transition:opacity 0.2s",
    ].join(";");
    document.body.appendChild(el);
  }
  el.style.borderLeft = "3px solid " + (
    kind === "error" ? "var(--bad,#e57373)"
    : kind === "warn" ? "var(--warn,#f0a35e)"
    : "var(--accent,#7ab8ff)"
  );
  el.textContent = msg;
  el.style.opacity = "1";
  clearTimeout(_plan3Toast._timer);
  _plan3Toast._timer = setTimeout(() => {
    if (el) el.style.opacity = "0";
  }, 3500);
}

// ---------- Plan3 G4: dual toggle (mic / speaker) ----------

function updateMicToggleVisual() {
  const btn = document.getElementById("toggle-mic");
  if (!btn) return;
  btn.setAttribute("aria-pressed", state.mic_on ? "true" : "false");
  // 录音按钮 enable / disable 跟随 toggle (Q6 mic-btn 默认 disabled)
  document.querySelectorAll(".mic-btn").forEach(b => {
    b.disabled = !state.mic_on;
  });
}

function updateSpeakerToggleVisual() {
  const btn = document.getElementById("toggle-speaker");
  if (!btn) return;
  btn.setAttribute("aria-pressed", state.speaker_on ? "true" : "false");
}

document.getElementById("toggle-mic")?.addEventListener("click", () => {
  state.mic_on = !state.mic_on;
  try { localStorage.setItem("micOn", String(state.mic_on)); } catch (_) {}
  updateMicToggleVisual();
  // 关 mic 时立刻停掉正在录的 VoiceInput + 清掉 .mic-pulse 视觉
  if (!state.mic_on && VOICE_INPUT && VOICE_INPUT.isRecording) {
    try { VOICE_INPUT.stop(); } catch (_) {}
    document.querySelectorAll(".mic-btn.mic-pulse").forEach(b => {
      b.classList.remove("mic-pulse");
      b.dataset.recording = "false";
    });
  }
});

document.getElementById("toggle-speaker")?.addEventListener("click", () => {
  state.speaker_on = !state.speaker_on;
  try { localStorage.setItem("speakerOn", String(state.speaker_on)); } catch (_) {}
  updateSpeakerToggleVisual();
  // 关 speaker 时立刻停掉正在播的 audio
  if (!state.speaker_on && CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (_) {}
    CURRENT_TTS_AUDIO = null;
  }
  // Plan3.5 Bug 4: 翻 ON 时立即朗读当前问题——click 本身是 user gesture,
  // 不会被 autoplay policy block; 这是已显示问题但 toggle 才打开的场景下
  // 给用户即时反馈,确认 TTS 真的能听到。无 current_question 时 (home /
  // profile view) 啥也不干。
  if (state.speaker_on && state.current_question) {
    fetchAndPlayTTS(state.current_question);
  }
});

// 初始化 toggle 视觉 (基于 localStorage 恢复的 state)
updateMicToggleVisual();
updateSpeakerToggleVisual();

// ---------- Plan3.5 Bug 3 STT: VoiceInput class (MediaRecorder + server-side ASR) ----------

/**
 * 封装 MediaRecorder + multipart fetch 到 /api/stt/transcribe。
 * 替代 v1 Chrome 原生 Web Speech API (中文准确度差且仅 Chromium 系支持)。
 *
 * 对比旧实现：
 * - 浏览器支持: getUserMedia + MediaRecorder = Chrome / Firefox / Safari (vs Chrome only)
 * - 准确度: 后端 mimo-v2-omni 多模态模型转录, 比 Chrome 原生中文 ASR 更稳
 * - UX 退化: 没有流式 partial result, 用户停录后才看到完整文本 (trade-off 必接受)
 * - 网络依赖: 后端服务必需; 503 fallback toast 提示用户改打字
 *
 * 使用方式:
 *   const v = new VoiceInput({ targetTextarea, onStart, onStop, onError });
 *   v.start();   // async 申请麦克风权限并开始录音; 失败回调 onError
 *   v.stop();    // 主动停, 触发 onstop → 上传转录 → onStop callback
 */
class VoiceInput {
  constructor(opts) {
    this.targetTextarea = opts.targetTextarea;
    this.onStart = opts.onStart || (() => {});
    this.onStop = opts.onStop || (() => {});
    this.onError = opts.onError || (() => {});
    this.isRecording = false;
    this._mediaRecorder = null;
    this._stream = null;
    this._chunks = [];
  }

  static isSupported() {
    return typeof window !== "undefined" &&
      typeof navigator !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function" &&
      typeof window.MediaRecorder === "function";
  }

  // 静态属性: MediaRecorder mime fallback 链, 优先 webm/opus (Chrome 默认 + 体积小)。
  // 按顺序探 MediaRecorder.isTypeSupported, 第一个 true 的赢; 都不支持降级到 ""
  // (浏览器选默认; 后端 ffmpeg 转码到 wav 兜底)。
  static MIME_PRIORITY = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/wav",
  ];

  async start() {
    if (this.isRecording) return;
    if (!VoiceInput.isSupported()) {
      this.onError(new Error("浏览器不支持麦克风录音 (建议 Chrome / Edge / Firefox)"));
      return;
    }

    // 1. 申请麦克风权限 (getUserMedia 异步)
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      // NotAllowedError / NotFoundError / SecurityError 等
      const name = e && e.name ? e.name : "unknown";
      const msg = name === "NotAllowedError"
        ? "请允许麦克风权限 (浏览器地址栏左侧 🎤 图标)"
        : name === "NotFoundError"
        ? "未检测到麦克风设备"
        : `获取麦克风失败: ${name}`;
      this.onError(new Error(msg));
      return;
    }
    this._stream = stream;

    // 2. 选 mime: 探 MIME_PRIORITY 链, 第一个 isTypeSupported 的赢
    let mime = "";
    for (const m of VoiceInput.MIME_PRIORITY) {
      if (window.MediaRecorder.isTypeSupported && window.MediaRecorder.isTypeSupported(m)) {
        mime = m;
        break;
      }
    }
    // mime === "" → 让浏览器选默认; 后端 ffmpeg 兜底转 wav。

    // 3. 创建 MediaRecorder
    let recorder;
    try {
      recorder = mime ? new window.MediaRecorder(stream, { mimeType: mime })
                      : new window.MediaRecorder(stream);
    } catch (e) {
      this._cleanupStream();
      this.onError(new Error("无法初始化录音器: " + (e.message || e)));
      return;
    }
    this._mediaRecorder = recorder;
    this._chunks = [];

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) this._chunks.push(ev.data);
    };
    recorder.onstart = () => {
      this.isRecording = true;
      this.onStart();
    };
    recorder.onerror = (ev) => {
      const errName = (ev && ev.error && ev.error.name) || "unknown";
      this.onError(new Error("录音出错: " + errName));
    };
    recorder.onstop = async () => {
      this.isRecording = false;
      const blobMime = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(this._chunks, { type: blobMime });
      this._chunks = [];
      this._cleanupStream();
      // 上传 + 转录回填 textarea。失败由 _uploadAndTranscribe 内部 onError 处理。
      await this._uploadAndTranscribe(blob);
      this.onStop();
    };

    // 4. 启动录音 (sync; 真正的 isRecording=true 在 onstart event 内置)
    try {
      recorder.start();
    } catch (e) {
      this._cleanupStream();
      this.onError(new Error("无法启动录音: " + (e.message || e)));
    }
  }

  stop() {
    if (!this.isRecording || !this._mediaRecorder) return;
    // 触发 onstop async; cleanup + upload 在 onstop 内
    try { this._mediaRecorder.stop(); } catch (_) {}
  }

  _cleanupStream() {
    if (this._stream) {
      try {
        this._stream.getTracks().forEach(t => t.stop());
      } catch (_) {}
      this._stream = null;
    }
    this._mediaRecorder = null;
  }

  async _uploadAndTranscribe(blob) {
    // 上传 audio blob 到 /api/stt/transcribe → 把 transcript 追加到 textarea。
    if (!blob || blob.size === 0) return;
    if (blob.size > 5 * 1024 * 1024) {
      this.onError(new Error("录音过长 (限 60s / 5MB), 请缩短后重试"));
      return;
    }

    const fd = new FormData();
    // filename 取个合理后缀, server 端用 mime 做实际路由
    const ext = (blob.type || "audio/webm").includes("webm") ? "webm"
              : (blob.type || "").includes("mp4")  ? "m4a"
              : (blob.type || "").includes("ogg")  ? "ogg"
              : (blob.type || "").includes("wav")  ? "wav"
              : "webm";
    fd.append("file", blob, `recording.${ext}`);
    if (typeof USER_ID === "string") fd.append("user_id", USER_ID);

    let resp;
    try {
      resp = await fetch("/api/stt/transcribe", { method: "POST", body: fd });
    } catch (e) {
      this.onError(new Error("上传录音失败: " + (e.message || e)));
      return;
    }
    if (!resp.ok) {
      // 503 走 TTS 同款 fallback toast 模式; 其余 status 给具体错误
      let msg;
      if (resp.status === 503) {
        msg = "STT 服务暂时不可用, 请改键盘输入";
      } else if (resp.status === 413) {
        msg = "录音过长 (≤ 60s / 5MB)";
      } else if (resp.status === 422) {
        msg = "音频解码失败, 请重录";
      } else if (resp.status === 400) {
        msg = "录音格式不支持 (浏览器 MediaRecorder 设置异常)";
      } else {
        msg = `STT 上传失败 (HTTP ${resp.status})`;
      }
      this.onError(new Error(msg));
      return;
    }

    let data;
    try {
      data = await resp.json();
    } catch (_) {
      this.onError(new Error("STT 响应解析失败"));
      return;
    }
    const transcript = (data && typeof data.transcript === "string") ? data.transcript.trim() : "";
    if (!transcript) {
      // 空转录 (静音 / 无清晰人声) 不视为错; 给个 toast 让用户知道。
      if (typeof _plan3Toast === "function") {
        _plan3Toast("没听清, 请再说一次", "warn");
      }
      return;
    }
    // 在原有内容后追加, 空格 / 换行 分隔(用户已有打字内容不丢)
    const cur = this.targetTextarea.value || "";
    const sep = cur && !cur.endsWith("\n") ? " " : "";
    this.targetTextarea.value = cur + sep + transcript;
  }
}

// ---------- mic-btn click handlers (3 个 textarea) ----------

document.querySelectorAll(".mic-btn").forEach(btn => {
  btn.dataset.recording = "false";
  btn.addEventListener("click", () => {
    if (!state.mic_on) {
      _plan3Toast("请先在右上角打开 🎤 麦克风模式", "warn");
      return;
    }
    if (!VoiceInput.isSupported()) {
      _plan3Toast("当前浏览器不支持语音输入 (建议 Chrome / Edge)", "error");
      return;
    }
    const targetId = btn.dataset.targetTextarea;
    const ta = document.getElementById(targetId);
    if (!ta) {
      console.warn("mic-btn: target textarea not found", targetId);
      return;
    }

    // 已在录: 停。未录: 先停掉别的 instance, 再开新。
    if (btn.dataset.recording === "true" && VOICE_INPUT) {
      VOICE_INPUT.stop();
      return;
    }

    if (VOICE_INPUT && VOICE_INPUT.isRecording) {
      VOICE_INPUT.stop();
      // 清掉别的 mic-btn 的 active 视觉
      document.querySelectorAll(".mic-btn.mic-pulse").forEach(b => {
        b.classList.remove("mic-pulse");
        b.dataset.recording = "false";
      });
    }

    // Capture newVI 在 closure 内，让 onStop 用 instance equality check
    // 避免 swap race：用户从 textarea A 切到 B 时，旧 instance 的 onend 会
    // 触发 onStop callback；如果 unconditional `VOICE_INPUT = null` 会把
    // 新 live instance 也 nulls 掉。`if (VOICE_INPUT === newVI)` 保证只
    // 释放自己。
    const newVI = new VoiceInput({
      targetTextarea: ta,
      onStart: () => {
        btn.classList.add("mic-pulse");
        btn.dataset.recording = "true";
      },
      onStop: () => {
        btn.classList.remove("mic-pulse");
        btn.dataset.recording = "false";
        if (VOICE_INPUT === newVI) VOICE_INPUT = null;  // 仅释放自己，不踩新 instance
      },
      onError: (err) => {
        btn.classList.remove("mic-pulse");
        btn.dataset.recording = "false";
        console.error("VoiceInput error:", err);
        _plan3Toast("语音识别失败：" + (err.message || err), "error");
      },
    });
    VOICE_INPUT = newVI;
    newVI.start();
  });
});

// ---------- Plan3 G3 TTS: fetchAndPlayTTS + auto-speak hook ----------

/**
 * POST /api/tts/synthesize → audio blob → HTMLAudioElement → play.
 * 单实例: 新一次调用会 pause 上一次的 audio (避免叠播)。
 * 失败 silent: TTS 是 enhancement, 不能让朗读失败 block 文本流程。
 */
async function fetchAndPlayTTS(text) {
  if (!text || !text.trim()) return;
  // 先停掉上一段
  if (CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (_) {}
    CURRENT_TTS_AUDIO = null;
  }
  let blob;
  try {
    const resp = await fetch("/api/tts/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, user_id: USER_ID }),
    });
    if (!resp.ok) {
      console.warn("TTS endpoint failed:", resp.status);
      return;
    }
    blob = await resp.blob();
  } catch (e) {
    console.warn("TTS fetch error:", e);
    return;
  }

  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  CURRENT_TTS_AUDIO = audio;
  // Plan3.5 Bug 4: 加 visible playing indicator (speaker icon pulse)
  const speakerBtn = document.getElementById("toggle-speaker");
  audio.addEventListener("ended", () => {
    URL.revokeObjectURL(url);
    if (CURRENT_TTS_AUDIO === audio) CURRENT_TTS_AUDIO = null;
    if (speakerBtn) speakerBtn.classList.remove("tts-playing");
  });
  audio.addEventListener("error", () => {
    URL.revokeObjectURL(url);
    if (CURRENT_TTS_AUDIO === audio) CURRENT_TTS_AUDIO = null;
    if (speakerBtn) speakerBtn.classList.remove("tts-playing");
  });
  audio.addEventListener("pause", () => {
    if (speakerBtn) speakerBtn.classList.remove("tts-playing");
  });
  try {
    await audio.play();
    if (speakerBtn) speakerBtn.classList.add("tts-playing");
  } catch (e) {
    // Plan3.5 Bug 4: 不再静默吞 reject——明确告诉用户「需点页面激活」。
    // 常见触发场景: 页面加载时 localStorage speakerOn=true,首次 auto-render
    // 触发 _maybeSpeakCurrentQuestion 在 user gesture activation 之前 → reject。
    // 用户接到 toast 提示后再点 toggle off-on 即可重新触发 (此时 click 本身
    // 是 user gesture)。
    console.warn("TTS autoplay blocked:", e);
    if (typeof _plan3Toast === "function") {
      _plan3Toast("浏览器阻止了语音自动播放,请点 🔈 关闭再打开重试", "warn");
    }
    URL.revokeObjectURL(url);
    if (CURRENT_TTS_AUDIO === audio) CURRENT_TTS_AUDIO = null;
    if (speakerBtn) speakerBtn.classList.remove("tts-playing");
  }
}

// 渲染当前问题时调用 (renderInterviewView / submitAnswer next-turn / startReplay)
function _maybeSpeakCurrentQuestion() {
  if (!state.speaker_on) return;
  if (!state.current_question) return;
  fetchAndPlayTTS(state.current_question);
}

// ---------- Plan3 G1 upload: XHR + progress + parsed_text 注入 ----------

document.getElementById("upload-btn")?.addEventListener("click", () => {
  const inp = document.getElementById("upload-input");
  if (inp) inp.click();
});

document.getElementById("upload-input")?.addEventListener("change", (ev) => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    _plan3Toast("文件过大（限 10MB）", "warn");
    ev.target.value = "";
    return;
  }

  const xhr = new XMLHttpRequest();
  const bar = document.getElementById("upload-progress");
  const warnDiv = document.getElementById("upload-warnings");
  const btn = document.getElementById("upload-btn");
  const originalBtnText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "解析中...";
  }

  xhr.upload.onprogress = (e) => {
    if (!bar || !e.lengthComputable) return;
    bar.classList.remove("hidden");
    bar.value = (e.loaded / e.total) * 100;
  };

  xhr.onload = () => {
    if (bar) {
      bar.classList.add("hidden");
      bar.value = 0;
    }
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalBtnText;
    }
    if (xhr.status === 200) {
      let resp;
      try { resp = JSON.parse(xhr.responseText); }
      catch (_) {
        _plan3Toast("解析响应失败", "error");
        return;
      }
      // Plan3 §7.4: parsed_text 注入到 view-material 的项目原文 textarea
      // (Q6 上传按钮位于 view-material; index.html 实际 id = material-input)
      const ta = document.getElementById("material-input");
      if (ta && typeof resp.parsed_text === "string") {
        ta.value = resp.parsed_text;
        // visual feedback: 把焦点移到 textarea, 提示用户已填好可继续
        ta.focus();
      }
      const warns = resp.parse_warnings || [];
      if (warnDiv) {
        if (warns.length) {
          warnDiv.textContent = "解析提示：" + warns.join("；");
          warnDiv.classList.remove("hidden");
        } else {
          warnDiv.textContent = "";
          warnDiv.classList.add("hidden");
        }
      }
      _plan3Toast(`已解析 ${file.name} (${(resp.parsed_text || "").length} 字)`, "info");
    } else {
      let detail = xhr.responseText || `HTTP ${xhr.status}`;
      try {
        const parsed = JSON.parse(detail);
        if (typeof parsed.detail === "string") detail = parsed.detail;
        else if (parsed.detail && typeof parsed.detail.message === "string") {
          detail = parsed.detail.message;
        } else if (parsed.detail) detail = JSON.stringify(parsed.detail);
      } catch (_) {}
      _plan3Toast(`上传失败 (${xhr.status})：${detail}`, "error");
    }
  };

  xhr.onerror = () => {
    if (bar) bar.classList.add("hidden");
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalBtnText;
    }
    _plan3Toast("网络错误，上传失败", "error");
  };

  xhr.open("POST", "/api/uploads");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("user_id", USER_ID);
  xhr.send(fd);

  // 重置 input 以允许重选同一文件 (input.change 不触发同值)
  ev.target.value = "";
});
