from siftivex.tag_vocabulary import build_system_prompt
from siftivex.vlm import build_vlm_chat_payload


def test_build_vlm_chat_payload_thinking_disabled():
    payload = build_vlm_chat_payload(
        {"model": "m", "enable_thinking": False, "max_tokens": 100},
        system_prompt="sys",
        user_text="user",
        data_url="data:image/jpeg;base64,xx",
    )
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert "thinking_budget_tokens" not in payload


def test_build_vlm_chat_payload_thinking_enabled_with_budget():
    payload = build_vlm_chat_payload(
        {
            "model": "m",
            "enable_thinking": True,
            "thinking_budget_tokens": 256,
            "max_tokens": 2048,
        },
        system_prompt="sys",
        user_text="user",
        data_url="data:image/jpeg;base64,xx",
    )
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["thinking_budget_tokens"] == 256


def test_build_system_prompt_thinking_mode():
    prompt = build_system_prompt({}, enable_thinking=True, max_thinking_chars=300)
    assert "under 300 characters" in prompt
    assert "no thinking" not in prompt
