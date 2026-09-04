"""Offline regression coverage for communication attachment compatibility."""

from models import FileAttachmentPayload


def test_frontend_attachment_shape_is_preserved_in_api_documents():
    attachment = FileAttachmentPayload.model_validate(
        {
            "name": "synthetic-note.txt",
            "data_url": "data:text/plain;base64,c3ludGhldGlj",
            "mime_type": "text/plain",
        }
    )

    assert attachment.model_dump() == {
        "name": "synthetic-note.txt",
        "data_url": "data:text/plain;base64,c3ludGhldGlj",
        "mime_type": "text/plain",
    }


def test_legacy_attachment_keys_remain_accepted_but_normalize_to_current_shape():
    attachment = FileAttachmentPayload.model_validate(
        {
            "file_name": "legacy-note.txt",
            "file_data": "data:text/plain;base64,bGVnYWN5",
            "mime_type": "text/plain",
        }
    )

    assert attachment.model_dump() == {
        "name": "legacy-note.txt",
        "data_url": "data:text/plain;base64,bGVnYWN5",
        "mime_type": "text/plain",
    }
