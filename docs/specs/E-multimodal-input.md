# Spec E — Plan3 多模态输入：文件上传 / 语音输入 / 语音输出 / 双独立 toggle

> 起草日期：2026-05-10
> 父文档：[../overview.md](../overview.md)
> 上游依赖：v2 已交付状态 + [Spec D (Plan2)](D-plan2-long-term-training.md) 的 anonymous user_id + UserProfile 持久化机制
> 范围：Plan3 = G1 + G2 + G3 + G4 + G5 五条 feature

---

## 1. 范围

### 1.1 In-scope

| 编号 | feature | 一句话 |
|---|---|---|
| **G1** | 文件上传（Onboarding material） | PDF/Word/MD/纯文本 → 后端 PyMuPDF / python-docx 解析 → 注入 onboarding 现有 textarea，用户可编辑后提交 |
| **G2** | STT 语音输入（Chrome `webkitSpeechRecognition`） | onboarding chat / interview answer / resume_iterate 三个 textarea 各加 mic 按钮；麦克风 toggle on 时按钮可点击启用 |
| **G3** | TTS 语音输出（MiMo `mimo-v2.5-tts`） | view-interview 渲染 Interviewer 问题时，扬声器 toggle on 自动调后端 → 返回音频 → Audio 元素播放 |
| **G4** | 麦克风 / 扬声器 双独立 toggle | nav header 两个 icon button（🎤 / 🔈）；localStorage 持久化；中途切换立即生效 |
| **G5** | TTS 后端封装（services/tts.py） | OpenAI 兼容 `POST /v1/audio/speech` 调用 + retry once on network error + 失败 503 |

### 1.2 Out-of-scope（YAGNI）

- 「我的资料库」UI（用户面访曾上传文件 / 重新引用）
- OCR 图片简历 / 手写笔记识别
- 视频项目介绍上传
- 跨浏览器 STT fallback（Safari / Firefox / mobile）
- 服务端 STT（MiMo / Whisper / DeepSeek 等）
- TTS voice 多选 / 男女声 / 情感语调（默认 voice 一种；schema 留接口字段，UI 不暴露）
- 实时打断面试官（用户开口时 TTS 自动暂停）
- STT 多语言混合 explicit 切换（默认 zh-CN，混入英文术语自然识别）
- 上传文件版本管理 / 历史回看
- 跨设备文件同步 / 用户 ID 导出导入
- F4 简历多轮迭代支持上传 PDF（Plan2 维持 textarea 粘贴；Plan3 不扩展到 resume_iterate flow）

---

## 2. 设计哲学

> Plan2 立"长期训练"维度。Plan3 立"**沉浸 + 低 friction**"维度，让 ProjectProbe 比 ChatGPT 更接近真实面试体验。

ChatGPT 能用语音 + 上传 PDF，但它们与训练逻辑**解耦**：

| ChatGPT 能力 | 局限 |
|---|---|
| 朗读响应 | 朗读的是任意输出，没有"面试官"角色一致性 |
| 麦克风输入 | 输入仅作为文字喂给同一对话，不驱动状态机推进 |
| PDF 上传 | 上传后用户还得自描述要训练什么；项目结构不被识别 |

Plan3 让这三个能力**直接服务**项目深挖状态机：

| feature | ChatGPT 做不到 |
|---|---|
| G1 上传 | 解析后直接进 onboarding → coach.plan → 状态机；用户改完 textarea 即"开始面试" |
| G2 STT | 麦克风讲完一答 → 直接驱动 Interviewer.next_turn → 触发 missing_slot 检测 |
| G3 TTS | 朗读的是 Interviewer 角色的追问，扮演陌生面试官 |
| G4 toggle | 一键切换"训练营模式"，UX 一致性强 |

每条都直接服务评分核心句"相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试"。

---

## 3. 用户身份机制

**完全沿用 Plan2 已建立的 anonymous user_id 机制**：

