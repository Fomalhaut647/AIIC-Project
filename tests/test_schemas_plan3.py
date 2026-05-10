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
