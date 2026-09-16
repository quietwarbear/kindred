"""AI calls must carry their instructions as a system message.

litellm forwards unknown keyword arguments to the provider, so `system_prompt=`
was rejected: "Unrecognized request argument supplied: system_prompt" (Sentry
KINDRED-BACKEND-1). That broke the Ubuntu Guide briefing, AI gathering plans and
history, oral-history translation, and memory tagging — each one silently fell
back while looking healthy.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
AI_MODULES = ("ai_gathering.py", "ai_oralhistory.py", "ai_steward.py", "ai_tagging.py")


def source(name: str) -> str:
    return (BACKEND / name).read_text()


def test_no_ai_call_passes_system_prompt_to_the_provider():
    for name in AI_MODULES:
        assert "system_prompt=" not in source(name), name


def test_every_ai_call_sends_a_system_message():
    for name in AI_MODULES:
        text = source(name)
        calls = text.count("litellm.acompletion(")
        systems = text.count('{"role": "system", "content"')
        assert calls > 0, name
        assert systems == calls, f"{name}: {systems} system messages for {calls} calls"


def test_system_messages_come_before_the_user_content():
    for name in AI_MODULES:
        text = source(name)
        for call in text.split("litellm.acompletion(")[1:]:
            block = call.split(")", 1)[0]
            system_at = block.find('"role": "system"')
            user_at = block.find('"role": "user"')
            assert system_at != -1, name
            if user_at != -1:
                assert system_at < user_at, name