- 前端：`localStorage.userId`（Plan2 P11 已实施）
- 后端：所有 POST 请求 body 加 `user_id: str = "anonymous"`（Plan2 已实施）
- 上传文件按 user_id 隔离存储

无新身份字段。Plan3 不引入登录 / 跨设备同步等机制。

---

## 4. 持久化布局

### 4.1 文件结构

在 v2 + Plan2 已有的 `data/` 基础上扩展：

```
data/
├── sessions/<session_id>.json           # v2
├── users/<user_id>.json                  # Plan2
├── uploads/<user_id>/                    # Plan3 新增
│   ├── <file_id>.pdf                     # 原文件（白名单 ext）
│   ├── <file_id>.json                    # UploadedFile 元数据
│   └── ...
└── question_bank.{seed,synthetic}.json   # v2
```

`<file_id>` = uuid v4；磁盘文件名永远只用 file_id + 白名单 ext，原 filename 只入元数据，避免路径注入。

### 4.2 .gitignore 新增

`.gitignore` 在 Plan2 P0 已加 `data/users/*.json`，Plan3 P0 追加：

```
# Plan3: per-user upload files (raw + metadata)
data/uploads/**
!data/uploads/.gitkeep
```

### 4.3 配额

- **单文件 ≤ 10MB**：项目 PDF 一般 1-5MB，留 margin；前端验证 + 后端 FastAPI body limit 双层校验
- **单 user 总配额 ≤ 50MB**：5 个项目材料约 25MB，留 buffer；超限返回 413 Payload Too Large
- **白名单 ext**：`.pdf` / `.docx` / `.md` / `.txt`；`.doc` (legacy binary) 拒绝并提示"导出为 .docx 或 PDF"

### 4.4 兼容性

- 不存在 `data/uploads/` 目录时，FileStore 启动时自动 mkdir
- 不影响 v2 / Plan2 现有 sessions / users 文件

---

## 5. 数据契约新增（services/schemas.py）

### 5.1 UploadedFile（新）

```python
class UploadedFile(BaseModel):
    file_id: str                          # uuid v4
    user_id: str
    original_filename: str                 # 仅 metadata 显示用
    file_type: Literal["pdf","docx","md","txt"]
    size_bytes: int
    uploaded_at: datetime
    parsed_text: str                       # 解析后文本，注入 textarea 用
    parse_warnings: list[str] = []         # 如 "PDF 含图片，OCR 跳过"
```

### 5.2 UploadResponse（新；endpoint 返回 schema）

```python
class UploadResponse(BaseModel):
    file_id: str
    parsed_text: str
    file_type: str
    parse_warnings: list[str] = []
```

### 5.3 TTSRequest（新；endpoint 入参）

```python
class TTSRequest(BaseModel):
    text: str                              # 1 ≤ len ≤ 4000
    voice: str = "default"                 # 留接口字段；UI 当前不暴露
    user_id: str = "anonymous"
```

### 5.4 不修改既有 schema

Plan3 不动 v2 / Plan2 的 InterviewPacket / SessionMeta / UserProfile / EvaluationReport。文件上传后解析结果走 onboarding/material textarea，进入下一步 coach.plan 路径完全不变。

---

## 6. API 接口（新增）

### 6.1 新增

| Endpoint | 方法 | 输入 → 输出 |
|---|---|---|
| `/api/uploads` | POST multipart | `file: UploadFile` + `user_id: str = Form("anonymous")` → `UploadResponse` |
| `/api/tts/synthesize` | POST JSON | `TTSRequest` → `audio/mpeg` 音频流 |

### 6.2 错误码

**`/api/uploads`**：
- 200：上传 + 解析成功
- 400：file_type 不在白名单 / 空文件 / `.doc` legacy
- 413：单文件超过 10MB 或 user 配额超限
- 422：文件读到了但解析失败（如 PDF 加密 / .docx 损坏）；返回 detail 包含 parse_warnings

