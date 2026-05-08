from server.mimo import CHAT_MODELS, MIMO_BASE_URL


def test_chat_models_are_known_chat_capable():
    assert "mimo-v2.5-pro" in CHAT_MODELS
    assert "mimo-v2.5" in CHAT_MODELS
    assert "mimo-v2-pro" in CHAT_MODELS
    assert "mimo-v2-omni" in CHAT_MODELS


def test_chat_models_exclude_tts():
    for m in CHAT_MODELS:
        assert "tts" not in m, f"{m} looks like a TTS model and shouldn't be in chat list"


def test_mimo_base_url_is_token_plan_v1():
    assert MIMO_BASE_URL == "https://token-plan-cn.xiaomimimo.com/v1"
