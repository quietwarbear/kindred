import base64
import json
import os
import re
import uuid

import litellm


SYSTEM_PROMPT = """
You create culturally respectful memory tags for private communities.
Return ONLY compact JSON using this exact shape:
{"tags": ["tag one", "tag two"], "summary": "one sentence summary", "sentiment": "positive|neutral|reflective|celebratory|somber", "mood": "one or two word mood"}

Rules:
- Create 3 to 6 short tags.
- Keep tags lowercase and human-friendly.
- Prefer relational/community tags like family branch, ministry, worship, reunion, elders, youth, testimony, service, remembrance.
- Never invent names that are not supported by the input.
- Summary must be 8 to 18 words.
- Sentiment must be one of: positive, neutral, reflective, celebratory, somber.
- Mood is a brief emotional descriptor (e.g., "joyful", "nostalgic", "grateful", "reverent").
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
        "celebration": "celebration",
        "graduation": "milestone",
        "wedding": "celebration",
        "birthday": "birthday",
        "funeral": "remembrance",
        "memorial": "remembrance",
        "baptism": "baptism",
    }

    for keyword, tag in keyword_map.items():
        if keyword in corpus and tag not in tags:
            tags.append(tag)

    if community_type and community_type.lower() not in corpus:
        tags.append(community_type.lower())

    if not tags:
        tags = ["community archive", "shared memory", "legacy"]

    # Simple heuristic sentiment
    sentiment = "neutral"
    positive_words = {"joy", "celebrate", "happy", "grateful", "blessed", "wonderful", "love"}
    reflective_words = {"remember", "reflect", "legacy", "history", "passed", "honor"}
    if any(w in corpus for w in positive_words):
        sentiment = "positive"
    elif any(w in corpus for w in reflective_words):
        sentiment = "reflective"

    return {
        "tags": tags[:6],
        "summary": f"{title or 'Community memory'} preserved for {community_type or 'the community'} archives.",
        "sentiment": sentiment,
        "mood": "nostalgic" if sentiment == "reflective" else "warm",
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

        # Build messages for litellm
        # Note: Using OPENAI_API_KEY environment variable. Set GOOGLE_CLIENT_ID if using Google models.
        messages = [{"role": "user", "content": prompt}]

        # Add image to message if provided
        if image_data_url and image_data_url.startswith("data:image") and "," in image_data_url:
            # Extract base64 data and media type from data URL
            header, data = image_data_url.split(",", 1)
            media_type = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"

            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}}
                ]
            }]

        # Use litellm.acompletion for async calls with LLM provider
        # Supports multiple providers: openai, gemini, claude, etc.
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            api_key=api_key,
            temperature=0.3,
        )

        raw = response.choices[0].message.content
        parsed = _clean_json(raw)
        tags = parsed.get("tags", []) if isinstance(parsed, dict) else []
        summary = parsed.get("summary") if isinstance(parsed, dict) else None
        sentiment = parsed.get("sentiment", "neutral") if isinstance(parsed, dict) else "neutral"
        mood = parsed.get("mood", "warm") if isinstance(parsed, dict) else "warm"

        normalized_tags = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip() and tag.strip().lower() not in normalized_tags:
                normalized_tags.append(tag.strip().lower())

        if not normalized_tags:
            return fallback

        valid_sentiments = {"positive", "neutral", "reflective", "celebratory", "somber"}
        if sentiment not in valid_sentiments:
            sentiment = "neutral"

        return {
            "tags": normalized_tags[:6],
            "summary": summary or fallback["summary"],
            "sentiment": sentiment,
            "mood": mood[:30] if mood else "warm",
        }
    except Exception:
        return fallback


async def batch_retag_memories(
    api_key: str,
    model: str,
    memories: list[dict],
    community_name: str,
    community_type: str,
) -> list[dict]:
    """Re-tag a batch of memories with improved AI analysis."""
    results = []
    for memory in memories:
        result = await generate_memory_tags(
            api_key=api_key,
            model=model,
            community_name=community_name,
            community_type=community_type,
            title=memory.get("title", ""),
            description=memory.get("description", ""),
            event_title=memory.get("event_title", ""),
            special_focus="",
            image_data_url=memory.get("image_data_url"),
        )
        results.append({"memory_id": memory["id"], **result})
    return results