**`/api/tts/synthesize`**：
- 200：返回 `audio/mpeg` Content-Type 的音频流
- 422：text 为空或超过 4000 字
- 503：MiMo 上游不可用 / retry 后仍失败；前端在 fetch 层 catch → 静默降级（文字仍渲染）

### 6.3 不修改既有 endpoint

Plan2 P7 给 6 个 POST endpoint 加的可选 `user_id` 字段保持；Plan3 上传 endpoint 用 multipart Form 字段透传同一 user_id。

---

## 7. G1 文件上传 flow

### 7.1 用户路径

1. view-onboarding（Plan2 已有 view）现有 textarea 旁加「上传文件」按钮
2. 用户选择文件（input accept=".pdf,.docx,.md,.txt"）
3. 前端 multipart POST `/api/uploads`
4. 上传中显示 progress bar（XHR upload progress 事件）
5. 后端：校验 ext / size / 配额 → 存 `data/uploads/<user_id>/<file_id>.<ext>` → 调 `parse_file` → 写 `<file_id>.json` 元数据 → 返回 `UploadResponse`
6. 前端：把 `parsed_text` 填进现有 textarea；`parse_warnings` 显示在下方淡黄提示框
7. 用户编辑 textarea（修复解析错位、补充上下文等）
8. 点「下一步」→ 进入 Plan2 已有的 coach.plan → start 流程，**不变**

### 7.2 后端流程

```python
@app.post("/api/uploads", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
):
    # 1. 校验 ext 白名单
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "docx", "md", "txt"}:
        raise HTTPException(400, "unsupported file type")

    # 2. 校验 size（streaming check）
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 10MB)")

    # 3. 校验 user 配额
    user_dir = DATA_DIR / "uploads" / user_id
    used = sum(p.stat().st_size for p in user_dir.glob("*") if p.is_file()) if user_dir.exists() else 0
    if used + len(contents) > 50 * 1024 * 1024:
        raise HTTPException(413, "user quota exceeded (max 50MB)")

    # 4. 生成 file_id 并落盘
    file_id = str(uuid.uuid4())
    user_dir.mkdir(parents=True, exist_ok=True)
    raw_path = user_dir / f"{file_id}.{ext}"
    raw_path.write_bytes(contents)

    # 5. 解析
    try:
        parsed_text, warnings = await parse_file(raw_path, ext)
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        raise HTTPException(422, f"parse failed: {e}")

    # 6. 写元数据
    meta = UploadedFile(
        file_id=file_id, user_id=user_id,
        original_filename=file.filename or "unknown",
        file_type=ext, size_bytes=len(contents),
        uploaded_at=datetime.now(),
        parsed_text=parsed_text, parse_warnings=warnings,
    )
    (user_dir / f"{file_id}.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    return UploadResponse(
        file_id=file_id, parsed_text=parsed_text,
        file_type=ext, parse_warnings=warnings,
    )
```

### 7.3 services/file_parse.py

```python
"""File parsing module — Plan3 G1."""
from pathlib import Path

import fitz  # PyMuPDF


async def parse_file(path: Path, file_type: str) -> tuple[str, list[str]]:
    """根据 file_type 分发；返回 (parsed_text, warnings)。"""
    if file_type == "pdf":
        return _parse_pdf(path)
    if file_type == "docx":
        return _parse_docx(path)
    if file_type in ("md", "txt"):
        return path.read_text(encoding="utf-8"), []
    raise ValueError(f"unsupported file_type: {file_type}")


def _parse_pdf(path: Path) -> tuple[str, list[str]]:
    """PyMuPDF 抽取页面文本。图片 + OCR 跳过，warnings 提示。"""
    warnings: list[str] = []
    chunks: list[str] = []
    with fitz.open(path) as doc:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted; please remove password protection")
        for i, page in enumerate(doc):
            txt = page.get_text("text")
            chunks.append(txt)
            # 检测图片但不 OCR
            if page.get_images():
                warnings.append(f"page {i+1} contains images (OCR not performed)")
    return "\n\n".join(chunks).strip(), warnings


def _parse_docx(path: Path) -> tuple[str, list[str]]:
    """python-docx 抽取段落 + 表格。"""
    from docx import Document
    warnings: list[str] = []
    doc = Document(str(path))
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    for t in doc.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
        if doc.tables:
            warnings.append("docx contains tables (rendered as plain text rows)")
            break  # 只报一次 warning
    return "\n\n".join(parts).strip(), warnings
```

