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
