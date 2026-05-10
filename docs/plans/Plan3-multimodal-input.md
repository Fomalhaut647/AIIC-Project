# AIIC v2 Plan3 — Multimodal Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 [Spec E](../specs/E-multimodal-input.md) 全部 5 条 feature（G1 文件上传 + G2 STT + G3 TTS + G4 双独立 toggle + G5 TTS 后端封装），让 ProjectProbe 立"沉浸 + 低 friction"差异化维度。

**Architecture:** 在 v2 + Plan2 已有 services + server + web 三层基础上增量扩展。引入 anonymous user_id-aware 文件上传 + Chrome 原生 STT 前端搞定 + MiMo TTS 后端封装；新增 `services/file_parse.py`（PDF/Word/MD/txt 分发）+ `services/tts.py`（OpenAI 兼容 audio.speech）；server 加 2 endpoint；web 加 2 toggle + 上传按钮 + 三 textarea mic 按钮 + view-interview TTS 自动播。

**Tech Stack:** Python (Pixi) / Pydantic v2 / httpx async / FastAPI / vanilla JS / Web Speech API / pytest

**Pre-conditions:**

### 实施策略：worktree 并行 + frontend sync point（maintainer 决定）

**Spec E §13.5 原本要求 Plan3 等 Plan2 P0-P16 全部 ship 才起跑**，但 maintainer 决定用 git worktree 并行实施 Plan2/3。本 plan 据此调整：

```
main             A → B → C → D → ... (Plan2 P0-P16 在 main 串行推进)
worktree-plan3   A → Q0 → Q1 → ... → Q5 → ⏸ (sync) → Q6 → Q7 → Q8 → Q9
                 ↑                  ↑       ↑
                 branch off main    backend 完成   等 Plan2 frontend (P10-P14) ship
                                                 后 rebase 到最新 main 再起 frontend
```

- **worktree branch**：`feat/plan3-multimodal-input`，从当前 main HEAD 分出（已含 Plan2 P0-P7）
- **Q0-Q5（backend + endpoints）可立即并行**：与 Plan2 P8-P14 不冲突。文件冲突点：
  - `services/schemas.py`：Plan3 末尾追加 3 个新 schema，Plan2 已稳定该文件 → 冲突可加性合并
  - `server/main.py`：Plan2 P8/P9 加 5 个新 endpoint，Plan3 加 2 个不同 endpoint → 冲突可加性合并
- **Q6-Q8（web/）必须 sync**：Plan3 frontend 工作前等 Plan2 P10-P14 全部 merge 到 main，然后 worktree rebase 到最新 main，在 Plan2 frontend 已 ship 的基础上加 Plan3 frontend
- **Q9 部署**：等 Plan2 P16 也完成，最终 worktree 合到 main 一并部署

**已有外部状态**：

- `.env` 已含 `MIMO_API_KEY` / `MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1` / `MIMO_MODEL=mimo-v2.5-tts`（maintainer 已配）
- main 上 4 个 v2 in-progress modified files（services/coach.py / llm.py / web/app.js / web/index.html）由 Plan2 teammate 视情况处理；Plan3 teammate worktree 独立分支不受影响
- pixi.toml 已含 `pymupdf >=1.27.2.2,<2`（PDF 解析复用）；新增 `python-docx` 依赖在 Q0 加

**测试约定**：

- v2 + Plan2 现有 tests 都必须 pass（Plan3 不改既有）
- 每 task 严格 TDD：写 RED test → 跑 RED → 实现 → 跑 GREEN → commit
- frontend 视觉 task 允许 RED test 写为 "DOM id / class 契约存在性 + 数据流 hook 调用次数" 层级，而非像素回归测试
- frontend task implementer subagent 起手必须 invoke `frontend-design:frontend-design`（与 Plan2 P10-P14 同要求）

**Spec coverage:**

| Spec E 节 | Plan task |
|---|---|
| §1 范围（5 features） | Q0-Q9 全覆盖 |
| §2 设计哲学 | — 不直接对应 task；commit message 引用 |
| §3 用户身份机制 | 沿用 Plan2 已实施；不新增 |
| §4 持久化布局 | Q0（目录 + .gitignore） |
| §5 数据契约（3 新 schema） | Q1 |
| §6 API 接口（2 新 endpoint） | Q4（uploads）+ Q5（tts） |
| §7 G1 文件上传 | Q2（file_parse）+ Q4（endpoint）+ Q6（前端 upload UI） |
| §8 G2 STT | Q7（VoiceInput class）+ Q6（mic 按钮 DOM） |
| §9 G3 TTS | Q3（tts.py）+ Q5（endpoint）+ Q7（fetchAndPlayTTS） |
| §10 G4 双 toggle | Q6（DOM）+ Q7（状态管理） |
| §11 测试策略 | 散落各 task + Q9 集成 smoke |
| §12 风险 + 兜底 | Q3（retry on network error）+ Q4（白名单/配额）+ Q5（503 fallback）+ Q7（onerror 处理） |
| §13 v2/Plan2 兼容性 | 不修改既有 schema/endpoint/视图；Q9 验证既有 tests pass |
| §14 实施依赖图 | Q0-Q9 task 顺序匹配 |
| §15 评分自检 | commit message + Plan3-report |

---

### Task Q0: worktree 准备 + 依赖 + .gitignore + data/uploads

**Files:**
- Create: `data/uploads/.gitkeep`
- Modify: `.gitignore`, `pixi.toml`

**Pre-conditions for this task**：当前 cwd 是 worktree（`/home/ubuntu/AIIC-Project-plan3` 或 `git worktree add` 出的目录），HEAD 在 `feat/plan3-multimodal-input` branch。

- [ ] **Step 1: 验证 worktree branch 状态**

```bash
git branch --show-current
git rev-parse --abbrev-ref HEAD
git status --short
```

Expected: branch `feat/plan3-multimodal-input`，无 uncommitted changes（worktree 起手干净）。

如果 branch 不对，stop 并 SendMessage team-lead 要求重建 worktree。

- [ ] **Step 2: 验证 v2 + Plan2 (P0-P7) 已在 worktree base 上**

```bash
ls services/store.py services/coach.py services/interviewer.py services/export.py
grep -l "UserProfile" services/schemas.py
grep -l "compute_replay_coverage" services/coach.py
grep -l "INTERVIEWER_REPLAY_PROMPT_INJECT" services/prompts.py
pixi run test
```

Expected:
- 4 文件都存在
- schemas.py 含 UserProfile（Plan2 P1 落地）
- coach.py 含 compute_replay_coverage（Plan2 P3）
- prompts.py 含 INTERVIEWER_REPLAY_PROMPT_INJECT（Plan2 P5）
- 现有 tests 全 pass（具体数量按 worktree base 推算，不应低于 Plan2 P7 累计的 113 + 任何后续）

如果其中任何 fail，stop + SendMessage team-lead。

- [ ] **Step 3: 创建 data/uploads 目录**

```bash
mkdir -p data/uploads
touch data/uploads/.gitkeep
```

- [ ] **Step 4: .gitignore 加 uploads 规则**

Edit `.gitignore`，在 Plan2 P0 加的 `# Plan2: per-user profile JSON dumps` 块下面追加：

```
# Plan3: per-user upload files (raw + metadata)
data/uploads/**
!data/uploads/.gitkeep
```

- [ ] **Step 5: pixi 加 python-docx 依赖**

```bash
pixi add "python-docx>=1.1,<2"
```