### 7.4 前端 UI（在 onboarding/material 视图）

```html
<div class="upload-row">
  <input type="file" id="upload-input" accept=".pdf,.docx,.md,.txt" hidden>
  <button id="upload-btn">📎 上传项目材料（PDF / Word / Markdown / TXT）</button>
  <progress id="upload-progress" class="hidden" max="100" value="0"></progress>
  <div id="upload-warnings" class="warnings hidden"></div>
</div>
<textarea id="material-textarea" placeholder="或直接粘贴你的项目描述..."></textarea>
```

```javascript
document.getElementById('upload-btn').addEventListener('click',
  () => document.getElementById('upload-input').click());

document.getElementById('upload-input').addEventListener('change', async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    showToast('文件过大（限 10MB）'); return;
  }

  const xhr = new XMLHttpRequest();
  xhr.upload.onprogress = (e) => {
    const pct = (e.loaded / e.total) * 100;
    const bar = document.getElementById('upload-progress');
    bar.classList.remove('hidden');
    bar.value = pct;
  };
  xhr.onload = () => {
    document.getElementById('upload-progress').classList.add('hidden');
    if (xhr.status === 200) {
      const resp = JSON.parse(xhr.responseText);
      document.getElementById('material-textarea').value = resp.parsed_text;
      const w = document.getElementById('upload-warnings');
      if (resp.parse_warnings.length) {
        w.textContent = '解析提示：' + resp.parse_warnings.join('; ');
        w.classList.remove('hidden');
      } else {
        w.classList.add('hidden');
      }
    } else {
      showToast(`上传失败：${xhr.status} ${xhr.responseText}`);
    }
  };
  xhr.open('POST', '/api/uploads');
  const fd = new FormData();
  fd.append('file', file);
  fd.append('user_id', USER_ID);
  xhr.send(fd);
});
```

注意：用 XHR 而不是 fetch 是为了拿 upload progress（fetch 当前还无 upload progress 标准支持）。

---

## 8. G2 STT 语音输入（Chrome 原生）

### 8.1 浏览器 API

`window.SpeechRecognition || window.webkitSpeechRecognition`（Chrome 上是 `webkitSpeechRecognition`）。

设置：
- `lang = 'zh-CN'`（中文为主，混入英文术语 Chrome 自动音译近似处理）
- `continuous = true`（讲长答案不被自动切断）
- `interimResults = true`（流式 partial 实时显示）

### 8.2 web/app.js 封装

```javascript
class VoiceInput {
  constructor(textarea) {
    this.textarea = textarea;
    this.recognition = null;
    this.isRecording = false;
    this.commitedText = '';  // 已 final 的文本
  }

  start() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      showToast('浏览器不支持语音识别（请用 Chrome）');
      return false;
    }
    this.recognition = new SR();
    this.recognition.lang = 'zh-CN';
    this.recognition.continuous = true;
    this.recognition.interimResults = true;

    this.commitedText = this.textarea.value;
    if (this.commitedText && !this.commitedText.endsWith(' ')) this.commitedText += ' ';

    this.recognition.onresult = (event) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += t;
        else interim += t;
      }
      if (final) this.commitedText += final;
      this.textarea.value = this.commitedText + interim;
    };

    this.recognition.onerror = (e) => {
      showToast('语音识别错误：' + e.error);
      this.stop();
    };

    this.recognition.onend = () => {
      // continuous=true 模式下被浏览器中断（如静音 30s），重启
      if (this.isRecording) try { this.recognition.start(); } catch (e) {}
    };

    this.recognition.start();
    this.isRecording = true;
    return true;
  }

  stop() {
    this.isRecording = false;
    if (this.recognition) {
      try { this.recognition.stop(); } catch (e) {}
      this.recognition = null;
    }
  }
}
```

