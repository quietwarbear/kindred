"""Pilot consent & cohort management — a small, content-free state machine.

The Release 13 runbook and launch checklist repeatedly require that a pilot
organizer has *explicitly consented* before any real event is created. This
module turns that manual runbook checkbox into a recorded, platform-admin-gated
state machine on the community, so the cohort and each community's consent are
auditable.

It stores only categorical status, opaque actor/community ids, an optional short
cohort label, and timestamps — never customer content. Recording consent here is
a bookkeeping record of a consent conversation that happens out of band; it does
not itself enable any delivery, provider call, or send.
"""

from __future__ import annotations

from typing import Any

PILOT_STATUSES = frozenset(
    {"not_enrolled", "enrolled", "consented", "active", "completed", "withdrawn"}
)

# action -> (allowed-from statuses, resulting status)
_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "enroll": (frozenset({"not_enrolled", "withdrawn"}), "enrolled"),
    "record_consent": (frozenset({"enrolled"}), "consented"),
    "activate": (frozenset({"consented"}), "active"),
    "complete": (frozenset({"active"}), "completed"),
    "withdraw": (frozenset({"enrolled", "consented", "active"}), "withdrawn"),
}

PILOT_ACTIONS = frozenset(_TRANSITIONS)


class PilotTransitionError(ValueError):
    """A deliberately sanitized invalid-transition signal."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_status(value: Any) -> str:
    status = str(value or "").strip()
    return status if status in PILOT_STATUSES else "not_enrolled"


def allowed_actions(current_status: str) -> list[str]:
    """The actions valid from a given status (for driving the UI)."""
    current = normalize_status(current_status)
    return [
        action
        for action, (allowed_from, _new) in _TRANSITIONS.items()
        if current in allowed_from
    ]


def apply_pilot_action(current_status: Any, action: str) -> str:
    """Return the resulting status for an action, or raise PilotTransitionError."""
    current = normalize_status(current_status)
    if action not in _TRANSITIONS:
        raise PilotTransitionError("unknown_pilot_action")
    allowed_from, new_status = _TRANSITIONS[action]
    if current not in allowed_from:
        raise PilotTransitionError("invalid_pilot_transition")
    return new_status


def public_pilot_record(pilot: dict[str, Any] | None) -> dict[str, Any]:
    """Categorical, content-free view of one community's pilot record."""
    pilot = pilot or {}
    status = normalize_status(pilot.get("status"))
    return {
        "status": status,
        "cohort_label": str(pilot.get("cohort_label") or ""),
        "consented": bool(pilot.get("consented_at")),
        "updated_at": str(pilot.get("updated_at") or ""),
        "allowed_actions": allowed_actions(status),
    }


def pilot_cohort_summary(communities: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the cohort for the admin view.

    Counts every community by status and lists only those actually in the cohort
    (status != not_enrolled). Community id/name are included for the authorized
    platform admin; no customer/member data is ever touched.
    """
    counts = {status: 0 for status in PILOT_STATUSES}
    cohort: list[dict[str, Any]] = []
    available: list[dict[str, str]] = []
    for community in communities:
        record = public_pilot_record(community.get("pilot"))
        counts[record["status"]] += 1
        community_id = str(community.get("id") or "")
        community_name = str(community.get("name") or "")
        if record["status"] != "not_enrolled":
            cohort.append(
                {
                    "community_id": community_id,
                    "community_name": community_name,
                    **record,
                }
            )
        elif community_id:
            available.append(
                {"community_id": community_id, "community_name": community_name}
            )
    return {
        "counts": counts,
        "total_communities": len(communities),
        "cohort_size": len(cohort),
        "cohort": cohort,
        "available": available[:500],
    }
