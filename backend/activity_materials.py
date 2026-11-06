"""K6 per-activity materials: validated file uploads for one activity.

File metadata sits on the event (``activity_materials``) so the serializers can
gate it like the virtual link without a database round trip. File bytes sit in
``activity_material_files`` so event reads never carry them.

The type is decided by the file's own leading bytes, never by the name or the
client's claimed MIME type, and only PDFs and common images are accepted.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from typing import Any

from fastapi import HTTPException, status

MAX_MATERIAL_BYTES = 5 * 1024 * 1024
MAX_MATERIALS_PER_ACTIVITY = 10
MAX_MATERIALS_PER_EVENT = 100
MAX_MATERIAL_NAME_LENGTH = 120

ALLOWED_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def sniff_material_type(data: bytes) -> str | None:
    """Return the MIME type implied by the file's leading bytes, if allowed."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _reject(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=http_status, detail={"code": code, "message": message})


def decode_material_data_url(data_url: str) -> bytes:
    """Decode a ``data:...;base64,`` URL (or bare base64) with a size cap."""
    raw = str(data_url or "").strip()
    if raw.startswith("data:"):
        header, _, raw = raw.partition(",")
        if ";base64" not in header:
            _reject("material_encoding", "Files must be sent base64-encoded.")
    # Base64 inflates by 4/3; refuse oversized input before decoding it.
    if len(raw) > (MAX_MATERIAL_BYTES * 4) // 3 + 8:
        _reject(
            "material_too_large",
            "Files can be up to 5 MB.",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        _reject("material_encoding", "That file could not be read.")
    if not data:
        _reject("material_empty", "That file is empty.")
    if len(data) > MAX_MATERIAL_BYTES:
        _reject(
            "material_too_large",
            "Files can be up to 5 MB.",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    return data


def safe_material_name(name: str, mime_type: str) -> str:
    """Return a display/download name with a matching extension and no paths."""
    text = unicodedata.normalize("NFKC", str(name or "")).replace("\\", "/")
    text = text.rsplit("/", 1)[-1]
    text = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", text).strip(" .")
    extension = ALLOWED_EXTENSIONS[mime_type]
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", text) or "material"
    stem = stem[: MAX_MATERIAL_NAME_LENGTH - len(extension)].rstrip(" .") or "material"
    return f"{stem}{extension}"


def validate_material_upload(name: str, data_url: str) -> tuple[bytes, str, str]:
    """Return ``(bytes, mime_type, safe_name)`` or raise a 4xx HTTPException."""
    data = decode_material_data_url(data_url)
    mime_type = sniff_material_type(data)
    if not mime_type:
        _reject(
            "material_type",
            "Only PDF, PNG, JPEG, GIF and WebP files can be attached.",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    return data, mime_type, safe_material_name(name, mime_type)


def content_disposition(name: str) -> str:
    """An RFC 6266 attachment header with an ASCII fallback and UTF-8 name."""
    from urllib.parse import quote

    ascii_name = name.encode("ascii", "ignore").decode() or "material"
    ascii_name = ascii_name.replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def material_download_headers(name: str) -> dict[str, str]:
    return {
        "Content-Disposition": content_disposition(name),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }


def find_material(event: dict[str, Any], material_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in event.get("activity_materials") or []
            if row.get("id") == material_id
        ),
        None,
    )
