"""File parsing for project material uploads — Plan3 G1 (Spec E §7.3)."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from docx import Document  # python-docx


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
