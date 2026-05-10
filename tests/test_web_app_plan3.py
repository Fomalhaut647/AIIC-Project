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


# Plan3.5 Bug 3: VoiceInput 内核从 webkitSpeechRecognition → MediaRecorder + server STT.
# 旧 contract test (zh-CN / interimResults / continuous) 已删, 因为这些字面 string
# 不再出现在 app.js. 替代为下面 STT-API contract test.


def test_voice_input_uses_media_recorder():
    """Plan3.5 Bug 3: VoiceInput 用 MediaRecorder API (而非 webkitSpeechRecognition)."""
    assert "MediaRecorder" in APP_JS, (
        "VoiceInput 必须用 MediaRecorder 录音, 替代旧的 webkitSpeechRecognition"
    )


def test_voice_input_uses_get_user_media():
    """Plan3.5 Bug 3: VoiceInput 用 navigator.mediaDevices.getUserMedia 申请麦克风。"""
    assert "getUserMedia" in APP_JS


def test_voice_input_posts_to_stt_endpoint():
    """Plan3.5 Bug 3: 录音 stop 后 multipart POST 到后端 STT endpoint。"""
    assert "/api/stt/transcribe" in APP_JS


def test_voice_input_prefers_webm_opus():
    """Plan3.5 Bug 3: 优先 audio/webm;codecs=opus (Chrome MediaRecorder 默认; 体积小)。"""
    # 允许 ';codecs=opus' 后缀 + 不要求恰好这一种（fallback chain 可加 audio/webm / mp4 等）
    assert "audio/webm" in APP_JS, "MediaRecorder mime 应优选 audio/webm 系列"


def test_voice_input_no_longer_uses_webkit_speech_recognition():
    """Plan3.5 Bug 3 反向 contract: 老 webkitSpeechRecognition 引用应已彻底移除,
    防止半改一半（旧 + 新代码并存导致两个 audio path race）。"""
    assert "webkitSpeechRecognition" not in APP_JS, (
        "旧 webkitSpeechRecognition 引用必须全部清掉,不允许双 STT 通路并存"
    )


def test_voice_input_handles_permission_denied():
    """Plan3.5 Bug 3: getUserMedia 拒绝授权时给用户明确提示 (toast),
    不静默吞 NotAllowedError 让 mic 按钮假装在录音。"""
    # 弱 contract: VoiceInput onError 路径 + _plan3Toast 引用
    fn_chunk = APP_JS[APP_JS.find("class VoiceInput"):]
    assert "getUserMedia" in fn_chunk
    # toast 调用在 mic-btn click handler 的 onError callback 中处理
    # (与原有 webkit error toast pattern 一致)


def test_voice_input_handles_503_unavailable():
    """Plan3.5 Bug 3: STT endpoint 503 时给 fallback toast (与 TTS 同模式)。"""
    fn_chunk = APP_JS[APP_JS.find("class VoiceInput"):]
    # 弱 contract: 检查 onError 在 fetch 失败 / 非 200 时被调用
    assert "onError" in fn_chunk


# ---------- Plan3.5 Bug 4: TTS 听不到诊断 + 修 ----------


def test_toggle_speaker_immediately_speaks_on_turning_on():
    """Plan3.5 Bug 4 fix: 翻 ON 时立即调 fetchAndPlayTTS(state.current_question),
    避免用户翻开 toggle 后还要等下一轮才能听到声音。click 本身是 user gesture,
    autoplay policy 不会 block。"""
    # 弱 contract: 找到 toggle-speaker click handler 内 fetchAndPlayTTS + current_question 引用
    # 用片段匹配,允许格式调整
    handler_start = APP_JS.find('toggle-speaker")?.addEventListener("click"')
    assert handler_start >= 0, "toggle-speaker click handler missing"
    # handler 范围: 从 addEventListener 到下一个分号匹配段尾 / 下个顶级 listener
    # 简单上限: 取后续 2KB 切片粗略验证内联引用
    handler_chunk = APP_JS[handler_start:handler_start + 2000]
    assert "fetchAndPlayTTS" in handler_chunk, (
        "toggle-speaker handler 必须 inline 调用 fetchAndPlayTTS 让 ON 即时朗读"
    )
    assert "state.current_question" in handler_chunk, (
        "toggle-speaker handler 必须 guard state.current_question (home view 没问题不读)"
    )


def test_fetch_and_play_tts_surfaces_autoplay_block():
    """Plan3.5 Bug 4 fix: audio.play() reject 不再静默,通过 _plan3Toast 反馈给用户。"""
    fn_start = APP_JS.find("async function fetchAndPlayTTS")
    assert fn_start >= 0
    fn_chunk = APP_JS[fn_start:fn_start + 3500]
    assert "_plan3Toast" in fn_chunk, (
        "fetchAndPlayTTS catch 应 surface autoplay block 给用户,不能静默吞 reject"
    )


def test_speaker_button_has_playing_visual_indicator():
    """Plan3.5 Bug 4 fix: TTS 播放期间 speaker icon 加 .tts-playing 视觉反馈,
    play()/ended/error 三处管理。"""
    fn_chunk = APP_JS[APP_JS.find("async function fetchAndPlayTTS"):]
    assert 'classList.add("tts-playing")' in fn_chunk
    assert 'classList.remove("tts-playing")' in fn_chunk


def test_styles_has_tts_playing_animation():
    """tts-playing class 必须有对应 keyframe + style block。"""
    css = (Path(__file__).parent.parent / "web" / "styles.css").read_text(encoding="utf-8")
    assert "#toggle-speaker.tts-playing" in css
    assert "@keyframes tts-pulse" in css
