// AIIC MiMo Chat — single-page client
const STORAGE_KEY = "aiic.chat.v1";
const DEFAULT_MODEL = "mimo-v2.5-pro";

// ---------- state ----------
let state = loadState();
let abortCtl = null;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { conversations: [], activeId: null };
    const s = JSON.parse(raw);
    if (!s.conversations) s.conversations = [];
    return s;
  } catch (e) {
    console.error("loadState failed", e);
    return { conversations: [], activeId: null };
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function activeConv() {
  return state.conversations.find((c) => c.id === state.activeId) || null;
}

function newConv(model = DEFAULT_MODEL) {
  const conv = {
    id: crypto.randomUUID(),
    title: "新会话",
    model,
    messages: [],
  };
  state.conversations.unshift(conv);
  state.activeId = conv.id;
  saveState();
  renderAll();
}

function deleteConv(id) {
  state.conversations = state.conversations.filter((c) => c.id !== id);
  if (state.activeId === id) {
    state.activeId = state.conversations[0]?.id || null;
  }
  saveState();
  renderAll();
}

function renameConv(id, title) {
  const c = state.conversations.find((c) => c.id === id);
  if (!c) return;
  c.title = title;
  saveState();
  renderAll();
}

function switchConv(id) {
  state.activeId = id;
  saveState();
  renderAll();
}

// ---------- rendering ----------
function renderAll() {
  renderSidebar();
  renderMessages();
  renderTitle();
}

function renderSidebar() {
  const ul = document.getElementById("conv-list");
  ul.innerHTML = "";
  for (const c of state.conversations) {
    const li = document.createElement("li");
    if (c.id === state.activeId) li.classList.add("active");

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = c.title || "(空)";
    title.onclick = () => switchConv(c.id);

    const renameBtn = document.createElement("button");
    renameBtn.textContent = "✏";
    renameBtn.title = "重命名";
    renameBtn.onclick = (e) => {
      e.stopPropagation();
      const t = prompt("新标题", c.title);
      if (t) renameConv(c.id, t);
    };

    const delBtn = document.createElement("button");
    delBtn.textContent = "✕";
    delBtn.title = "删除";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      if (confirm(`删除会话 "${c.title}" ？`)) deleteConv(c.id);
    };

    li.append(title, renameBtn, delBtn);
    ul.appendChild(li);
  }
}

function renderMessages() {
  const box = document.getElementById("messages");
  box.innerHTML = "";
  const conv = activeConv();
  if (!conv) return;
  for (const m of conv.messages) {
    box.appendChild(renderMsg(m));
  }
  scrollToBottom();
}

function renderMsg(m) {
  const div = document.createElement("div");
  div.className = `msg ${m.role}`;
  if (m.role === "assistant" && window.marked) {
    div.innerHTML = window.marked.parse(m.content || "");
  } else {
    div.textContent = m.content;
  }
  return div;
}

function renderTitle() {
  const conv = activeConv();
  document.getElementById("conv-title").textContent = conv?.title || "";
  const picker = document.getElementById("model-picker");
  if (conv) picker.value = conv.model;
}

function scrollToBottom() {
  const box = document.getElementById("messages");
  box.scrollTop = box.scrollHeight;
}

// ---------- model picker ----------
async function loadModels() {
  const resp = await fetch("/api/models");
  const data = await resp.json();
  const picker = document.getElementById("model-picker");
  picker.innerHTML = "";
  for (const m of data.data) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.id;
    picker.appendChild(opt);
  }
  if (activeConv()) picker.value = activeConv().model;
  picker.onchange = () => {
    const c = activeConv();
    if (c) {
      c.model = picker.value;
      saveState();
    }
  };
}

// ---------- send / stream ----------
async function send() {
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text) return;

  let conv = activeConv();
  if (!conv) {
    newConv(document.getElementById("model-picker").value || DEFAULT_MODEL);
    conv = activeConv();
  }

  conv.messages.push({ role: "user", content: text });
  if (conv.title === "新会话" || !conv.title) {
    conv.title = text.slice(0, 24);
  }
  saveState();
  input.value = "";
  renderAll();

  const assistantMsg = { role: "assistant", content: "" };
  conv.messages.push(assistantMsg);
  saveState();

  const box = document.getElementById("messages");
  const msgEl = renderMsg(assistantMsg);
  box.appendChild(msgEl);
  scrollToBottom();

  setSending(true);
  abortCtl = new AbortController();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: conv.model,
        messages: conv.messages.slice(0, -1).map((m) => ({ role: m.role, content: m.content })),
        stream: true,
      }),
      signal: abortCtl.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        handleSseEvent(event, assistantMsg, msgEl);
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      assistantMsg.content += "\n\n[已停止]";
    } else {
      console.error(err);
      conv.messages.pop();
      conv.messages.push({ role: "error", content: String(err.message || err) });
      renderMessages();
      saveState();
      setSending(false);
      return;
    }
  } finally {
    abortCtl = null;
  }

  saveState();
  renderMsg(assistantMsg);
  if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content || "");
  setSending(false);
}

function handleSseEvent(eventText, assistantMsg, msgEl) {
  let isError = false;
  let dataLines = [];
  for (const line of eventText.split("\n")) {
    if (line.startsWith("event:") && line.includes("error")) isError = true;
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  const data = dataLines.join("\n");
  if (!data) return;
  if (isError) {
    assistantMsg.content += `\n\n[错误] ${data}`;
    msgEl.classList.add("error");
    if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content);
    else msgEl.textContent = assistantMsg.content;
    return;
  }
  if (data === "[DONE]") return;
  try {
    const obj = JSON.parse(data);
    const delta = obj.choices?.[0]?.delta?.content || "";
    if (delta) {
      assistantMsg.content += delta;
      if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content);
      else msgEl.textContent = assistantMsg.content;
      scrollToBottom();
    }
  } catch (e) {
    // 非 JSON data 行（如心跳），忽略
  }
}

function setSending(sending) {
  const btn = document.getElementById("send");
  if (sending) {
    btn.textContent = "停止";
    btn.classList.add("stop");
  } else {
    btn.textContent = "发送";
    btn.classList.remove("stop");
  }
}

// ---------- wiring ----------
document.getElementById("new-conv").onclick = () => {
  const model = document.getElementById("model-picker").value || DEFAULT_MODEL;
  newConv(model);
};
document.getElementById("send").onclick = () => {
  if (abortCtl) abortCtl.abort();
  else send();
};
document.getElementById("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (abortCtl) abortCtl.abort();
    else send();
  }
});

// ---------- init ----------
(async function init() {
  await loadModels();
  if (state.conversations.length === 0) newConv();
  else renderAll();
})();
