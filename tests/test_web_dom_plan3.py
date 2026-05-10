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
    mic_btns = html.count('class="mic-btn"')
    assert mic_btns >= 3, f"expected >= 3 mic buttons, found {mic_btns}"


def test_styles_has_mic_pulse_class():
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    assert ".mic-pulse" in css