### 8.3 三个 textarea 集成

每个 textarea 旁加 mic 按钮（onboarding chat / interview answer / resume_iterate textarea）：

```html
<div class="textarea-with-mic">
  <textarea id="..."></textarea>
  <button class="mic-btn" data-target-textarea="...">🎤</button>
</div>
```

按钮 click handler：
- 检查 `state.mic_on`（全局麦克风 toggle 状态）
- toggle off → 按钮置灰，点击不响应
- toggle on：
  - 当前不在录音 → 实例化 VoiceInput + start()，按钮显示红色 pulse 动画
  - 当前在录音 → stop()，按钮恢复正常

```javascript
document.querySelectorAll('.mic-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    if (!state.mic_on) {
      showToast('请先开启麦克风模式');
      return;
    }
    const targetId = btn.dataset.targetTextarea;
    const ta = document.getElementById(targetId);
    if (btn.dataset.recording === 'true') {
      VOICE_INPUT?.stop();
      btn.dataset.recording = 'false';
      btn.classList.remove('mic-pulse');
    } else {
      VOICE_INPUT = new VoiceInput(ta);
      if (VOICE_INPUT.start()) {
        btn.dataset.recording = 'true';
        btn.classList.add('mic-pulse');
      }
    }
  });
});
```

### 8.4 隐私与权限

- 第一次点 mic → 浏览器弹麦克风授权 prompt
- 拒绝授权 → onerror 触发 → toast 提示「请在浏览器设置允许麦克风」
- 不持久化任何录音；流仅在内存里走 Chrome → Google STT 端

---

## 9. G3 TTS 语音输出（MiMo）

### 9.1 services/tts.py

```python
"""MiMo TTS — Plan3 G3.

OpenAI 兼容 POST /v1/audio/speech，返回 audio bytes。
"""
import os

import httpx


async def synthesize_speech(
    text: str,
    voice: str = "default",
    *,
    timeout: float = 30.0,
) -> bytes:
    """调 MiMo audio.speech；retry once on httpx.NetworkError；
    成功返 bytes；失败 raise httpx.HTTPError 让 endpoint 层处理。"""
    api_key = os.environ["MIMO_API_KEY"]
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-tts")

    url = f"{base_url}/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}

    async def _call():
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content

    try:
        return await _call()
    except httpx.NetworkError:
        return await _call()  # retry once
```

### 9.2 endpoint

```python
from fastapi.responses import Response
from services.tts import synthesize_speech

@app.post("/api/tts/synthesize")
async def tts_synthesize(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(422, "text is empty")
    if len(req.text) > 4000:
        raise HTTPException(422, "text too long (max 4000 chars)")
    try:
        audio = await synthesize_speech(req.text, req.voice)
    except Exception:
        raise HTTPException(503, "TTS upstream unavailable")
    return Response(content=audio, media_type="audio/mpeg")
```

### 9.3 前端 helper

```javascript
let CURRENT_TTS_AUDIO = null;

async function fetchAndPlayTTS(text) {
  // 停掉前一个（如还在播）
  if (CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (e) {}
    CURRENT_TTS_AUDIO = null;
  }

  let res;
  try {
    res = await fetch('/api/tts/synthesize', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, user_id: USER_ID}),
    });
  } catch (e) {
    console.warn('TTS fetch failed', e);
    return;  // 静默降级
  }

  if (!res.ok) {
    console.warn('TTS HTTP', res.status);
    return;  // 静默降级
  }

  const blob = await res.blob();
  const audio = new Audio(URL.createObjectURL(blob));
  CURRENT_TTS_AUDIO = audio;
  audio.play().catch(e => console.warn('TTS audio.play() rejected', e));
}
```

### 9.4 view-interview 集成

Interviewer 问题渲染时（Plan2 已有 renderInterview 函数）：

