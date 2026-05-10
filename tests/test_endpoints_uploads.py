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


@pytest.mark.parametrize(
    "bad_user_id",
    [
        "../escape",      # 经典 path traversal
        "a/b",            # 嵌入分隔符
        "u space",        # 空格
        "u\nbreak",       # 换行
        "x" * 65,         # 超过 64 字符
        "汉字",            # 非 ASCII
        # 注意：空字符串被 fastapi Form("anonymous") 当作未提供，
        # fallback 到 default "anonymous"（合法 user_id），不会触发 400
    ],
)
def test_upload_rejects_invalid_user_id(client, bad_user_id):
    """user_id 必须 [A-Za-z0-9_-]{1,64}；防 path traversal + control chars。"""
    r = client.post(
        "/api/uploads",
        files={"file": ("note.md", b"# x", "text/markdown")},
        data={"user_id": bad_user_id},
    )
    assert r.status_code == 400, f"user_id {bad_user_id!r} unexpectedly accepted"


def test_upload_rollback_on_parse_failure(client, tmp_path, monkeypatch):
    """write 成功 + parse 失败 → raw_path 被 unlink，user 目录不留 orphan。"""

    async def fake_parse(*args, **kwargs):
        raise ValueError("synthetic parse fail")

    monkeypatch.setattr("server.main.parse_file", fake_parse)

    r = client.post(
        "/api/uploads",
        files={"file": ("rollback.md", b"# x", "text/markdown")},
        data={"user_id": "u-rollback"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "parse failed"

    user_dir = tmp_path / "uploads" / "u-rollback"
    if user_dir.exists():
        # 目录可能被 mkdir 创建但应无文件残留
        assert list(user_dir.glob("*")) == []


def test_upload_corrupt_docx_returns_422_and_unlinks(client, tmp_path):
    """非 valid zip 的 .docx → service 层 wrap → endpoint 422 + raw unlink。
    实测此 fixture 触发 zipfile.BadZipFile（reviewer round 2 empirical 验证；
    我之前 commit message 误标 PackageNotFoundError，path 在 phys_pkg 层 raise
    但实测 trace 是 BadZipFile）。验 PR review Issue 2 修复。"""
    fake_docx = b"\x00\x00\x00\x00 not a real zip"
    r = client.post(
        "/api/uploads",
        files={"file": (
            "corrupt.docx",
            fake_docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )},
        data={"user_id": "u-corrupt"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "parse failed"

    user_dir = tmp_path / "uploads" / "u-corrupt"
    if user_dir.exists():
        assert list(user_dir.glob("*")) == []


def test_upload_zip_without_content_types_returns_422_and_unlinks(client, tmp_path):
    """valid zip 但缺 [Content_Types].xml (用户 mv archive.zip resume.docx 场景)
    → python-docx 从 zipfile.getinfo() 抛 raw KeyError → service 层必须 catch
    KeyError wrap 成 ValueError，否则 endpoint narrow except 不覆盖 → 500 + raw
    orphan。reviewer round 2 score 100 sibling bug。"""
    import zipfile
    from io import BytesIO
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("foo.txt", "hello")  # valid zip, but no [Content_Types].xml

    r = client.post(
        "/api/uploads",
        files={"file": (
            "fake.docx",
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )},
        data={"user_id": "u-fakezip"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "parse failed"

    user_dir = tmp_path / "uploads" / "u-fakezip"
    if user_dir.exists():
        assert list(user_dir.glob("*")) == []
