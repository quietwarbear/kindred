import json
import re
import uuid

from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage


SYSTEM_PROMPT = """
You create culturally respectful memory tags for private communities.
Return ONLY compact JSON using this exact shape:
{"tags": ["tag one", "tag two"], "summary": "one sentence summary"}

Rules:
- Create 3 to 6 short tags.
- Keep tags lowercase and human-friendly.
- Prefer relational/community tags like family branch, ministry, worship, reunion, elders, youth, testimony, service, remembrance.
- Never invent names that are not supported by the input.
- Summary must be 8 to 18 words.
""".strip()


def _clean_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    return json.loads(cleaned.strip())


def _heuristic_tags(
    community_type: str,
    title: str,
    description: str,
    event_title: str,
    special_focus: str,
) -> dict:
    corpus = " ".join(
        [community_type or "", title or "", description or "", event_title or "", special_focus or ""]
    ).lower()
    tags: list[str] = []

    keyword_map = {
        "family": "family legacy",
        "reunion": "reunion",
        "church": "church life",
        "ministry": "ministry",
        "worship": "worship",
        "sermon": "sermon archive",
        "elder": "elders",
        "youth": "youth reflections",
        "choir": "choir",
        "prayer": "prayer",
        "community": "community archive",
        "volunteer": "service",
        "potluck": "shared table",
        "history": "oral history",
        "memory": "memory vault",
        "story": "story thread",
    }

    for keyword, tag in keyword_map.items():
        if keyword in corpus and tag not in tags:
            tags.append(tag)

    if community_type and community_type.lower() not in corpus:
        tags.append(community_type.lower())

    if not tags:
        tags = ["community archive", "shared memory", "legacy"]

    return {
        "tags": tags[:6],
        "summary": f"{title or 'Community memory'} preserved for {community_type or 'the community'} archives.",
    }


async def generate_memory_tags(
    api_key: str,
    model: str,
    community_name: str,
    community_type: str,
    title: str,
    description: str,
    event_title: str,
    special_focus: str,
    image_data_url: str | None = None,
) -> dict:
    fallback = _heuristic_tags(community_type, title, description, event_title, special_focus)
    if not api_key or not model:
        return fallback

    try:
        prompt = f"""
Community: {community_name}
Community type: {community_type}
Memory title: {title}
Memory description: {description}
Related event: {event_title}
Special focus: {special_focus}

Return the JSON only.
""".strip()

        file_contents = []
        if image_data_url and image_data_url.startswith("data:image") and "," in image_data_url:
            file_contents.append(ImageContent(image_data_url.split(",", 1)[1]))

        chat = LlmChat(
            api_key=api_key,
            session_id=str(uuid.uuid4()),
            system_message=SYSTEM_PROMPT,
        ).with_model("gemini", model).with_params(temperature=0.3)

        raw = await chat.send_message(UserMessage(text=prompt, file_contents=file_contents))
        parsed = _clean_json(raw)
        tags = parsed.get("tags", []) if isinstance(parsed, dict) else []
        summary = parsed.get("summary") if isinstance(parsed, dict) else None

        normalized_tags = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip() and tag.strip().lower() not in normalized_tags:
                normalized_tags.append(tag.strip().lower())

        if not normalized_tags:
            return fallback

        return {
            "tags": normalized_tags[:6],
            "summary": summary or fallback["summary"],
        }
    except Exception:
        return fallback