预期：`pixi.toml` 加一行依赖；`pixi.lock` 自动更新。

如果 pixi 网络问题安装失败，重试一次；仍失败 SendMessage team-lead。

- [ ] **Step 6: 验证 import 通过**

```bash
pixi run python -c "from docx import Document; import fitz; print('ok')"
```

Expected: `ok`。

- [ ] **Step 7: Run baseline tests**

```bash
pixi run test
```

Expected: 全 pass，未受新依赖影响。

- [ ] **Step 8: Commit**

```bash
git add data/uploads/.gitkeep .gitignore pixi.toml pixi.lock
git commit -m "$(cat <<'EOF'
chore(plan3): prepare worktree — add python-docx + data/uploads dir + gitignore

Plan3 G1 文件上传需 .docx 解析能力（PyMuPDF v1 已装可解 PDF）。
data/uploads/ 沿用 Plan2 data/users/ 同 pattern：.gitignore 兜底。
EOF
)"
```

---

### Task Q1: services/schemas.py — Plan3 新 3 个 schema

**Files:**
- Modify: `services/schemas.py`
- Test: `tests/test_schemas_plan3.py`

新增：`UploadedFile` / `UploadResponse` / `TTSRequest`。不动既有 schema。

- [ ] **Step 1: Write failing tests**

Create `tests/test_schemas_plan3.py`:

```python
"""Plan3 schemas tests — Spec E §5."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from services.schemas import TTSRequest, UploadResponse, UploadedFile


def test_uploaded_file_minimal():
    f = UploadedFile(
        file_id="abc-123",
        user_id="u1",
        original_filename="resume.pdf",
        file_type="pdf",
        size_bytes=12345,
        uploaded_at=datetime(2026, 5, 12),
        parsed_text="hello",
    )
    assert f.parse_warnings == []


def test_uploaded_file_rejects_unknown_file_type():
    with pytest.raises(ValidationError):
        UploadedFile(
            file_id="x", user_id="u",
            original_filename="x.exe", file_type="exe",
            size_bytes=0, uploaded_at=datetime.now(), parsed_text="",
        )


def test_upload_response_defaults_warnings():
    r = UploadResponse(file_id="x", parsed_text="hi", file_type="pdf")
    assert r.parse_warnings == []


def test_tts_request_defaults():
    r = TTSRequest(text="你好")
    assert r.voice == "default"
    assert r.user_id == "anonymous"


def test_tts_request_accepts_user_id():
    r = TTSRequest(text="你好", user_id="u1")
    assert r.user_id == "u1"
```

- [ ] **Step 2: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_schemas_plan3.py -v
```

Expected: `ImportError` for `UploadedFile` / `UploadResponse` / `TTSRequest`.

- [ ] **Step 3: Implement schemas in services/schemas.py**

在 `services/schemas.py` 末尾追加（保留 v2 + Plan2 所有现有定义；不破坏现有 import）：

```python
# ----------------- Plan3 多模态输入 -----------------

from typing import Literal

class UploadedFile(BaseModel):
    """Spec E §5.1 — 上传文件元数据；存到 data/uploads/<user_id>/<file_id>.json。"""
    file_id: str
    user_id: str
    original_filename: str
    file_type: Literal["pdf", "docx", "md", "txt"]
    size_bytes: int
    uploaded_at: datetime
    parsed_text: str
    parse_warnings: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Spec E §5.2 — POST /api/uploads 响应。"""
    file_id: str
    parsed_text: str
    file_type: str
    parse_warnings: list[str] = Field(default_factory=list)


class TTSRequest(BaseModel):
    """Spec E §5.3 — POST /api/tts/synthesize 入参。"""
    text: str
    voice: str = "default"
    user_id: str = "anonymous"
```

注意：
- `Literal` 如 schemas.py 顶部未 import，加 `from typing import Literal`
- `Field` / `BaseModel` / `datetime` 应已 import；如缺补上

- [ ] **Step 4: Run tests to verify PASS**

```bash
pixi run pytest tests/test_schemas_plan3.py -v
```

Expected: 5 passed。

- [ ] **Step 5: Run all tests baseline**

```bash
pixi run test
```

Expected: baseline 数量 + 5（不破坏既有）。

- [ ] **Step 6: Commit**

```bash
git add services/schemas.py tests/test_schemas_plan3.py
git commit -m "$(cat <<'EOF'
feat(schemas): add Plan3 multimodal schemas

新增 UploadedFile / UploadResponse / TTSRequest；不修改 v2/Plan2 既有 schema。
file_type Literal["pdf","docx","md","txt"] 限制白名单。
EOF
)"
```

---

### Task Q2: services/file_parse.py — PDF/Word/MD/txt 分发

**Files:**
- Create: `services/file_parse.py`
- Test: `tests/test_file_parse.py`
- Test fixtures: `tests/fixtures/sample.pdf` / `sample.docx` / `sample.md` / `sample.txt`

新模块：把上传文件路径 + 类型 → 解析文本 + warnings。

- [ ] **Step 1: 准备 test fixtures**

```bash
mkdir -p tests/fixtures
echo "# 项目动机
这是一个测试 markdown 文件。

## baseline
我用 zero-shot 作 baseline。" > tests/fixtures/sample.md
echo "纯文本测试。换行也支持。" > tests/fixtures/sample.txt
```

PDF / docx fixtures 在 implementation 后用 Python 即时构造（避免在仓库里塞二进制文件）。

- [ ] **Step 2: Write failing tests**

Create `tests/test_file_parse.py`:

```python
"""file_parse tests — Spec E §7.3."""
from pathlib import Path

import pytest

from services.file_parse import parse_file


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_parse_md():
    text, warnings = await parse_file(FIXTURES / "sample.md", "md")
    assert "项目动机" in text
    assert "baseline" in text
    assert warnings == []


@pytest.mark.asyncio
async def test_parse_txt():
    text, warnings = await parse_file(FIXTURES / "sample.txt", "txt")
    assert "纯文本测试" in text
    assert warnings == []


@pytest.mark.asyncio
async def test_parse_pdf_simple(tmp_path: Path):
    """构造一个简单 PDF（内含一行文本），验证解析。"""
    import fitz
    pdf_path = tmp_path / "simple.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Hello PDF 世界", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()

    text, warnings = await parse_file(pdf_path, "pdf")
    assert "Hello PDF" in text or "世界" in text
    assert warnings == []  # 简单文本，无图片


@pytest.mark.asyncio
async def test_parse_pdf_with_image(tmp_path: Path):
    """含图片的 PDF 应在 warnings 中提示。"""
    import fitz
    pdf_path = tmp_path / "with_image.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "page text", fontsize=12)
    # 插入一个最小像素图（红色方块）
    import io
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
    pix.set_rect(pix.irect, (255, 0, 0))
    rect = fitz.Rect(100, 100, 110, 110)
    page.insert_image(rect, pixmap=pix)
    doc.save(str(pdf_path))
    doc.close()

    text, warnings = await parse_file(pdf_path, "pdf")
    assert any("image" in w.lower() for w in warnings)


@pytest.mark.asyncio
async def test_parse_pdf_encrypted_raises(tmp_path: Path):
    """加密 PDF 抛 ValueError。"""
    import fitz
    pdf_path = tmp_path / "enc.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "secret")
    doc.save(str(pdf_path), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="x", user_pw="y")
    doc.close()

    with pytest.raises(ValueError, match="encrypted"):
        await parse_file(pdf_path, "pdf")


@pytest.mark.asyncio
async def test_parse_docx(tmp_path: Path):
    """构造一个简单 docx，验证段落 + 表格。"""
    from docx import Document
    docx_path = tmp_path / "sample.docx"
    doc = Document()
    doc.add_paragraph("第一段：项目动机")
    doc.add_paragraph("第二段：baseline 选择")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "指标"
    table.rows[0].cells[1].text = "数值"
    table.rows[1].cells[0].text = "准确率"
    table.rows[1].cells[1].text = "0.85"
    doc.save(str(docx_path))

    text, warnings = await parse_file(docx_path, "docx")
    assert "项目动机" in text
    assert "baseline 选择" in text
    assert "指标" in text or "准确率" in text  # 表格被渲染为行
    assert any("table" in w.lower() for w in warnings)


@pytest.mark.asyncio
async def test_parse_unsupported_type_raises():
    with pytest.raises(ValueError, match="unsupported"):
        await parse_file(FIXTURES / "sample.txt", "xyz")
```

- [ ] **Step 3: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_file_parse.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.file_parse'`.

- [ ] **Step 4: Implement services/file_parse.py**

Create `services/file_parse.py`:

```python
"""File parsing for project material uploads — Plan3 G1 (Spec E §7.3)."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


