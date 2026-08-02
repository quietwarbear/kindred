"""Release 17 — pilot consent & cohort management (synthetic, content-free)."""

import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "kindred_release17_unit")
# Admin authority is derived server-side from this env against the user's email,
# never from a stored is_platform_admin flag.
os.environ["PLATFORM_ADMIN_EMAIL"] = "admin@pilot.invalid"

import pytest
from fastapi import HTTPException

from models import PilotCohortActionRequest
from pilot_cohort import (
    PilotTransitionError,
    allowed_actions,
    apply_pilot_action,
    pilot_cohort_summary,
    public_pilot_record,
)
from routes import pilot

ADMIN = {"id": "admin-1", "email": "admin@pilot.invalid"}
NON_ADMIN = {"id": "user-1", "email": "user@pilot.invalid"}
# A user carrying a forged is_platform_admin flag but the wrong email must be
# denied — the gate never trusts the stored flag.
FORGED_ADMIN = {
    "id": "user-2",
    "email": "user@pilot.invalid",
    "is_platform_admin": True,
}


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------


def test_happy_path_transitions():
    assert apply_pilot_action(None, "enroll") == "enrolled"
    assert apply_pilot_action("enrolled", "record_consent") == "consented"
    assert apply_pilot_action("consented", "activate") == "active"
    assert apply_pilot_action("active", "complete") == "completed"


def test_withdraw_and_reenroll():
    assert apply_pilot_action("consented", "withdraw") == "withdrawn"
    assert apply_pilot_action("withdrawn", "enroll") == "enrolled"


def test_invalid_transitions_fail_closed():
    for current, action in [
        (None, "activate"),  # can't activate before enrolled+consented
        ("enrolled", "activate"),  # must consent first
        ("consented", "complete"),  # must activate first
        ("completed", "withdraw"),  # terminal
        ("not_enrolled", "record_consent"),
    ]:
        with pytest.raises(PilotTransitionError) as exc:
            apply_pilot_action(current, action)
        assert exc.value.code == "invalid_pilot_transition"


def test_unknown_action_rejected():
    with pytest.raises(PilotTransitionError) as exc:
        apply_pilot_action("enrolled", "delete_everything")
    assert exc.value.code == "unknown_pilot_action"


def test_allowed_actions_drive_the_ui():
    assert set(allowed_actions("not_enrolled")) == {"enroll"}
    assert set(allowed_actions("enrolled")) == {"record_consent", "withdraw"}
    assert set(allowed_actions("consented")) == {"activate", "withdraw"}
    assert set(allowed_actions("completed")) == set()


def test_public_record_is_categorical():
    record = public_pilot_record(
        {
            "status": "consented",
            "cohort_label": "thanksgiving-2026",
            "consented_at": "2026-11-01T00:00:00+00:00",
            "consent_by": "admin-1",
            "updated_at": "2026-11-01T00:00:00+00:00",
        }
    )
    assert record == {
        "status": "consented",
        "cohort_label": "thanksgiving-2026",
        "consented": True,
        "updated_at": "2026-11-01T00:00:00+00:00",
        "allowed_actions": ["activate", "withdraw"],
    }
    assert public_pilot_record(None)["status"] == "not_enrolled"


def test_cohort_summary_counts_and_is_content_free():
    communities = [
        {"id": "c1", "name": "Toure Family", "pilot": {"status": "consented"}},
        {"id": "c2", "name": "Second Baptist", "pilot": {"status": "enrolled"}},
        {"id": "c3", "name": "Not In Pilot"},  # not_enrolled
    ]
    summary = pilot_cohort_summary(communities)
    assert summary["total_communities"] == 3
    assert summary["cohort_size"] == 2  # only c1, c2 are in the cohort
    assert summary["counts"]["consented"] == 1
    assert summary["counts"]["enrolled"] == 1
    assert summary["counts"]["not_enrolled"] == 1
    # c3 (not enrolled) is offered as available to enroll — id + name only.
    assert summary["available"] == [
        {"community_id": "c3", "community_name": "Not In Pilot"}
    ]
    # The listed cohort carries only categorical/opaque fields (+ admin-visible id/name).
    for entry in summary["cohort"]:
        assert set(entry) == {
            "community_id",
            "community_name",
            "status",
            "cohort_label",
            "consented",
            "updated_at",
            "allowed_actions",
        }


# --------------------------------------------------------------------------
# Endpoint gating
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _FakeCommunities:
    def __init__(self, doc=None, matched_count=1):
        self.doc = doc
        self.updates = []
        self._matched = matched_count

    def find(self, _query, _projection=None):
        docs = [self.doc] if self.doc else []

        class _Cursor:
            async def to_list(self, _n):
                return list(docs)

        return _Cursor()

    async def find_one(self, _query, _projection=None):
        return self.doc

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return _Result(self._matched)


