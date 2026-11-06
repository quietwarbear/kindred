"""K10: organizer export of an event's memory capsule (ZIP of JSON + media).

The capsule is every memory filed against the event (``memories.event_id``):
stories from the reunion prompt plus photos and voice notes shared to the
event from the memory timeline. Kindred has no object store, so photos and
voice notes live inside the memory document as ``data:`` URLs. The export
decodes each one into its own file under ``media/`` and points at it from
``memories.json``.

What is left out, on purpose:
- Drafts (``capsule_status == "draft"``). Nobody else can see a contributor's
  unpublished draft, so the organizer's export can't either.
- Emails and internal account ids. Contributors appear by display name, the
  same way the capsule shows them.

Because media lives only inside the memory document, deleting a memory (the
contributor's withdraw on the capsule, or ``DELETE /memories/{id}``) deletes
its media with it; there is no separate file to clean up. A later export
simply no longer contains it.

The writer is incremental (one memory at a time) so a large capsule is never
held in memory as a list of decoded files.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import unicodedata
import zipfile
from typing import IO, Any

EXPORT_FORMAT_VERSION = 1
MAX_EXPORT_BYTES = 500 * 1024 * 1024  # decoded media, across the whole capsule

MEDIA_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}

MEDIA_FIELDS = (("image_data_url", "photo"), ("voice_note_data_url", "voice"))

README = """Memory capsule export

memories.json lists every published memory shared to this event, oldest
first. Photos and voice notes are in media/; each memory's "media" entries
name their file. Drafts that contributors have not published are not
included. Contributors are listed by display name only.
"""


class ExportTooLarge(Exception):
    pass


def is_exportable(memory: dict[str, Any]) -> bool:
    return memory.get("capsule_status", "published") != "draft"


def decode_media(data_url: Any) -> tuple[bytes, str] | None:
    """Return ``(bytes, mime)`` for a base64 image/audio data URL, else None."""
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None
    header, sep, payload = data_url.partition(",")
    if not sep or ";base64" not in header:
        return None
    mime = header[5:].split(";", 1)[0].strip().lower()
    if mime not in MEDIA_EXTENSIONS:
        return None
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        return None
    if not raw:
        return None
    return raw, mime


def safe_slug(value: Any, fallback: str = "event") -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:60]
    return slug or fallback


def export_filename(event: dict[str, Any], exported_at: str) -> str:
    return f"memory-capsule-{safe_slug(event.get('title'))}-{exported_at[:10] or 'export'}.zip"


def _media_name(memory_id: str, kind: str, mime: str) -> str:
    return f"media/{safe_slug(memory_id, 'memory')}-{kind}.{MEDIA_EXTENSIONS[mime]}"


def _comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "author_name": str(comment.get("author_name") or comment.get("created_by_name") or ""),
        "text": str(comment.get("text") or ""),
        "created_at": str(comment.get("created_at") or ""),
    }


class CapsuleZipWriter:
    """Write a capsule ZIP into ``fileobj`` one memory at a time."""

    def __init__(self, fileobj: IO[bytes], *, max_bytes: int = MAX_EXPORT_BYTES):
        self._zip = zipfile.ZipFile(fileobj, "w", compression=zipfile.ZIP_DEFLATED)
        self._entries: list[dict[str, Any]] = []
        self._names: set[str] = set()
        self._bytes = 0
        self._max = max_bytes
        self.media_files = 0
        self.skipped_media = 0

    def add(self, memory: dict[str, Any]) -> None:
        if not is_exportable(memory):
            return
        memory_id = str(memory.get("id") or f"memory-{len(self._entries) + 1}")
        media: list[dict[str, Any]] = []
        for field, kind in MEDIA_FIELDS:
            if not memory.get(field):
                continue
            decoded = decode_media(memory.get(field))
            if decoded is None:
                self.skipped_media += 1
                media.append({"kind": kind, "file": None, "note": "Could not be read"})
                continue
            raw, mime = decoded
            self._bytes += len(raw)
            if self._bytes > self._max:
                raise ExportTooLarge()
            name = _media_name(memory_id, kind, mime)
            counter = 2
            while name in self._names:
                stem, ext = name.rsplit(".", 1)
                name = f"{stem}-{counter}.{ext}"
                counter += 1
            self._names.add(name)
            # Photos and audio are already compressed; store them as-is.
            self._zip.writestr(name, raw, compress_type=zipfile.ZIP_STORED)
            self.media_files += 1
            media.append({"kind": kind, "file": name, "mime_type": mime, "size": len(raw)})
        self._entries.append(
            {
                "id": memory_id,
                "title": str(memory.get("title") or ""),
                "story": str(memory.get("description") or ""),
                "category": str(memory.get("category") or ""),
                "tags": [str(tag) for tag in memory.get("tags") or []],
                "contributor_name": str(memory.get("created_by_name") or ""),
                "source": str(memory.get("source") or "timeline"),
                "created_at": str(memory.get("created_at") or ""),
                "updated_at": str(memory.get("updated_at") or ""),
                "media": media,
                "comments": [_comment(c) for c in memory.get("comments") or [] if isinstance(c, dict)],
            }
        )

    def finish(self, event: dict[str, Any], *, exported_at: str) -> dict[str, Any]:
        entries = sorted(self._entries, key=lambda entry: (entry["created_at"], entry["id"]))
        manifest = {
            "format_version": EXPORT_FORMAT_VERSION,
            "exported_at": exported_at,
            "event": {
                "id": str(event.get("id") or ""),
                "title": str(event.get("title") or ""),
                "start_at": str(event.get("start_at") or ""),
                "end_at": str(event.get("end_at") or ""),
                "timezone": str(event.get("timezone") or "UTC"),
            },
            "memory_count": len(entries),
            "media_count": self.media_files,
            "memories": entries,
        }
        self._zip.writestr("memories.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        self._zip.writestr("README.txt", README)
        self._zip.close()
        return {
            "memory_count": len(entries),
            "media_count": self.media_files,
            "skipped_media": self.skipped_media,
        }

    def abort(self) -> None:
        try:
            self._zip.close()
        except Exception:  # pragma: no cover - best effort
            pass
