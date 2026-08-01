"""Synthetic Stage 12B grant, authorization, and privacy regressions."""

import os
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_stage12b_unit")

import pytest

from legacy_table_transfer import (
    TRANSFER_CONSENT_VERSION,
    TransferFailure,
    require_transfer_configuration,
    revision_digest,
    transfer_configuration,
    validate_owned_recipe,
)
from models import LegacyTableTransferAcknowledgement, LegacyTableTransferStartRequest

BASE_THREAD = {
    "id": "synthetic-recipe-thread",
    "created_by": "synthetic-author",
    "category": "recipe-tradition",
    "title": "Synthetic dish",
    "body": "Synthetic preparation notes.",
    "revision": 1,
}
AUTHOR = {"id": "synthetic-author", "role": "member"}


def configure(monkeypatch):
    monkeypatch.setenv("LEGACY_TABLE_TRANSFER_ENABLED", "true")
    monkeypatch.setenv("LEGACY_TABLE_TRANSFER_HASH_KEY", "s" * 48)
    monkeypatch.setenv("LEGACY_TABLE_API_ORIGIN", "https://api.legacytable.app")
    monkeypatch.setenv("LEGACY_TABLE_WEB_ORIGIN", "https://legacytable.app")
    monkeypatch.setenv("UBUNTU_SSO_SECRET", "synthetic-only")


@pytest.mark.parametrize(
    "missing",
    [
        "LEGACY_TABLE_TRANSFER_ENABLED",
        "LEGACY_TABLE_TRANSFER_HASH_KEY",
        "LEGACY_TABLE_API_ORIGIN",
        "LEGACY_TABLE_WEB_ORIGIN",
        "UBUNTU_SSO_SECRET",
    ],
)
def test_every_configuration_preflight_fails_closed(monkeypatch, missing):
    configure(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    assert transfer_configuration()["ready"] is False
    with pytest.raises(TransferFailure, match="transfer_configuration_unavailable"):
        require_transfer_configuration()


def test_exact_configuration_is_required_and_values_are_not_projected(monkeypatch):
    configure(monkeypatch)
    result = transfer_configuration()
    assert result == {
        "status": "ready",
        "ready": True,
        "api_origin": "https://api.legacytable.app",
        "web_origin": "https://legacytable.app",
    }
    assert "synthetic-only" not in repr(result)
    assert "s" * 48 not in repr(result)


@pytest.mark.parametrize(
    "change",
    [
        {"created_by": "another-author"},
        {"category": "oral-history"},
        {"hidden": True},
        {"deleted_at": "2026-01-01T00:00:00Z"},
        {"withdrawn_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_author_only_eligible_recipe_gate(change):
    with pytest.raises(TransferFailure, match="transfer_not_found"):
        validate_owned_recipe(BASE_THREAD | change, AUTHOR)
    validate_owned_recipe(BASE_THREAD, AUTHOR)


def test_immutable_revision_digest_changes_for_selected_content_only():
    baseline = revision_digest(BASE_THREAD)
    assert revision_digest(dict(BASE_THREAD)) == baseline
    assert revision_digest(BASE_THREAD | {"title": "Changed"}) != baseline
    assert revision_digest(BASE_THREAD | {"body": "Changed"}) != baseline
    assert revision_digest(BASE_THREAD | {"revision": 2}) != baseline
    assert (
        revision_digest(BASE_THREAD | {"comments": [{"private": "ignored"}]})
        == baseline
    )


def test_explicit_consent_and_acknowledgement_schemas_are_closed():
    with pytest.raises(Exception):
        LegacyTableTransferStartRequest(
            thread_id="synthetic-recipe-thread", consent_confirmed=False
        )
    with pytest.raises(Exception):
        LegacyTableTransferStartRequest.model_validate(
            {
                "thread_id": "synthetic-recipe-thread",
                "consent_confirmed": True,
                "extra": "no",
            }
        )
    acknowledgement = LegacyTableTransferAcknowledgement(
        operation_id="ltop_synthetic_operation",
        source_revision_digest="a" * 64,
        status="accepted",
        receipt_reference="ltr_synthetic_receipt",
    )
    assert acknowledgement.model_dump(exclude_none=True)["status"] == "accepted"
    assert TRANSFER_CONSENT_VERSION == "kindred_recipe_import_v1"


def test_routes_keep_grants_out_of_paths_queries_and_logging():
    route_source = (Path(__file__).parents[1] / "routes" / "legacy.py").read_text()
    transfer_source = (
        Path(__file__).parents[1] / "legacy_table_transfer.py"
    ).read_text()
    assert 'alias="X-Kindred-Transfer"' in route_source
    assert "/transfer-payload/{" not in route_source
    assert "/transfer-acknowledgement/{" not in route_source
    assert "logger." not in route_source
    assert "logger." not in transfer_source
    assert '"grant_digest"' in transfer_source
    assert '"credential":' not in transfer_source