@pytest.mark.asyncio
async def test_cohort_endpoints_require_platform_admin(monkeypatch):
    monkeypatch.setattr(pilot, "communities_collection", _FakeCommunities())
    # Wrong email → denied.
    with pytest.raises(HTTPException) as e1:
        await pilot.get_pilot_cohort(NON_ADMIN)
    assert e1.value.status_code == 403
    with pytest.raises(HTTPException) as e2:
        await pilot.pilot_cohort_action(
            "c1", PilotCohortActionRequest(action="enroll"), NON_ADMIN
        )
    assert e2.value.status_code == 403
    # A forged is_platform_admin flag with the wrong email is still denied.
    with pytest.raises(HTTPException) as e3:
        await pilot.get_pilot_cohort(FORGED_ADMIN)
    assert e3.value.status_code == 403


@pytest.mark.asyncio
async def test_real_admin_email_is_authorized(monkeypatch):
    monkeypatch.setattr(pilot, "communities_collection", _FakeCommunities())
    # The genuine admin (matching PLATFORM_ADMIN_EMAIL) is not denied.
    result = await pilot.get_pilot_cohort(ADMIN)
    assert "counts" in result and "cohort" in result


@pytest.mark.asyncio
async def test_record_consent_requires_confirmation(monkeypatch):
    collection = _FakeCommunities({"id": "c1", "pilot": {"status": "enrolled"}})
    monkeypatch.setattr(pilot, "communities_collection", collection)
    with pytest.raises(HTTPException) as exc:
        await pilot.pilot_cohort_action(
            "c1",
            PilotCohortActionRequest(action="record_consent", consent_confirmed=False),
            ADMIN,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "consent_confirmation_required"
    assert collection.updates == []  # nothing persisted


@pytest.mark.asyncio
async def test_invalid_transition_returns_409(monkeypatch):
    collection = _FakeCommunities({"id": "c1", "pilot": {"status": "enrolled"}})
    monkeypatch.setattr(pilot, "communities_collection", collection)
    with pytest.raises(HTTPException) as exc:
        await pilot.pilot_cohort_action(
            "c1", PilotCohortActionRequest(action="activate"), ADMIN
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "invalid_pilot_transition"
    assert collection.updates == []


@pytest.mark.asyncio
async def test_record_consent_persists_categorical_record(monkeypatch):
    collection = _FakeCommunities({"id": "c1", "pilot": {"status": "enrolled"}})
    monkeypatch.setattr(pilot, "communities_collection", collection)

    async def fake_now():
        return "2026-11-01T00:00:00+00:00"

    monkeypatch.setattr(pilot, "now_iso", lambda: "2026-11-01T00:00:00+00:00")
    result = await pilot.pilot_cohort_action(
        "c1",
        PilotCohortActionRequest(
            action="record_consent", consent_confirmed=True, cohort_label="thanksgiving"
        ),
        ADMIN,
    )
    assert result["pilot"]["status"] == "consented"
    assert result["pilot"]["consented"] is True
    assert result["pilot"]["cohort_label"] == "thanksgiving"
    # Persisted record includes the opaque admin id + consent timestamp.
    _query, update = collection.updates[0]
    persisted = update["$set"]["pilot"]
    assert persisted["status"] == "consented"
    assert persisted["consented_at"] == "2026-11-01T00:00:00+00:00"
    assert persisted["consent_by"] == "admin-1"


@pytest.mark.asyncio
async def test_missing_community_is_404(monkeypatch):
    monkeypatch.setattr(pilot, "communities_collection", _FakeCommunities(None))
    with pytest.raises(HTTPException) as exc:
        await pilot.pilot_cohort_action(
            "nope", PilotCohortActionRequest(action="enroll"), ADMIN
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reenroll_clears_stale_consent(monkeypatch):
    # A withdrawn community that had consented must not report stale consent
    # after being re-enrolled.
    collection = _FakeCommunities(
        {
            "id": "c1",
            "pilot": {
                "status": "withdrawn",
                "consented_at": "2026-10-01T00:00:00+00:00",
                "consent_by": "admin-1",
                "withdrawn_at": "2026-10-05T00:00:00+00:00",
            },
        }
    )
    monkeypatch.setattr(pilot, "communities_collection", collection)
    result = await pilot.pilot_cohort_action(
        "c1", PilotCohortActionRequest(action="enroll"), ADMIN
    )
    assert result["pilot"]["status"] == "enrolled"
    assert result["pilot"]["consented"] is False  # not "ever consented"
    persisted = collection.updates[0][1]["$set"]["pilot"]
    assert "consented_at" not in persisted
    assert "withdrawn_at" not in persisted


@pytest.mark.asyncio
async def test_status_guarded_write_conflicts_when_status_changed(monkeypatch):
    # Simulate a concurrent action having moved the status: the guarded update
    # matches nothing, so this write is rejected instead of clobbering.
    collection = _FakeCommunities(
        {"id": "c1", "pilot": {"status": "enrolled"}}, matched_count=0
    )
    monkeypatch.setattr(pilot, "communities_collection", collection)
    with pytest.raises(HTTPException) as exc:
        await pilot.pilot_cohort_action(
            "c1",
            PilotCohortActionRequest(action="record_consent", consent_confirmed=True),
            ADMIN,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "concurrent_pilot_conflict"
    # The guard filtered on the status we read.
    guard = collection.updates[0][0]
    assert guard["pilot.status"] == "enrolled"