```javascript
function renderInterviewerQuestion(q) {
  // ... v2 已有 DOM 渲染逻辑 ...
  if (state.speaker_on) {
    fetchAndPlayTTS(q);
  }
}
```

view 切换 / 用户主动停止时：

```javascript
function switchView(name) {
  if (CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (e) {}
    CURRENT_TTS_AUDIO = null;
  }
  // ... v2 已有 view 切换逻辑 ...
}
```

### 9.5 cost 控制

- 每次 Interviewer 问题约 50-100 字
- 一轮面试约 10 轮 → 10 次 TTS 调用 → 约 800 字
- MiMo 计费按字符或秒，预估单次面试 < ¥0.5
- **不做 server 端 cache**（每次问题不同，cache 命中率几乎 0）
- 加 per-user 日 quota：默认 200 次/日，超限 endpoint 返回 503（与 MiMo 上游故障同 code，前端静默降级）

---

## 10. G4 双独立 toggle

### 10.1 UI

nav header（Plan2 已有共享 header 区）加两个 icon button：

```html
<button id="toggle-mic" class="nav-toggle" title="麦克风模式">🎤</button>
<button id="toggle-speaker" class="nav-toggle" title="扬声器模式">🔈</button>
```

CSS 状态：
- on：背景 `--accent`，icon 实色
- off：背景透明，icon 半透明

### 10.2 状态管理

```javascript
state.mic_on = (localStorage.getItem('micOn') === 'true');
state.speaker_on = (localStorage.getItem('speakerOn') === 'true');

document.getElementById('toggle-mic').addEventListener('click', () => {
  state.mic_on = !state.mic_on;
  localStorage.setItem('micOn', state.mic_on);
  updateMicToggleVisual();
  if (!state.mic_on && VOICE_INPUT?.isRecording) {
    VOICE_INPUT.stop();  // 切 off 立即停掉正在录的
  }
});

document.getElementById('toggle-speaker').addEventListener('click', () => {
  state.speaker_on = !state.speaker_on;
  localStorage.setItem('speakerOn', state.speaker_on);
  updateSpeakerToggleVisual();
  if (!state.speaker_on && CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (e) {}
    CURRENT_TTS_AUDIO = null;
  }
});
```

### 10.3 默认值

- 第一次访问：mic_on = false, speaker_on = false
- 隐私 friendly：不会在用户没明示同意前激活麦克风
- localStorage 持久化：第二次访问保留上次状态

### 10.4 中途切换语义

- mic_on 切 on：mic 按钮立即可点击，不自动激活录音（per Round 2 user 决定）
- mic_on 切 off：所有 mic 按钮置灰；正在录音的立即 stop
- speaker_on 切 on：下一次 Interviewer 出问题时自动播
- speaker_on 切 off：当前正在播的立即 pause，未来问题不再播

---

## 11. 测试策略

### 11.1 新 unit tests（services/）

`tests/test_file_parse.py`：
- PDF 简单 sample → 抽到文本，warnings 空
- PDF 含图片 → warnings 含 "page X contains images"
- PDF 加密 → raise ValueError "PDF is encrypted"
- .docx 简单 sample → 文本 + 表格行
- .docx 含表格 → warnings 含 "docx contains tables"
- .md / .txt → 直接 read_text 内容
- 不支持 ext → raise ValueError

`tests/test_tts_module.py`：
- mock httpx → 返 audio bytes 成功
- mock httpx network error → retry once → 第二次成功 → 返 bytes
- mock httpx 一直 network error → 抛 NetworkError（让 endpoint 层 catch）
- 缺 MIMO_API_KEY env → KeyError

`tests/test_schemas_plan3.py`：
- UploadedFile / UploadResponse / TTSRequest 默认值 + 字段验证
- TTSRequest text 空字符串通过 schema（在 endpoint 层校验非空）

### 11.2 新 endpoint tests（server/）