async def parse_file(path: Path, file_type: str) -> tuple[str, list[str]]:
    """根据 file_type 分发；返回 (parsed_text, warnings)。

    file_type 必须是 'pdf' | 'docx' | 'md' | 'txt'。
    PDF 加密 / 解析错误 → ValueError。
    """
    if file_type == "pdf":
        return _parse_pdf(path)
    if file_type == "docx":
        return _parse_docx(path)
    if file_type in ("md", "txt"):
        return path.read_text(encoding="utf-8"), []
    raise ValueError(f"unsupported file_type: {file_type}")


def _parse_pdf(path: Path) -> tuple[str, list[str]]:
    """PyMuPDF 抽页面文本；图片不 OCR，warnings 提示。"""
    warnings: list[str] = []
    chunks: list[str] = []
    with fitz.open(path) as doc:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted; please remove password protection")
        for i, page in enumerate(doc):
            txt = page.get_text("text")
            chunks.append(txt)
            if page.get_images():
                warnings.append(f"page {i + 1} contains images (OCR not performed)")
    return "\n\n".join(chunks).strip(), warnings


def _parse_docx(path: Path) -> tuple[str, list[str]]:
    """python-docx 抽段落 + 表格。"""
    from docx import Document

    warnings: list[str] = []
    doc = Document(str(path))
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    if doc.tables:
        for t in doc.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells]
                parts.append(" | ".join(cells))
        warnings.append("docx contains tables (rendered as plain text rows)")
    return "\n\n".join(parts).strip(), warnings
```

- [ ] **Step 5: Run tests to verify PASS**

```bash
pixi run pytest tests/test_file_parse.py -v
```

Expected: 7 passed。

- [ ] **Step 6: Commit**

```bash
git add services/file_parse.py tests/test_file_parse.py tests/fixtures/sample.md tests/fixtures/sample.txt
git commit -m "$(cat <<'EOF'
feat(file_parse): add PDF/DOCX/MD/TXT parser dispatch

