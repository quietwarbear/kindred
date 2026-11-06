"""K10: organizer export of an event's memory capsule, and contributor delete.

- The export is a ZIP: memories.json (stories, names, comments, pointers)
  plus every photo and voice note decoded under media/.
- Drafts, emails and account ids never appear in it.
- Organizer-only.
- Media lives only inside the memory document, so a contributor's delete
  removes it, and the next export no longer contains it.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_k10_export_unit")

from capsule_export import (  # noqa: E402
    CapsuleZipWriter,
    ExportTooLarge,
    decode_media,
    export_filename,
)
from routes import reunion_memories as capsule_routes  # noqa: E402
from routes import timeline as timeline_routes  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
OGG = b"OggS" + b"\x01" * 40
NOW = "2026-11-30T12:00:00+00:00"


def data_url(mime, raw):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


EVENT = {"id": "event-1", "community_id": "c-1", "title": "Harvest Gathering 2026", "start_at": "2026-11-27T12:00", "timezone": "UTC"}


def memory(memory_id, **extra):
    base = {
        "id": memory_id,
        "community_id": "c-1",
        "event_id": "event-1",
        "title": "A story",
        "description": f"Story {memory_id}",
        "created_by": f"user-{memory_id}",
        "created_by_name": f"Person {memory_id}",
        "created_by_email": f"{memory_id}@example.invalid",
        "image_data_url": "",
        "voice_note_data_url": "",
        "comments": [],
        "tags": [],
        "created_at": f"2026-11-28T00:00:0{memory_id[-1]}+00:00",
    }
    base.update(extra)
    return base


def build(memories, **kwargs):
    buffer = io.BytesIO()
    writer = CapsuleZipWriter(buffer, **kwargs)
    for item in memories:
        writer.add(item)
    counts = writer.finish(EVENT, exported_at=NOW)
    buffer.seek(0)
    return zipfile.ZipFile(buffer), counts


def manifest(archive):
    return json.loads(archive.read("memories.json"))


# ---------------------------------------------------------------------------
# The ZIP
# ---------------------------------------------------------------------------


def test_zip_holds_json_and_decoded_media():
    archive, counts = build(
        [
            memory("m1", image_data_url=data_url("image/png", PNG), comments=[{"author_name": "Cy", "text": "Love this", "created_at": NOW}]),
            memory("m2", voice_note_data_url=data_url("audio/ogg", OGG)),
            memory("m3"),
        ]
    )
    names = set(archive.namelist())
    assert {"memories.json", "README.txt", "media/m1-photo.png", "media/m2-voice.ogg"} <= names
    assert archive.read("media/m1-photo.png") == PNG
    assert archive.read("media/m2-voice.ogg") == OGG
    data = manifest(archive)
    assert data["event"]["title"] == "Harvest Gathering 2026"
    assert data["memory_count"] == 3 and data["media_count"] == 2
    first = data["memories"][0]
    assert first["story"] == "Story m1" and first["contributor_name"] == "Person m1"
    assert first["media"] == [{"kind": "photo", "file": "media/m1-photo.png", "mime_type": "image/png", "size": len(PNG)}]
    assert first["comments"] == [{"author_name": "Cy", "text": "Love this", "created_at": NOW}]
    assert counts == {"memory_count": 3, "media_count": 2, "skipped_media": 0}


def test_media_is_stored_uncompressed_and_json_compressed():
    archive, _ = build([memory("m1", image_data_url=data_url("image/png", PNG))])
    assert archive.getinfo("media/m1-photo.png").compress_type == zipfile.ZIP_STORED
    assert archive.getinfo("memories.json").compress_type == zipfile.ZIP_DEFLATED


def test_drafts_are_never_exported():
    archive, counts = build([memory("m1"), memory("m2", capsule_status="draft", image_data_url=data_url("image/png", PNG))])
    data = manifest(archive)
    assert [m["id"] for m in data["memories"]] == ["m1"]
    assert not any(name.startswith("media/") for name in archive.namelist())
    assert counts["media_count"] == 0


def test_no_emails_or_account_ids_leave_in_the_export():
    archive, _ = build([memory("m1"), memory("m2")])
    raw = archive.read("memories.json").decode()
    assert "@" not in raw
    assert "user-m1" not in raw and "created_by" not in raw


def test_unreadable_media_is_noted_not_fatal():
    archive, counts = build(
        [
            memory("m1", image_data_url="https://elsewhere.invalid/photo.png"),
            memory("m2", voice_note_data_url="data:text/html;base64,PHNjcmlwdD4="),
        ]
    )
    data = manifest(archive)
    assert data["memories"][0]["media"] == [{"kind": "photo", "file": None, "note": "Could not be read"}]
    assert counts["skipped_media"] == 2
    assert not any(name.startswith("media/") for name in archive.namelist())


def test_media_names_are_safe_and_unique():
    archive, _ = build(
        [
            memory("../../etc/m1", image_data_url=data_url("image/png", PNG)),
            memory("..-..-etc-m1", image_data_url=data_url("image/png", PNG)),
        ]
    )
    media = sorted(name for name in archive.namelist() if name.startswith("media/"))
    assert media == ["media/etc-m1-photo-2.png", "media/etc-m1-photo.png"]
    assert all(".." not in name for name in archive.namelist())


def test_size_cap_refuses_huge_capsules():
    with pytest.raises(ExportTooLarge):
        build([memory("m1", image_data_url=data_url("image/png", PNG))], max_bytes=10)


def test_decode_media_and_filename():
    assert decode_media(data_url("image/jpeg", b"\xff\xd8\xff")) == (b"\xff\xd8\xff", "image/jpeg")
    assert decode_media("data:image/png,notbase64") is None
    assert decode_media(None) is None
    assert export_filename({"title": "Fête d'été!"}, NOW) == "memory-capsule-fete-d-ete-2026-11-30.zip"
    assert export_filename({}, NOW) == "memory-capsule-event-2026-11-30.zip"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


def _matches(doc, query):
    for key, expected in query.items():
        if isinstance(expected, dict) and "$ne" in expected:
            if doc.get(key, None) == expected["$ne"]:
                return False
        elif doc.get(key) != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return deepcopy(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class _Memories:
    def __init__(self, docs):
        self.docs = [deepcopy(d) for d in docs]

    def find(self, query, _projection=None):
        return _Cursor([d for d in self.docs if _matches(d, query)])

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return type("R", (), {"deleted_count": before - len(self.docs)})()


ORGANIZER = {"id": "org-1", "role": "organizer", "community_id": "c-1", "full_name": "Organizer"}
MEMBER = {"id": "user-m1", "role": "member", "community_id": "c-1", "full_name": "Person m1"}


@pytest.fixture
def store(monkeypatch):
    memories = _Memories(
        [
            memory("m1", image_data_url=data_url("image/png", PNG), voice_note_data_url=data_url("audio/ogg", OGG)),
            memory("m2"),
            memory("m3", community_id="c-2"),
            memory("m4", event_id="event-2"),
        ]
    )

    async def event_for_user(event_id, _user):
        if event_id != "event-1":
            raise HTTPException(status_code=404)
        return deepcopy(EVENT)

    monkeypatch.setattr(capsule_routes, "memories_collection", memories)
    monkeypatch.setattr(capsule_routes, "get_event_for_user", event_for_user)
    monkeypatch.setattr(timeline_routes, "memories_collection", memories)
    return memories


async def _download(user):
    response = await capsule_routes.export_reunion_memory_capsule("event-1", user)
    body = b"".join([chunk async for chunk in response.body_iterator])
    return response, zipfile.ZipFile(io.BytesIO(body))


@pytest.mark.asyncio
async def test_export_route_is_organizer_only(store):
    with pytest.raises(HTTPException) as exc:
        await capsule_routes.export_reunion_memory_capsule("event-1", MEMBER)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_export_route_streams_only_this_events_memories(store):
    response, archive = await _download(ORGANIZER)
    assert response.media_type == "application/zip"
    assert 'filename="memory-capsule-harvest-gathering-2026-' in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "private, no-store"
    assert [m["id"] for m in manifest(archive)["memories"]] == ["m1", "m2"]
    assert archive.read("media/m1-voice.ogg") == OGG


@pytest.mark.asyncio
async def test_export_route_refuses_oversized_capsule(store, monkeypatch):
    monkeypatch.setattr(capsule_routes, "CapsuleZipWriter", lambda f: CapsuleZipWriter(f, max_bytes=10))
    with pytest.raises(HTTPException) as exc:
        await capsule_routes.export_reunion_memory_capsule("event-1", ORGANIZER)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_contributor_delete_removes_media_from_the_capsule(store, monkeypatch):
    async def own_memory(memory_id, _user):
        return next(d for d in store.docs if d["id"] == memory_id)

    monkeypatch.setattr(timeline_routes, "get_memory_for_user", own_memory)
    assert await timeline_routes.delete_memory("m1", MEMBER) == {"ok": True}
    # The document that held the photo and voice note is gone...
    assert not any(d["id"] == "m1" for d in store.docs)
    assert not any(PNG_B64 in json.dumps(d) for d in store.docs)
    # ...and the next export has no trace of it.
    _response, archive = await _download(ORGANIZER)
    assert [m["id"] for m in manifest(archive)["memories"]] == ["m2"]
    assert not any(name.startswith("media/") for name in archive.namelist())


PNG_B64 = base64.b64encode(PNG).decode()


def test_memory_media_is_only_stored_on_memory_documents():
    """Guard: if media is ever copied into another collection or onto disk,
    contributor delete must clean that copy too. Fail loudly so it does.
    """
    backend = Path(__file__).resolve().parent.parent
    allowed = {"models.py", "ai_tagging.py", "capsule_export.py", "routes/timeline.py", "routes/reunion_memories.py"}
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(("tests/", "venv", ".venv")) or rel in allowed:
            continue
        if re.search(r"image_data_url|voice_note_data_url", path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == []
