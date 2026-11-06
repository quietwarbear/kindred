"""K12: invitation and announcement emails are readable by assistive tech.

- A language is declared, so screen readers pick the right voice.
- Footer text meets WCAG AA contrast (4.5:1) on the white card.
"""

from __future__ import annotations

import os
import re

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k12_unit")

import event_messaging  # noqa: E402
import invitation_delivery  # noqa: E402


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_on_white(hex_color: str) -> float:
    return 1.05 / (_luminance(hex_color) + 0.05)


def _text_colors(html: str) -> set[str]:
    return {match.lower() for match in re.findall(r"(?<!background:)color:#([0-9a-fA-F]{6})", html)}


def _sources():
    return {
        "event_messaging": open(event_messaging.__file__, encoding="utf-8").read(),
        "invitation_delivery": open(invitation_delivery.__file__, encoding="utf-8").read(),
    }


def test_emails_declare_language_and_charset():
    page = event_messaging._page("<p>Hi</p>")
    assert page.startswith('<!doctype html><html lang="en"><head><meta charset="utf-8"></head>')
    for name, source in _sources().items():
        assert "<html><body" not in source, name


def test_email_text_colors_meet_aa_on_white():
    for name, source in _sources().items():
        for color in _text_colors(source):
            if color == "ffffff":
                continue  # white text on the coloured button
            assert _contrast_on_white(color) >= 4.5, (name, color)


def test_announcement_footer_is_readable():
    footer = event_messaging._footer("https://app.example.invalid/unsubscribe", "An organizer")
    for color in _text_colors(footer):
        assert _contrast_on_white(color) >= 4.5
