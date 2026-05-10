"""Plan3 web/app.js contract test — Spec E §8 / §9.3 / §10.

无 JSDOM (5 硬约束禁加 dep), 用文件内容契约 test 验证 Q7 关键 symbol/wiring.
真实浏览器 e2e 由 Q9 部署后 maintainer 手动验。
"""
from pathlib import Path

APP_JS = (Path(__file__).parent.parent / "web" / "app.js").read_text(encoding="utf-8")


def test_voice_input_class_defined():
    """VoiceInput class 封装 webkitSpeechRecognition (Spec E §8 G2 STT)."""
    assert "class VoiceInput" in APP_JS


def test_fetch_and_play_tts_helper_defined():
    """fetchAndPlayTTS helper 调 /api/tts/synthesize → blob → Audio (Spec E §9.3)."""
    assert "fetchAndPlayTTS" in APP_JS


def test_toggle_mic_listener_wired():
    """toggle-mic click 事件被绑 + localStorage 'micOn' 持久化 (Spec E §10)."""
    assert "toggle-mic" in APP_JS
    assert "micOn" in APP_JS  # localStorage key


def test_toggle_speaker_listener_wired():
    """toggle-speaker click 事件被绑 + localStorage 'speakerOn' 持久化 (Spec E §10)."""
    assert "toggle-speaker" in APP_JS
    assert "speakerOn" in APP_JS


def test_upload_endpoint_called():
    """/api/uploads endpoint 被前端 XHR 调用 (Spec E §7.4)."""
    assert "/api/uploads" in APP_JS


def test_tts_endpoint_called():
    """/api/tts/synthesize endpoint 被前端调用 (Spec E §9.3)."""
    assert "/api/tts/synthesize" in APP_JS


def test_mic_pulse_class_toggled_in_js():
    """mic-pulse class 在录音 start/stop 时被加/去 (Q6 已加 CSS keyframe)."""
    assert "mic-pulse" in APP_JS


def test_voice_input_uses_chinese_locale():
    """Web Speech API 设 zh-CN locale (Spec E §8)."""
    assert "zh-CN" in APP_JS


def test_voice_input_continuous_mode():
    """interimResults + continuous 配置 (Spec E §8: real-time partial commit)."""
    assert "interimResults" in APP_JS
    assert "continuous" in APP_JS