`tests/test_endpoints_uploads.py`：
- POST /api/uploads .pdf happy → 200 + parsed_text
- .docx happy → 200
- .md / .txt happy → 200
- ext 在白名单外 (.exe / .doc) → 400
- file size > 10MB → 413
- user 配额超限 → 413
- 加密 PDF → 422 + detail 含 "encrypted"

`tests/test_endpoints_tts.py`：
- POST /api/tts/synthesize happy → 200 + Content-Type: audio/mpeg
- 空 text → 422
- text > 4000 字 → 422
- mock MiMo 一直挂 → 503

### 11.3 集成 test

`tests/test_plan3_loop.py`：
- 上传 PDF → /api/uploads 返 parsed_text
- 用 parsed_text 走 onboarding → coach.plan → start 全链路（mock LLM）
- view-interview 渲染问题 → 检查 fetch /api/tts/synthesize 被调一次（mock）

### 11.4 前端手动 e2e

```
1. 起服务，Chrome 打开
2. 看到 nav 多了 🎤 + 🔈 两个 toggle 按钮，初始都灰
3. 进 onboarding → material 视图
4. 看到「📎 上传项目材料」按钮 + 现有 textarea
5. 点上传 → 选 PDF → progress bar 走完 → textarea 填解析文本 + warnings 显示（如有）
6. 修改 textarea 中部分内容 → 点「下一步」
7. 进 view-interview，看到 Interviewer 第一问
8. 点 🔈 toggle → 听到第一问被朗读
9. 点 🎤 toggle → 看到 textarea 旁 mic 按钮变彩色可点
10. 点 mic → 浏览器授权麦克风 → 红色 pulse 动画 → 讲一段话 → textarea 实时显示 partial → 停讲 final → 再点 mic 停
11. submit 答案 → 下一问 → 自动朗读
12. 点 🔈 toggle off → 当前朗读立即静音
13. 点 🎤 toggle off → mic 按钮变灰
14. 上传 .docx 测试
15. 上传 11MB 文件 → 前端 toast 拒绝
16. 上传 .exe → 前端 input accept 过滤 + 后端二次校验
```

### 11.5 维护现有

v2 + Plan2 现有 tests 全部继续 pass。Plan3 不修改既有 schemas / endpoints，所以应当无冲突；如有 break 视为实施 bug。

---

## 12. 风险 + 兜底

| 风险 | 兜底 |
|---|---|
| MiMo TTS 接口挂 / 超时 / 余额不足 | endpoint 503 + 前端静默降级（不打断面试，文字仍渲染） |
| MiMo TTS 字符 cost 累积 | per-user 日 quota（默认 200 次/日）；超限 503 |
| Chrome `webkitSpeechRecognition` Google 端鉴权失败 / 离线 | mic 按钮 onerror → toast「语音识别需联网，已切回文字」；不阻塞继续 |
| PyMuPDF PDF 解析乱码 / 表格丢字 | parse_warnings 提示用户；用户可手改 textarea |
| python-docx 不支持 `.doc` 二进制 | 上传时 `accept=".docx"`；后端再校验 ext，`.doc` → 400 + 提示 |
| 上传文件路径注入 / 文件名攻击 | 磁盘文件名永远是 `<file_id>.<ext>`（uuid + 白名单 ext），原 filename 只入元数据 |
| 同 user 频繁上传塞满磁盘 | per-user 配额 50MB；超限 413 |
| 麦克风权限被浏览器拒绝 | onerror toast「请在浏览器设置允许麦克风」 |
| TTS 音频长度过长（用户切换 view 仍在播） | view 切换 / toggle off 时 `currentTTSAudio?.pause()` |
| STT 浏览器 30s 静音自动 stop | onend 重启 recognition（如 isRecording=true） |
| Plan2 与 Plan3 并行实施 schemas/server/main.py 冲突 | Plan3 等 Plan2 P0-P16 全部 ship + 部署上线 + 用户 review 通过后才起跑实施 |
| MiMo TTS voice 名变更 / 模型下线 | tts.py `voice="default"` + 环境变量 `MIMO_MODEL` 兜底；schema 留接口字段易扩展 |
| 文件上传 multipart 体积过大 OOM | FastAPI 默认 body_size_limit；nginx `client_max_body_size 12M;`（留 margin） |
| .docx 含恶意 macro / xss | python-docx 只读文本不执行 macro；上传后立即解析 + 不在浏览器渲染原文件 |