PyMuPDF 抽 PDF 文本（图片不 OCR，warnings 提示）；python-docx 抽 docx
段落 + 表格行；md/txt 直读 utf-8。加密 PDF / 不支持 ext → ValueError。
EOF
)"
```

---

### Task Q3: services/tts.py — MiMo TTS 封装

**Files:**
- Create: `services/tts.py`
- Test: `tests/test_tts_module.py`

新模块：调 MiMo `/v1/audio/speech`，返 audio bytes；retry once on network error。

- [ ] **Step 1: Write failing tests**

Create `tests/test_tts_module.py`:

```python
"""TTS module tests — Spec E §9.1."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.tts import synthesize_speech


@pytest.mark.asyncio
async def test_synthesize_speech_happy(monkeypatch):
    """正常调用返 bytes。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake_resp = httpx.Response(
        status_code=200,
        content=b"\x00\x01\x02 fake mp3 bytes",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def fake_post(*args, **kwargs):
        return fake_resp

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        audio = await synthesize_speech("你好世界")

    assert audio.startswith(b"\x00\x01\x02")


@pytest.mark.asyncio
async def test_synthesize_speech_retry_once(monkeypatch):
    """第一次 NetworkError → retry → 第二次成功。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    call_count = {"n": 0}
    fake_ok = httpx.Response(
        status_code=200,
        content=b"recovered audio",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def flaky_post(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.NetworkError("transient")
        return fake_ok

    with patch("httpx.AsyncClient.post", side_effect=flaky_post):
        audio = await synthesize_speech("hi")

    assert audio == b"recovered audio"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_synthesize_speech_persistent_failure_raises(monkeypatch):
    """两次都 NetworkError → 抛。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    async def always_fail(*args, **kwargs):
        raise httpx.NetworkError("down")

    with patch("httpx.AsyncClient.post", side_effect=always_fail):
        with pytest.raises(httpx.NetworkError):
            await synthesize_speech("hi")


@pytest.mark.asyncio
async def test_synthesize_speech_4xx_raises(monkeypatch):
    """API 返 4xx → raise_for_status 抛 HTTPStatusError，不 retry。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake_400 = httpx.Response(
        status_code=400,
        text="bad request",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def fake_post(*args, **kwargs):
        return fake_400

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        with pytest.raises(httpx.HTTPStatusError):
            await synthesize_speech("hi")


@pytest.mark.asyncio
async def test_synthesize_speech_missing_api_key(monkeypatch):
    """缺 MIMO_API_KEY → KeyError（fail-fast）。"""
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with pytest.raises(KeyError):
        await synthesize_speech("hi")
```

- [ ] **Step 2: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_tts_module.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.tts'`.

- [ ] **Step 3: Implement services/tts.py**

Create `services/tts.py`:

```python
"""MiMo TTS — Plan3 G3 (Spec E §9.1).

OpenAI 兼容 POST /v1/audio/speech；返 audio bytes（mp3）。
Retry once on httpx.NetworkError；HTTP 4xx/5xx 不 retry，让 endpoint 层处理。
"""
from __future__ import annotations

import os

import httpx


async def synthesize_speech(
    text: str,
    voice: str = "default",
    *,
    timeout: float = 30.0,
) -> bytes:
    """Spec E §9.1 — 调 MiMo audio.speech。
    成功返 audio bytes；失败 raise httpx 异常给上层。"""
    api_key = os.environ["MIMO_API_KEY"]  # 缺 → KeyError fail-fast
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-tts")

    url = f"{base_url}/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}

    async def _call() -> bytes:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content

    try:
        return await _call()
    except httpx.NetworkError:
        return await _call()  # retry once on transient network error
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pixi run pytest tests/test_tts_module.py -v
```

Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add services/tts.py tests/test_tts_module.py
git commit -m "$(cat <<'EOF'
feat(tts): add MiMo TTS wrapper (OpenAI-compatible audio.speech)

POST /v1/audio/speech with retry-once on httpx.NetworkError；
HTTPStatusError 4xx/5xx 不 retry 让 endpoint 503 兜底；缺 MIMO_API_KEY
fail-fast KeyError。response_format=mp3 默认，UI 不暴露 voice 选择。
EOF
)"
```

---

### Task Q4: server/main.py — POST /api/uploads

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_endpoints_uploads.py`

新 endpoint：multipart 上传 → 解析 → 返 UploadResponse。

- [ ] **Step 1: Write failing tests**

Create `tests/test_endpoints_uploads.py`:

```python
"""Plan3 /api/uploads endpoint tests — Spec E §6 / §7.2."""
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def _make_pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Hello PDF 世界", fontsize=12)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_docx_bytes() -> bytes:
    from docx import Document
    doc = Document()
    doc.add_paragraph("DOCX 段落测试")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_upload_pdf_happy(client):
    pdf = _make_pdf_bytes()
    r = client.post(
        "/api/uploads",
        files={"file": ("project.pdf", pdf, "application/pdf")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_type"] == "pdf"
    assert "Hello PDF" in body["parsed_text"] or "世界" in body["parsed_text"]


def test_upload_docx_happy(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("project.docx", _make_docx_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 200
    assert "DOCX" in r.json()["parsed_text"]


def test_upload_md_happy(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("notes.md", b"# title\n\nbody", "text/markdown")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 200
    assert "title" in r.json()["parsed_text"]


def test_upload_txt_happy(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("note.txt", "纯文本".encode("utf-8"), "text/plain")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 200


def test_upload_rejects_unknown_ext(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("malware.exe", b"\x00\x00", "application/octet-stream")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 400


def test_upload_rejects_legacy_doc(client):
    r = client.post(
        "/api/uploads",
        files={"file": ("old.doc", b"\x00\x00", "application/msword")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 400


def test_upload_rejects_oversize(client):
    """11MB 文件 → 413。"""
    big = b"x" * (11 * 1024 * 1024)
    r = client.post(
        "/api/uploads",
        files={"file": ("huge.txt", big, "text/plain")},
        data={"user_id": "u1"},
    )
    assert r.status_code == 413


def test_upload_user_quota_exceeded(client, tmp_path):
    """提前在 user 目录塞满 50MB → 下一次上传返 413。"""
    user_dir = tmp_path / "uploads" / "u-full"
    user_dir.mkdir(parents=True)
    (user_dir / "preexisting.txt").write_bytes(b"x" * (50 * 1024 * 1024))

    r = client.post(
        "/api/uploads",
        files={"file": ("more.txt", b"hi", "text/plain")},
        data={"user_id": "u-full"},
    )
    assert r.status_code == 413


def test_upload_anonymous_default(client):
    """缺 user_id → fallback anonymous。"""
    r = client.post(
        "/api/uploads",
        files={"file": ("note.md", b"# x", "text/markdown")},
    )
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_endpoints_uploads.py -v
```

Expected: 全部 404 或 422（路径未注册）。

- [ ] **Step 3: 添加 endpoint 到 server/main.py**

Read `server/main.py` 找到合适插入位置（建议 v2 + Plan2 endpoints 之后）。

顶部 imports 追加（如未有）：

```python
import uuid
from pathlib import Path

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from services.file_parse import parse_file
from services.schemas import TTSRequest, UploadResponse, UploadedFile  # TTSRequest 用于 Q5
from services.tts import synthesize_speech                              # Q5 用
```

加 endpoint：

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_USER_QUOTA = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTS = {"pdf", "docx", "md", "txt"}


@app.post("/api/uploads", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
):
    """Spec E §7.2 — 上传项目材料；解析后注入 onboarding/material textarea。"""
    if not file.filename:
        raise HTTPException(400, "filename missing")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"unsupported file type: .{ext}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(413, f"file too large (max {MAX_FILE_SIZE // 1024 // 1024}MB)")

    user_dir = DATA_DIR / "uploads" / user_id
    used = sum(p.stat().st_size for p in user_dir.glob("*") if p.is_file()) if user_dir.exists() else 0
    if used + len(contents) > MAX_USER_QUOTA:
        raise HTTPException(413, f"user quota exceeded (max {MAX_USER_QUOTA // 1024 // 1024}MB)")

    file_id = str(uuid.uuid4())
    user_dir.mkdir(parents=True, exist_ok=True)
    raw_path = user_dir / f"{file_id}.{ext}"
    raw_path.write_bytes(contents)

    try:
        parsed_text, warnings = await parse_file(raw_path, ext)
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        raise HTTPException(422, f"parse failed: {e}")

    meta = UploadedFile(
        file_id=file_id,
        user_id=user_id,
        original_filename=file.filename,
        file_type=ext,
        size_bytes=len(contents),
        uploaded_at=datetime.now(),
        parsed_text=parsed_text,
        parse_warnings=warnings,
    )
    (user_dir / f"{file_id}.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    return UploadResponse(
        file_id=file_id,
        parsed_text=parsed_text,
        file_type=ext,
        parse_warnings=warnings,
    )
```

注意：`DATA_DIR` 是 Plan2 P7 加的环境变量驱动 Path（沿用同 pattern）；`datetime` 应已 import。

- [ ] **Step 4: Run tests to verify PASS**

```bash
pixi run pytest tests/test_endpoints_uploads.py -v
```

Expected: 9 passed。

- [ ] **Step 5: 跑全套测试 baseline**

```bash
pixi run test
```

Expected: 既有 tests + Q1+Q2+Q3+Q4 新增全 pass。

- [ ] **Step 6: Commit**

```bash
git add server/main.py tests/test_endpoints_uploads.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/uploads (multipart project material parse)

PDF/Word/MD/TXT 白名单 + 10MB 单文件上限 + 50MB user 配额；
存盘 data/uploads/<user_id>/<file_id>.{ext} + .json metadata；
解析失败回滚原文件 (raw_path.unlink)。
EOF
)"
```

---

### Task Q5: server/main.py — POST /api/tts/synthesize

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_endpoints_tts.py`

新 endpoint：调 `services.tts.synthesize_speech` 返 audio/mpeg。

- [ ] **Step 1: Write failing tests**

Create `tests/test_endpoints_tts.py`:

```python
"""Plan3 /api/tts/synthesize endpoint tests — Spec E §9.2."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "fake")
    with TestClient(app) as c:
        yield c


def test_tts_happy(client):
    fake = AsyncMock(return_value=b"fake mp3 bytes")
    with patch("server.main.synthesize_speech", fake):
        r = client.post("/api/tts/synthesize", json={"text": "你好世界"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == b"fake mp3 bytes"


def test_tts_passes_voice_and_user_id(client):
    fake = AsyncMock(return_value=b"x")
    with patch("server.main.synthesize_speech", fake) as p:
        r = client.post("/api/tts/synthesize", json={
            "text": "hi", "voice": "alto", "user_id": "u1",
        })
    assert r.status_code == 200
    p.assert_awaited_once_with("hi", "alto")  # voice 被透传


def test_tts_empty_text_422(client):
    r = client.post("/api/tts/synthesize", json={"text": ""})
    assert r.status_code == 422


def test_tts_blank_text_422(client):
    r = client.post("/api/tts/synthesize", json={"text": "   "})
    assert r.status_code == 422


def test_tts_text_too_long_422(client):
    r = client.post("/api/tts/synthesize", json={"text": "x" * 4001})
    assert r.status_code == 422


def test_tts_upstream_failure_503(client):
    fake = AsyncMock(side_effect=httpx.NetworkError("down"))
    with patch("server.main.synthesize_speech", fake):
        r = client.post("/api/tts/synthesize", json={"text": "hi"})
    assert r.status_code == 503
```

- [ ] **Step 2: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_endpoints_tts.py -v
```

Expected: 全部 404 / 405（路径未注册）。

- [ ] **Step 3: 添加 endpoint 到 server/main.py**

```python
@app.post("/api/tts/synthesize")
async def tts_synthesize(req: TTSRequest):
    """Spec E §9.2 — MiMo TTS。失败 → 503，前端静默降级。"""
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

注意：`synthesize_speech` 顶部 import 已在 Q4 加。`Response` 同。`HTTPException` 应已在 server/main.py 顶部 import。

- [ ] **Step 4: Run tests to verify PASS**

```bash
pixi run pytest tests/test_endpoints_tts.py -v
```

Expected: 6 passed。

- [ ] **Step 5: 跑全套测试 baseline**

```bash
pixi run test
```

Expected: Q1-Q5 累计新增全 pass，既有不动。

- [ ] **Step 6: Commit**

```bash
git add server/main.py tests/test_endpoints_tts.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/tts/synthesize (MiMo audio/mpeg stream)

422 for empty/blank/>4000-char text；503 for upstream failure（前端静默降级）；
voice 字段透传给 synthesize_speech，UI 当前不暴露选择。
EOF
)"
```

---

### Task Q6: web/index.html + web/styles.css — toggle 按钮 + 上传按钮 + mic 按钮 DOM

**SYNC POINT — 起手前 SendMessage team-lead 确认 Plan2 P10-P14 frontend 已 ship 到 main**

**Files:**
- Modify: `web/index.html`
- Modify: `web/styles.css`

视觉层改动：在 Plan2 已 ship 的 6 视图基础上加双 toggle + 上传按钮 + 三 textarea mic 按钮 DOM。

**implementer subagent prompt 必须列**：
- 起手 invoke `superpowers:test-driven-development`（DOM id / class 契约存在性测试）
- 起手 invoke `frontend-design:frontend-design`（视觉方案；保持 DOM id 契约 + vanilla CSS + 沿用现有 CSS 变量）
- 报告 DONE 前 invoke `superpowers:verification-before-completion`（pixi run serve + 浏览器 DOM inspect）

- [ ] **Step 1: SendMessage team-lead 确认 sync point**

```
"Q6 起手前 sync check：worktree 当前是否在 Plan2 P10-P14 已 merge 后的 main 上？
git log main..HEAD 应包含我所有 Q0-Q5 commits；git log HEAD..main 应空（rebase 后）。"
```

如 team-lead 回复"未 ready"，**等到 ready 再启动 Q6**。

- [ ] **Step 2: rebase 到最新 main**

```bash
git fetch origin
git rebase origin/main
```

如有冲突，解冲突 → continue。冲突一般出现在 schemas.py（Plan3 加的 schemas vs Plan2 加的 schemas，都在末尾追加，可加性合并）+ server/main.py（Plan3 加的 endpoints vs Plan2 加的 endpoints，函数定义独立）。

- [ ] **Step 3: 跑全套测试 baseline（rebase 后）**

```bash
pixi run test
```

Expected: 全 pass（Plan2 P0-P14 + Plan3 Q1-Q5 累计 tests 都能跑）。

- [ ] **Step 4: Write failing test for DOM contract**

Create `tests/test_web_dom_plan3.py`:

```python
"""Plan3 web DOM contract test — Spec E §10 / §7.4."""
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"


def test_index_html_has_mic_toggle():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="toggle-mic"' in html


def test_index_html_has_speaker_toggle():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="toggle-speaker"' in html


def test_index_html_has_upload_button():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="upload-btn"' in html
    assert 'id="upload-input"' in html


def test_index_html_has_mic_buttons_for_three_textareas():
    """三个 mic 按钮：onboarding chat / interview answer / resume_iterate textarea 各一。"""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    # data-target-textarea 是 dispatch 用的；至少 3 个 mic-btn
    mic_btns = html.count('class="mic-btn"')
    assert mic_btns >= 3, f"expected >= 3 mic buttons, found {mic_btns}"


def test_styles_has_mic_pulse_class():
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    assert ".mic-pulse" in css
```

- [ ] **Step 5: Run tests to verify FAIL**

```bash
pixi run pytest tests/test_web_dom_plan3.py -v
```

Expected: 5 fail。

- [ ] **Step 6: 修改 web/index.html**

在 nav header（Plan2 已加共享 header）加双 toggle：

```html
<button id="toggle-mic" class="nav-toggle" title="麦克风模式" aria-pressed="false">🎤</button>
<button id="toggle-speaker" class="nav-toggle" title="扬声器模式" aria-pressed="false">🔈</button>
```

在 view-onboarding 或 view-material 现有 textarea 前加上传：

```html
<div class="upload-row">
  <input type="file" id="upload-input" accept=".pdf,.docx,.md,.txt" hidden>
  <button id="upload-btn">📎 上传项目材料（PDF / Word / Markdown / TXT，≤10MB）</button>
  <progress id="upload-progress" class="hidden" max="100" value="0"></progress>
  <div id="upload-warnings" class="warnings hidden"></div>
</div>
```

在三个 textarea（onboarding chat input / interview answer textarea / resume_iterate input）旁各加 mic 按钮。Plan2 已建立 textarea 的 id（如 `material-textarea` / `interview-answer-input` / `resume-iterate-input`），用 `data-target-textarea` 关联：

```html
<div class="textarea-with-mic">
  <textarea id="material-textarea"></textarea>
  <button class="mic-btn" data-target-textarea="material-textarea" title="语音输入" disabled>🎤</button>
</div>
```

`disabled` 默认是因为 mic toggle 默认 off；JS 在 toggle on 时 enable。

- [ ] **Step 7: 修改 web/styles.css**

在末尾追加 Plan3 样式：

```css
/* Plan3 — 多模态输入 */
.nav-toggle {
  background: transparent;
  border: 1px solid var(--border, #333);
  color: var(--fg, #eee);
  padding: 4px 10px;
  margin-left: 4px;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0.5;
}
.nav-toggle[aria-pressed="true"] {
  background: var(--accent, #4a90e2);
  color: #fff;
  opacity: 1;
}

.upload-row {
  margin: 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
#upload-btn {
  padding: 8px 14px;
  background: var(--surface, #1a1a1a);
  border: 1px dashed var(--border, #555);
  color: var(--fg, #eee);
  border-radius: 6px;
  cursor: pointer;
}
#upload-btn:hover {
  border-color: var(--accent, #4a90e2);
}
#upload-progress {
  flex: 1;
  height: 6px;
}
.warnings {
  font-size: 0.85em;
  color: var(--warn, #e67e22);
  padding: 6px 12px;
  border-left: 3px solid var(--warn, #e67e22);
  background: rgba(230, 126, 34, 0.08);
  width: 100%;
}
.hidden { display: none; }

.textarea-with-mic {
  position: relative;
}
.textarea-with-mic textarea {
  width: 100%;
  padding-right: 48px;
  box-sizing: border-box;
}
.mic-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  background: transparent;
  border: 1px solid var(--border, #333);
  color: var(--fg, #eee);
  border-radius: 50%;
  width: 36px;
  height: 36px;
  cursor: pointer;
  font-size: 1em;
}
.mic-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.mic-btn.mic-pulse {
  background: #e74c3c;
  color: #fff;
  border-color: #e74c3c;
  animation: mic-pulse 1.2s ease-in-out infinite;
}
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0.6); }
  50%      { box-shadow: 0 0 0 10px rgba(231, 76, 60, 0); }
}
```

- [ ] **Step 8: Run tests to verify PASS**

```bash
pixi run pytest tests/test_web_dom_plan3.py -v
```

Expected: 5 passed。

- [ ] **Step 9: 启服务确认无 console error**

```bash
pixi run serve &
sleep 2
curl -sf http://127.0.0.1:8000/ > /dev/null
echo "served ok"
kill %1
```

或手动：浏览器打开 `http://127.0.0.1:8000`，DevTools console 无 error；nav 看到两个新 toggle 按钮（默认灰）；进 onboarding/material 视图看到上传按钮 + 三视图都有 mic 按钮（disabled）。

- [ ] **Step 10: Commit**

```bash
git add web/index.html web/styles.css tests/test_web_dom_plan3.py
git commit -m "$(cat <<'EOF'
feat(web): add multimodal DOM scaffold (toggles + upload + mic buttons)

🎤/🔈 双 toggle 加进共享 nav；onboarding 上传按钮 + progress bar + warnings
显示位；三 textarea (material / interview answer / resume_iterate) 旁
加 disabled mic 按钮（toggle on 时 JS enable）。CSS pulse 动画走纯 keyframes。
EOF
)"
```

---

### Task Q7: web/app.js — VoiceInput class + fetchAndPlayTTS + upload XHR + toggle 状态管理

**Files:**
- Modify: `web/app.js`

把所有 Plan3 前端逻辑接到 Q6 的 DOM 上。

**implementer subagent prompt 必须列**：
- 起手 invoke `superpowers:test-driven-development`（DOM 行为测试可用纯 JSDOM 或简单 unit test）
- 起手 invoke `frontend-design:frontend-design`（交互动效；保持 5 条硬约束）
- 报告 DONE 前 invoke `superpowers:verification-before-completion`（手动浏览器 e2e）

- [ ] **Step 1: 加 toggle 状态初始化（在 app.js 顶部 USER_ID 初始化附近）**

```javascript
// Plan3: 多模态 toggle 状态
state.mic_on = (localStorage.getItem('micOn') === 'true');
state.speaker_on = (localStorage.getItem('speakerOn') === 'true');

let VOICE_INPUT = null;        // 当前激活的 VoiceInput instance
let CURRENT_TTS_AUDIO = null;  // 当前播放的 TTS Audio


function updateMicToggleVisual() {
  const btn = document.getElementById('toggle-mic');
  btn.setAttribute('aria-pressed', state.mic_on ? 'true' : 'false');
  document.querySelectorAll('.mic-btn').forEach(b => {
    b.disabled = !state.mic_on;
  });
}
function updateSpeakerToggleVisual() {
  const btn = document.getElementById('toggle-speaker');
  btn.setAttribute('aria-pressed', state.speaker_on ? 'true' : 'false');
}

document.getElementById('toggle-mic').addEventListener('click', () => {
  state.mic_on = !state.mic_on;
  localStorage.setItem('micOn', state.mic_on);
  updateMicToggleVisual();
  if (!state.mic_on && VOICE_INPUT?.isRecording) {
    VOICE_INPUT.stop();
    document.querySelectorAll('.mic-btn.mic-pulse').forEach(b => {
      b.classList.remove('mic-pulse');
      b.dataset.recording = 'false';
    });
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

updateMicToggleVisual();
updateSpeakerToggleVisual();
```

- [ ] **Step 2: 加 VoiceInput class**

```javascript
class VoiceInput {
  constructor(textarea) {
    this.textarea = textarea;
    this.recognition = null;
    this.isRecording = false;
    this.commitedText = '';
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
    if (this.commitedText && !this.commitedText.endsWith(' ') && !this.commitedText.endsWith('\n')) {
      this.commitedText += ' ';
    }

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
      showToast('语音识别错误：' + (e.error || 'unknown'));
      this.stop();
    };

    this.recognition.onend = () => {
      // continuous=true 模式静音超时也会 onend；如仍 isRecording 则重启
      if (this.isRecording) {
        try { this.recognition.start(); } catch (e) {}
      }
    };

    try {
      this.recognition.start();
      this.isRecording = true;
      return true;
    } catch (e) {
      showToast('启动麦克风失败：' + e.message);
      return false;
    }
  }

  stop() {
    this.isRecording = false;
    if (this.recognition) {
      try { this.recognition.stop(); } catch (e) {}
      this.recognition = null;
    }
  }
}


// 三 textarea mic 按钮 click handler
document.querySelectorAll('.mic-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (!state.mic_on) {
      showToast('请先开启麦克风模式');
      return;
    }
    const targetId = btn.dataset.targetTextarea;
    const ta = document.getElementById(targetId);
    if (!ta) return;

    if (btn.dataset.recording === 'true') {
      VOICE_INPUT?.stop();
      btn.classList.remove('mic-pulse');
      btn.dataset.recording = 'false';
      VOICE_INPUT = null;
    } else {
      // 停掉别处可能在录的
      if (VOICE_INPUT?.isRecording) {
        VOICE_INPUT.stop();
        document.querySelectorAll('.mic-btn').forEach(b => {
          b.classList.remove('mic-pulse');
          b.dataset.recording = 'false';
        });
      }
      VOICE_INPUT = new VoiceInput(ta);
      if (VOICE_INPUT.start()) {
        btn.classList.add('mic-pulse');
        btn.dataset.recording = 'true';
      } else {
        VOICE_INPUT = null;
      }
    }
  });
});
```

- [ ] **Step 3: 加 fetchAndPlayTTS helper**

```javascript
async function fetchAndPlayTTS(text) {
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
    return;
  }
  if (!res.ok) {
    console.warn('TTS HTTP', res.status);
    return;
  }
  const blob = await res.blob();
  const audio = new Audio(URL.createObjectURL(blob));
  CURRENT_TTS_AUDIO = audio;
  audio.play().catch(e => console.warn('TTS audio.play() rejected', e));
}
```

- [ ] **Step 4: 接 view-interview 渲染问题处自动播**

Read `web/app.js` 找到 v2/Plan2 已有的 `renderInterview` 或类似函数（渲染当前 Interviewer 问题的位置）。在问题渲染 DOM 后追加：

```javascript
// Plan3: speaker toggle on 时自动播
if (state.speaker_on && state.current_question) {
  fetchAndPlayTTS(state.current_question);
}
```

`state.current_question` 字段名按 Plan2 实际命名调整。

也修改 `switchView` 函数，切走时停掉 audio：

```javascript
function switchView(name) {
  if (CURRENT_TTS_AUDIO) {
    try { CURRENT_TTS_AUDIO.pause(); } catch (e) {}
    CURRENT_TTS_AUDIO = null;
  }
  // ...（v2/Plan2 已有 view 切换逻辑）...
}
```

- [ ] **Step 5: 加 upload XHR handler**

```javascript
document.getElementById('upload-btn').addEventListener('click',
  () => document.getElementById('upload-input').click());

document.getElementById('upload-input').addEventListener('change', (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    showToast('文件过大（限 10MB）');
    return;
  }

  const xhr = new XMLHttpRequest();
  const bar = document.getElementById('upload-progress');
  const warnDiv = document.getElementById('upload-warnings');

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = (e.loaded / e.total) * 100;
      bar.classList.remove('hidden');
      bar.value = pct;
    }
  };

  xhr.onload = () => {
    bar.classList.add('hidden');
    bar.value = 0;
    if (xhr.status === 200) {
      let resp;
      try { resp = JSON.parse(xhr.responseText); } catch (e) {
        showToast('解析响应失败');
        return;
      }
      // 寻找 onboarding/material 视图主 textarea
      const ta = document.getElementById('material-textarea');
      if (ta) ta.value = resp.parsed_text;
      if (resp.parse_warnings && resp.parse_warnings.length) {
        warnDiv.textContent = '解析提示：' + resp.parse_warnings.join('; ');
        warnDiv.classList.remove('hidden');
      } else {
        warnDiv.classList.add('hidden');
      }
    } else {
      let detail = xhr.responseText;
      try { detail = JSON.parse(detail).detail || detail; } catch (e) {}
      showToast(`上传失败 (${xhr.status})：${detail}`);
    }
  };

  xhr.onerror = () => {
    bar.classList.add('hidden');
    showToast('网络错误，上传失败');
  };

  xhr.open('POST', '/api/uploads');
  const fd = new FormData();
  fd.append('file', file);
  fd.append('user_id', USER_ID);
  xhr.send(fd);

  // 重置 input value，允许重新选择同一文件
  ev.target.value = '';
});
```

注意：`material-textarea` 是 onboarding/material 视图主 textarea 的 id；具体 id 按 Plan2 实际命名调整。

- [ ] **Step 6: 手动 e2e**

```bash
pixi run serve
```

浏览器打开 `http://127.0.0.1:8000`，DevTools 打开：

1. 看到 nav 多了 🎤 + 🔈 两个 toggle，初始态灰
2. 点 🎤 → 视觉切到 active；mic 按钮去 disabled
3. 进 onboarding/material 视图 → 看到上传按钮
4. 点上传 → 选 PDF → progress bar 走完 → textarea 填解析文本
5. 点 textarea 旁 mic 按钮 → 浏览器弹麦克风授权 → 红色 pulse → 讲一句 → textarea 实时显示 partial → 停讲 final commit → 再点 mic 停
6. 点 🔈 toggle → 进 view-interview → 看到 / 听到第一问被朗读
7. 点 🔈 toggle off → 当前朗读立即停
8. 切换不同 view → 听到的 audio 应被 pause
9. console 无 error

- [ ] **Step 7: Commit**

```bash
git add web/app.js
git commit -m "$(cat <<'EOF'
feat(web): wire VoiceInput / TTS / upload XHR / dual toggle state

VoiceInput class 封装 webkitSpeechRecognition (lang=zh-CN, continuous,
interimResults)；fetchAndPlayTTS blob → Audio.src + 单实例追踪；
XHR upload progress + parsed_text 注入 textarea + warnings 渲染；
🎤/🔈 双 toggle localStorage 持久化 + 切换时停掉对应通道。
EOF
)"
```

---

### Task Q8: tests/test_plan3_loop.py — 集成 smoke

**Files:**
- Create: `tests/test_plan3_loop.py`

整条链路集成 smoke：上传 → onboarding → start → TTS 调用次数。

- [ ] **Step 1: Write integration test**

```python
"""Plan3 full integration smoke — Spec E §11.3.

完整链路：upload PDF → /api/uploads → 用 parsed_text 走 onboarding（mock LLM） →
start interview → 检查 /api/tts/synthesize 在 view-interview 渲染时被调用一次（mock）。
"""
from io import BytesIO
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIMO_API_KEY", "fake")
    with TestClient(app) as c:
        yield c


def _make_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "我的财会 Agent 项目：AI 生成公式 + 本地引擎核算", fontsize=12)
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_upload_then_onboarding(client):
    """上传 PDF 拿到 parsed_text，再用它喂 /api/coach/onboard。"""
    r = client.post(
        "/api/uploads",
        files={"file": ("project.pdf", _make_pdf(), "application/pdf")},
        data={"user_id": "u-int"},
    )
    assert r.status_code == 200
    parsed = r.json()["parsed_text"]
    assert "财会" in parsed or "Agent" in parsed

    fake_onboard = AsyncMock(return_value={
        "followup_questions": [],
        "user_model": {"id": "u", "target": "求职", "goal": "", "projects": [],
                       "strengths": [], "recurring_weaknesses": [],
                       "preferred_style": "strict", "current_stage": "onboarding"},
        "recommended_config": {},
    })
    with patch("server.main.coach_onboard", fake_onboard):
        r = client.post("/api/coach/onboard", json={
            "user_message": parsed, "history": [], "user_id": "u-int",
        })
    assert r.status_code == 200


def test_tts_endpoint_called_with_question_text(client):
    """直接调 /api/tts/synthesize 模拟前端在 renderInterviewerQuestion 时的调用。"""
    fake_synth = AsyncMock(return_value=b"audio bytes")
    with patch("server.main.synthesize_speech", fake_synth) as p:
        r = client.post("/api/tts/synthesize", json={
            "text": "你这次主要是为了准备保研复试还是 AI 岗位面试？",
            "user_id": "u-int",
        })
    assert r.status_code == 200
    p.assert_awaited_once()
    # 第一个 positional arg 是 text
    assert "保研" in p.await_args.args[0]
```

- [ ] **Step 2: Run tests to verify PASS**

```bash
pixi run pytest tests/test_plan3_loop.py -v
```

Expected: 2 passed。

- [ ] **Step 3: 跑全套测试 baseline**

```bash
pixi run test
```

Expected: 全 pass，含 v2 + Plan2 + Plan3 全部 tests。

- [ ] **Step 4: Commit**

```bash
git add tests/test_plan3_loop.py
git commit -m "$(cat <<'EOF'
test(plan3): add integration smoke (upload → onboard / tts call check)

mock LLM endpoint → 验证 upload-onboard 链路 + TTS endpoint 被调一次。
完整 e2e（含麦克风授权 / TTS 真返音频）走手动浏览器 e2e。
EOF
)"
```

---

### Task Q9: 部署 + nginx 调整 + Plan3-report

**Files:**
- Modify: `docs/deployment.md`（如改 nginx）
- Create: `docs/progress/Plan3-report.md`
- Server-side: nginx config + systemd

- [ ] **Step 1: SendMessage team-lead 等待 Plan2 全部 ship 到 main**

在合到 main 部署前确认：
- Plan2 P0-P16 全部 done + main 上 deploy 完成（健康检查 commit_hash 是 Plan2 P16 后的 sha）
- Plan3 worktree 已 rebase 到最新 main + 全部 Q0-Q8 commits 落地

- [ ] **Step 2: rebase + 全套测试**

```bash
git fetch origin
git rebase origin/main   # 解冲突；与 Q6 Step 2 类似
pixi run test
```

Expected: 全 pass。

- [ ] **Step 3: 合到 main**

```bash
git checkout main
git merge --no-ff feat/plan3-multimodal-input
```

`--no-ff` 保留分支结构便于回看；如项目 PR merge 习惯不同（用户级 CLAUDE.md 默认 squash），改用 squash。

- [ ] **Step 4: push 到 origin**

```bash
git push origin main
```

- [ ] **Step 5: 服务器 nginx `client_max_body_size` 调整**

```bash
ssh ubuntu@43.156.109.192 'sudo grep -n client_max_body_size /etc/nginx/sites-enabled/aiic.fomalhaut647.com'
```

如未配 / 配的小于 12M：

```bash
ssh ubuntu@43.156.109.192 'sudo sed -i "s|server_name aiic|client_max_body_size 12M;\n    server_name aiic|" /etc/nginx/sites-enabled/aiic.fomalhaut647.com && sudo nginx -t && sudo systemctl reload nginx'
```

注意：nginx config 编辑实际可能需要更精细的位置。先 grep + 看上下文，再决定插入点。如不确定，stop 并 SendMessage team-lead。

- [ ] **Step 6: 服务器 git pull + systemd restart**

```bash
ssh ubuntu@43.156.109.192 'cd /opt/aiic-chat && git pull && pixi install && sudo systemctl restart aiic-chat'
```

注意 `pixi install` 会装 python-docx 新依赖；如服务器 pixi 环境失败重试。

- [ ] **Step 7: 验证公网 URL**

```bash
curl -sf https://aiic.fomalhaut647.com/api/healthz | python -m json.tool
```

Expected: `commit_hash` 是当前 main HEAD；`status: ok`。Basic Auth 走 `-u aiic:<password>`（CLAUDE.md 部署 gotcha）。

- [ ] **Step 8: 手动 e2e on production（Chrome）**

按 Q7 Step 6 的 9 步走一遍 + 验证：
- TTS 真听到声音（MiMo 真调成功）
- mic 真录到中文文本
- 上传 PDF/Word 都解析成功
- nav toggle 状态在刷新后保留
- 报错 / cost 超限走静默降级（文字仍能继续）

- [ ] **Step 9: 写 docs/progress/Plan3-report.md**

```markdown
# Plan3 — 多模态输入交付报告

> 日期：YYYY-MM-DD
> 实施时长：N 小时
> 对应 spec：[../specs/E-multimodal-input.md](../specs/E-multimodal-input.md)
> 对应 plan：[../plans/Plan3-multimodal-input.md](../plans/Plan3-multimodal-input.md)

## 实际交付的 features

- [x] G1 文件上传（PDF / Word / MD / TXT；PyMuPDF + python-docx 解析）
- [x] G2 STT（Chrome 原生 webkitSpeechRecognition；三 textarea 都加 mic 按钮）
- [x] G3 TTS（MiMo mimo-v2.5-tts；OpenAI 兼容 audio.speech）
- [x] G4 麦克风 / 扬声器双独立 toggle（默认 off + localStorage 持久化）
- [x] G5 services/tts.py 后端封装

## 砍了 / 改了什么（vs spec）

- ……

## 踩了什么坑

- ……

## 与 Plan2 worktree 并行实施的体感

- 哪些 file 冲突最严重 / 解冲突花了多少时间
- frontend sync point 是否 work as designed
- 下次会怎么调整 worktree 策略

## 下一步候选（Plan4 候选）

- 跨浏览器 STT fallback（Safari/Firefox 走服务端 MiMo STT）
- TTS voice 多选 / 男女声切换
- 「我的资料库」UI（用户面访曾上传文件 / 重新引用）
- 语音 turn-taking（用户开口 TTS 自动暂停）
- OCR 图片简历
```

```bash
git add docs/progress/Plan3-report.md
git commit -m "docs(progress): add Plan3 delivery report"
git push origin main
```

- [ ] **Step 10: SendMessage team-lead 报告 Plan3 全部完成 + idle**

```
"Plan3 G1-G5 全部 ship 落地。
- main 最新 commit hash: <sha>
- 新增 tests: file_parse / tts_module / endpoints_uploads / endpoints_tts / web_dom_plan3 / plan3_loop
- 累计 tests: 全 pass
- 公网 https://aiic.fomalhaut647.com 已部署最新 + 浏览器 e2e 验证通过
- docs/progress/Plan3-report.md 落地

idle 等待下一步指示。"
```

---

## Self-review

按 writing-plans skill self-review checklist：

### 1. Spec coverage

| Spec E 节 | Plan task | 覆盖? |
|---|---|---|
| §1 范围（5 features） | Q0-Q9 | ✅ G1/G2/G3/G4/G5 全有对应 task |
| §2 设计哲学 | — | ✅ 不直接对应 task |
| §3 用户身份 | 沿用 Plan2 | ✅ 不新增 |
| §4 持久化布局 | Q0 | ✅ data/uploads + .gitignore |
| §5 数据契约（3 新 schema） | Q1 | ✅ |
| §6 API 接口（2 新 endpoint） | Q4 + Q5 | ✅ |
| §7 G1 文件上传 | Q2 + Q4 + Q6 + Q7 | ✅ |
| §8 G2 STT | Q6（DOM）+ Q7（VoiceInput） | ✅ |
| §9 G3 TTS | Q3 + Q5 + Q7 | ✅ |
| §10 G4 双 toggle | Q6（DOM）+ Q7（状态管理） | ✅ |
| §11 测试策略 | 散落 + Q8 集成 smoke + Q9 手动 e2e | ✅ |
| §12 风险 + 兜底 | Q3（retry）+ Q4（白名单/配额）+ Q5（503 fallback）+ Q7（onerror） | ✅ |
| §13 v2/Plan2 兼容性 | Q0 baseline + Q9 部署前全套 tests | ✅ |
| §14 实施依赖图 | Q0-Q9 顺序 | ✅ |
| §15 评分自检 | commit message + Plan3-report | ✅ |

**Gap**：spec §9.5 的 per-user TTS 日 quota（200 次/日上限）在 Q5 endpoint 实现里未体现（当前 endpoint 仅做 422 length check + 503 upstream fallback）。这是 spec → plan 简化（实施侧认为日 quota 是 over-engineering，YAGNI）。如果 maintainer 觉得 quota 必要，加一个 task Q5.5 实现 in-memory per-user-per-day counter；否则接受这条 spec 略简化的事实。

### 2. Placeholder scan

- 没有 TBD / TODO / "implement later"。所有 code blocks 完整可执行。
- Q4/Q5/Q6/Q7 多次说"按 Plan2 实际命名调整"是因为 worktree base 上 Plan2 frontend (P10-P14) 在 Q6 起手时才 ship 完，implementer 必须按彼时 main 的实际命名做对齐；这不是 placeholder 而是 sync point 设计。

### 3. Type consistency

- `UploadedFile` / `UploadResponse` / `TTSRequest` 字段在 Q1 / Q4 / Q5 / Q8 一致 ✅
- `synthesize_speech(text, voice)` 签名在 Q3 / Q5 / Q8 一致 ✅
- `parse_file(path, file_type)` 签名在 Q2 / Q4 一致 ✅
- DOM id (`#toggle-mic` / `#toggle-speaker` / `#upload-btn` / `#upload-input` / `#upload-progress` / `#upload-warnings` / `.mic-btn` / `data-target-textarea` / `material-textarea`) 在 Q6 / Q7 / Q8 一致 ✅

### 4. Ambiguity check

- Q6/Q7 频繁说 "Plan2 实际命名" 是 sync point 内在的 ambiguity——只能在 worktree rebase 后看实际状态；plan 给了 fallback id 名做参照，implementer 必须按彼时 main 实际 id 做对齐。
- Q9 Step 5 nginx config 编辑路径写的是 sed 注入；实际生产 nginx 文件结构可能不同，task 已写明"如不确定 stop + SendMessage"。

### 5. 修正后

无需修正。

---

**Plan complete and saved to `docs/plans/Plan3-multimodal-input.md`.**

实施建议：用 **superpowers:subagent-driven-development**（与 Plan2 同模式），但起步前先 `git worktree add` 出隔离工作目录 + `feat/plan3-multimodal-input` branch。Q6 起手前 sync 到最新 main（彼时 Plan2 P10-P14 应已 ship）。Q9 部署等 Plan2 P16 也完成后，Plan2 + Plan3 一并 push + 服务器拉一次 + nginx 调 + restart 一次。
