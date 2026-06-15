"""Living oral history — turn voice notes into preserved, translated text.

Two capabilities, both best-effort and graceful (return "" on any failure rather than
breaking the request):

- transcribe_audio: Whisper transcription of a captured voice note (data URL) via litellm.
- translate_text: render a story into the community's languages (Spanish + Yoruba) via the
  text model, so a grandmother's words reach the grandchildren who read another tongue.

Reuses OPENAI_API_KEY / GEMINI_MODEL (the default gpt-4o-mini is OpenAI under the hood, so
Whisper transcription works with the same key).
"""

import base64
import io
import json
import re

import litellm

_EXT_BY_MIME = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}

TRANSLATE_SYSTEM = """
You are a careful, warm translator preserving meaning, tone, names, and cultural nuance.
Return ONLY compact JSON: {"es": "...", "yo": "..."}.
Translate the user's text into Spanish (es) and Yoruba (yo). Keep personal names and place
names unchanged. Preserve the heartfelt, plain voice of the original.
""".strip()


def _clean_json(raw: str) -> dict:
    s = (raw or "").strip()
    s = re.sub(r"^```json", "", s)
    s = re.sub(r"^```", "", s)
    s = re.sub(r"```$", "", s)
    return json.loads(s.strip())


async def transcribe_audio(api_key: str, audio_data_url: str) -> str:
    """Transcribe a base64 audio data URL via Whisper. Returns "" on any failure."""
    if not api_key or not audio_data_url or "," not in audio_data_url:
        return ""
    try:
        header, b64 = audio_data_url.split(",", 1)
        mime = header.split(":")[1].split(";")[0] if ":" in header else "audio/webm"
        ext = _EXT_BY_MIME.get(mime, "webm")
        audio_bytes = base64.b64decode(b64)
        if not audio_bytes or len(audio_bytes) > 25 * 1024 * 1024:  # Whisper's 25MB cap
            return ""
        buf = io.BytesIO(audio_bytes)
        buf.name = f"voice.{ext}"
        resp = await litellm.atranscription(model="whisper-1", file=buf, api_key=api_key)
        text = getattr(resp, "text", None)
        if text is None and isinstance(resp, dict):
            text = resp.get("text", "")
        return (text or "").strip()
    except Exception:
        return ""


async def translate_text(api_key: str, model: str, text: str) -> dict:
    """Translate text to Spanish + Yoruba. Returns {"es": "", "yo": ""} on failure."""
    text = (text or "").strip()
    if not text or not api_key or not model:
        return {"es": "", "yo": ""}
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": text}],
            system_prompt=TRANSLATE_SYSTEM,
            api_key=api_key,
            temperature=0.2,
        )
        data = _clean_json(resp.choices[0].message.content)
        if not isinstance(data, dict):
            return {"es": "", "yo": ""}
        return {"es": str(data.get("es", "")).strip(), "yo": str(data.get("yo", "")).strip()}
    except Exception:
        return {"es": "", "yo": ""}
