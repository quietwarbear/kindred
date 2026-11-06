"""Organizer-chosen wording for the group a Kindred space belongs to (K3).

Kindred was built reunion-first, so the interface says "family". Organizers of
other gatherings (a festival, a retreat, a congregation's weekend) can pick the
word their people use instead. This module is the single source of that word
on the server; the frontend mirror is ``frontend/src/lib/groupWording.js`` and
both must agree on presets, length cap and allowed characters.

Storage: ``communities.group_label`` = ``{"preset", "singular", "plural"}``.
A missing or unreadable value always resolves to the "family" preset, so
existing spaces read exactly as before. Events inherit their community's
label; there is no per-event override.

Only words go through here. Plan names (Seedling ... Elder Grove), pricing
copy and the brand line are deliberately untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PRESETS: dict[str, tuple[str, str]] = {
    "family": ("family", "families"),
    "community": ("community", "communities"),
    "congregation": ("congregation", "congregations"),
    "circle": ("circle", "circles"),
    "team": ("team", "teams"),
}
DEFAULT_PRESET = "family"
CUSTOM = "custom"
MAX_LABEL_LENGTH = 24

# Letters (any script) in words joined by single spaces, hyphens or apostrophes.
# No digits, punctuation or markup: the word lands inside emails and sentences.
_WORD = r"[^\W\d_]+"
_LABEL_RE = re.compile(rf"^{_WORD}(?:[ '\-’]{_WORD})*$", re.UNICODE)


class GroupLabelError(ValueError):
    """Raised for an organizer-supplied label that cannot be stored."""


def default_group_label() -> dict[str, str]:
    singular, plural = PRESETS[DEFAULT_PRESET]
    return {"preset": DEFAULT_PRESET, "singular": singular, "plural": plural}


def _clean_word(value: Any, field: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise GroupLabelError(f"Enter the {field} word.")
    if len(text) > MAX_LABEL_LENGTH:
        raise GroupLabelError(
            f"Keep the {field} word to {MAX_LABEL_LENGTH} characters or fewer."
        )
    if not _LABEL_RE.match(text):
        raise GroupLabelError(
            f"Use letters only for the {field} word (spaces, hyphens and apostrophes are fine)."
        )
    return text


def validate_group_label(
    preset: Any, singular: Any = None, plural: Any = None
) -> dict[str, str]:
    """Return the stored form of an organizer's choice, or raise GroupLabelError."""
    key = str(preset or "").strip().lower()
    if key in PRESETS:
        word, words = PRESETS[key]
        return {"preset": key, "singular": word, "plural": words}
    if key != CUSTOM:
        raise GroupLabelError("Choose one of the listed words or a custom one.")
    return {
        "preset": CUSTOM,
        "singular": _clean_word(singular, "singular"),
        "plural": _clean_word(plural, "plural"),
    }


def resolve_group_label(raw: Any) -> dict[str, str]:
    """Read a stored value defensively; anything unreadable means "family"."""
    if not isinstance(raw, dict):
        return default_group_label()
    try:
        return validate_group_label(
            raw.get("preset"), raw.get("singular"), raw.get("plural")
        )
    except GroupLabelError:
        return default_group_label()


def group_label_for_community(community: dict[str, Any] | None) -> dict[str, str]:
    return resolve_group_label((community or {}).get("group_label"))


def _lower_first(word: str) -> str:
    # "Choir" mid-sentence reads "choir"; an all-caps acronym stays as typed.
    if len(word) > 1 and word[1:] == word[1:].lower():
        return word[0].lower() + word[1:]
    return word


def _upper_first(word: str) -> str:
    return word[:1].upper() + word[1:]


@dataclass(frozen=True)
class GroupWording:
    noun: str
    nouns: str

    @property
    def Noun(self) -> str:  # noqa: N802 - mirrors the frontend helper's names
        return _upper_first(self.noun)

    @property
    def Nouns(self) -> str:  # noqa: N802
        return _upper_first(self.nouns)

    @property
    def possessive(self) -> str:
        return f"{self.noun}'s"

    @property
    def Possessive(self) -> str:  # noqa: N802
        return f"{self.Noun}'s"


def wording(label: dict[str, Any] | None) -> GroupWording:
    resolved = resolve_group_label(label)
    return GroupWording(
        noun=_lower_first(resolved["singular"]),
        nouns=_lower_first(resolved["plural"]),
    )


def wording_for_community(community: dict[str, Any] | None) -> GroupWording:
    return wording(group_label_for_community(community))


async def wording_for_community_id(community_id: str | None) -> GroupWording:
    """Look up a community's wording; any lookup failure falls back to family."""
    if not community_id:
        return wording(None)
    from db import communities_collection

    try:
        community = await communities_collection.find_one(
            {"id": community_id}, {"_id": 0, "group_label": 1}
        )
    except Exception:  # pragma: no cover - wording must never break a send
        community = None
    return wording_for_community(community)