---

## 13. v2 + Plan2 兼容性

### 13.1 schema 兼容

- Plan3 仅新增 3 个 schema（UploadedFile / UploadResponse / TTSRequest），不动 v2 / Plan2 既有 schema
- v2 / Plan2 现有 session / user JSON 文件不受影响

### 13.2 endpoint 兼容

- 新 2 个 endpoint 不冲突现有路径
- 现有 endpoint 全部不变

### 13.3 前端兼容

- 沿用 Plan2 已建的 USER_ID + apiPost / apiGet helpers
- 新 toggle 按钮 + mic / speaker UI 是增量；不影响现有 5 视图（home / onboarding / material / interview / report）+ Plan2 的 view-profile 第 6 视图

### 13.4 部署兼容

- 新增 `data/uploads/` 目录，server 层 mkdir 自动创建
- 不需数据库迁移
- nginx `client_max_body_size` 需调到 ≥ 12M（默认 1M），是部署侧改动；deployment.md 新增条目记录

### 13.5 实施前置条件（硬约束）

**Plan3 实施必须等 Plan2 P0-P16 全部 ship + 部署上线 + 用户 review 通过后才起跑**。原因：
- Plan3 改动 `services/schemas.py` / `server/main.py` / `web/index.html` / `web/app.js` / `web/styles.css`，与 Plan2 多处重叠
- 并行实施会产生 merge 冲突 + 测试 baseline 不稳
- Plan3 spec / plan **可以现在就写**（不动代码，纯 maintainer 决策）

---

## 14. 实施依赖图

```
schemas.py (Plan3 新 3 个 schema)
   ↓
   ├──── file_parse.py     (PyMuPDF + python-docx)
   ├──── tts.py            (MiMo httpx async)
   ↓
server/main.py
   ├──── POST /api/uploads
   └──── POST /api/tts/synthesize
   ↓
web/index.html (mic + speaker toggle + 上传按钮 + 三 textarea mic 按钮)
   ↓
web/app.js
   ├──── VoiceInput class
   ├──── fetchAndPlayTTS helper
   ├──── upload XHR + progress
   └──── toggle 状态管理
   ↓
web/styles.css (mic pulse / toggle 态 / 上传 progress bar)
   ↓
集成 smoke + 部署
```

实施顺序：`schemas → file_parse + tts (并行) → server endpoints (串行) → web (HTML/JS/CSS 串行) → tests + 部署`

详细 task 拆分由 writing-plans skill 起草到 `docs/plans/Plan3-multimodal-input.md`。

### 新增依赖

`pixi.toml`：
- 新增 `python-docx`（PyMuPDF 已在 v1 期间装）
- 不引入 OCR / Whisper / 等大依赖

---

## 15. 评分自检（每条 feature 必答）

> 「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」

| feature | 答案 |
|---|---|
| G1 文件上传 | ChatGPT 也能上传 PDF 但用户还得自描述要训练；ProjectProbe 解析 → 直接进 onboarding → coach.plan → 状态机 |
| G2 STT | ChatGPT 麦克风输入仅作为文字喂给同一对话；ProjectProbe STT 结果直接驱动 Interviewer.next_turn → 触发 missing_slot 检测 |
| G3 TTS | ChatGPT 朗读响应没有"面试官"角色一致性；ProjectProbe 朗读的是 Interviewer 角色追问，沉浸感对齐"模拟陌生面试官"设计哲学 |
| G4 双 toggle | ChatGPT 无场景化模式切换；ProjectProbe 一键进"面试训练营"模式，UX 一致性强 |
| G5 TTS 后端封装 | 工程基础，不直接对评分句；服务 G3 |

每条都过关。
