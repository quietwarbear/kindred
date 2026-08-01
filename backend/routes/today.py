"""Snapshot-consistent, privacy-safe Family Today projection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.read_concern import ReadConcern

from attendee_hub import build_attendee_hub
from db import (
    budget_plans_collection,
    client,
    communities_collection,
    events_collection,
    family_access_requests_collection,
    gathering_proposal_conversions_collection,
    gathering_proposal_responses_collection,
    gathering_proposals_collection,
    invites_collection,
    memories_collection,
    notification_events_collection,
    reunion_recaps_collection,
    travel_plans_collection,
    users_collection,
)
from dependencies import get_current_user, notification_query_for_user
from family_space_activation import ACTIVE, PROVISIONAL, community_lifecycle_state
from organizer_command_center import (
    canonical_response_summary,
    deadline_summary,
    next_best_action,
    planning_progress,
)
from reunion_recap import recap_state, reunion_completion
from rsvp_integrity import member_invite_aliases
from today import (
    build_today_projection,
    opaque_action_reference,
    safe_recent_changes,
)

router = APIRouter(prefix="/api")
_ACTIVE_ROLES = {"member", "organizer", "host"}
_INACTIVE_STATES = {"suspended", "removed", "deleted"}
_STATIC_PATHS = {
    "family_access": "/family/join",
    "family_activation": "/family/activate",
    "family_home": "/home",
    "gathering_proposals": "/proposals",
    "gatherings": "/gatherings",
}


def _not_available() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Family Today is not available."
    )


def _event_tie(event: dict[str, Any]) -> str:
    return "\n".join(
        str(event.get(key) or "") for key in ("start_at", "created_at", "id")
    )


def _dynamic_candidate(
    *,
    actor: dict[str, Any],
    code: str,
    state: str,
    destination_category: str,
    event: dict[str, Any],
    path: str,
) -> tuple[dict[str, Any], tuple[str, str]]:
    reference = opaque_action_reference(
        community_id=actor["community_id"],
        user_id=actor["id"],
        action_code=code,
        subject=str(event["id"]),
    )
    return (
        {
            "code": code,
            "state": state,
            "destination_category": destination_category,
            "action_reference": reference,
            "tie_breaker": _event_tie(event),
        },
        (reference, path),
    )


def _static_candidate(
    code: str, state: str, destination_category: str, tie_breaker: str = ""
) -> dict[str, str]:
    return {
        "code": code,
        "state": state,
        "destination_category": destination_category,
        "tie_breaker": tie_breaker,
    }


async def _canonical_actor(
    current_user: dict[str, Any], *, session
) -> tuple[dict[str, Any], dict[str, Any]]:
    actor = await users_collection.find_one(
        {"id": current_user.get("id")},
        {
            "_id": 0,
            "id": 1,
            "community_id": 1,
            "community_ids": 1,
            "role": 1,
            "full_name": 1,
            "email": 1,
            "email_normalized": 1,
            "account_status": 1,
            "membership_status": 1,
        },
        session=session,
    )
    if (
        not actor
        or actor.get("role") not in _ACTIVE_ROLES
        or actor.get("account_status") in _INACTIVE_STATES
        or actor.get("membership_status") in _INACTIVE_STATES
        or not actor.get("community_id")
    ):
        raise _not_available()
    memberships = {str(item) for item in actor.get("community_ids") or [] if item}
    if memberships and actor["community_id"] not in memberships:
        raise _not_available()
    community = await communities_collection.find_one(
        {"id": actor["community_id"]},
        {"_id": 0, "id": 1, "lifecycle_state": 1},
        session=session,
    )
    if not community:
        raise _not_available()
    return actor, community


def _organizer_role(actor: dict[str, Any]) -> bool:
    return actor.get("role") in {"host", "organizer"}


async def _snapshot_projection(
    current_user: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    async with await client.start_session() as session:
        async with session.start_transaction(read_concern=ReadConcern("snapshot")):
            actor, community = await _canonical_actor(current_user, session=session)
            lifecycle = community_lifecycle_state(community)
            organizer = _organizer_role(actor)
            if lifecycle == PROVISIONAL:
                if not organizer:
                    raise _not_available()
                projection = build_today_projection(
                    viewer_role=actor["role"],
                    lifecycle_state="provisional",
                    candidates=[
                        _static_candidate(
                            "activate_family_space", "provisional", "family_activation"
                        )
                    ],
                    recent_changes=[],
                )
                return projection, {}
            if lifecycle != ACTIVE:
                raise _not_available()

            event_query: dict[str, Any] = {
                "community_id": actor["community_id"],
                "event_template": {"$in": ["reunion", "holiday_meal"]},
                "hidden_from_user_ids": {"$ne": actor["id"]},
            }
            if not organizer:
                event_query["publication_state"] = {"$ne": "organizer_draft"}
            events = await events_collection.find(
                event_query, {"_id": 0}, session=session
            ).to_list(500)
            event_ids = [item["id"] for item in events if item.get("id")]
            members = await users_collection.find(
                {
                    "community_id": actor["community_id"],
                    "role": {"$in": sorted(_ACTIVE_ROLES)},
                    "account_status": {"$nin": sorted(_INACTIVE_STATES)},
                    "membership_status": {"$nin": sorted(_INACTIVE_STATES)},
                },
                {"_id": 0, "id": 1, "email": 1, "email_normalized": 1, "role": 1},
                session=session,
            ).to_list(2000)
            memories = await memories_collection.find(
                {
                    "community_id": actor["community_id"],
                    "event_id": {"$in": event_ids},
                    "created_by": actor["id"],
                },
                {"_id": 0},
                session=session,
            ).to_list(1000)
            recaps = await reunion_recaps_collection.find(
                {"community_id": actor["community_id"], "event_id": {"$in": event_ids}},
                {"_id": 0, "event_id": 1, "state": 1, "created_at": 1, "updated_at": 1},
                session=session,
            ).to_list(500)
            proposals = await gathering_proposals_collection.find(
                {
                    "community_id": actor["community_id"],
                    "state": {"$in": ["submitted", "published"]},
                },
                {"_id": 0, "id": 1, "state": 1, "created_at": 1},
                session=session,
            ).to_list(500)
            responses = await gathering_proposal_responses_collection.find(
                {
                    "community_id": actor["community_id"],
                    "user_id": actor["id"],
                    "proposal_id": {
                        "$in": [item["id"] for item in proposals if item.get("id")]
                    },
                },
                {"_id": 0, "proposal_id": 1, "response": 1},
                session=session,
            ).to_list(500)
            conversions = await gathering_proposal_conversions_collection.find(
                {
                    "community_id": actor["community_id"],
                    "created_event_id": {"$in": event_ids},
                },
                {"_id": 0, "created_event_id": 1, "created_at": 1},
                session=session,
            ).to_list(500)
            access_requests = await family_access_requests_collection.find(
                {
                    "community_id": actor["community_id"],
                    "$or": [
                        {"status": "pending"},
                        {"applicant_user_id": actor["id"]},
                    ],
                },
                {
                    "_id": 0,
                    "id": 1,
                    "event_id": 1,
                    "applicant_user_id": 1,
                    "status": 1,
                    "applicant_confirmed_at": 1,
                    "created_at": 1,
                },
                session=session,
            ).to_list(500)
            travel = await travel_plans_collection.find(
                {"community_id": actor["community_id"], "event_id": {"$in": event_ids}},
                {"_id": 0, "event_id": 1},
                session=session,
            ).to_list(1000)
            budgets = await budget_plans_collection.find(
                {"community_id": actor["community_id"], "event_id": {"$in": event_ids}},
                {"_id": 0, "event_id": 1, "target_amount": 1, "current_amount": 1},
                session=session,
            ).to_list(1000)
            planning_invites = await invites_collection.find(
                {
                    "community_id": actor["community_id"],
                    "planning_event_id": {"$in": event_ids},
                    "role": "organizer",
                    "status": "pending",
                },
                {"_id": 0, "planning_event_id": 1},
                session=session,
            ).to_list(1000)
            notification_query = await notification_query_for_user(
                actor, session=session
            )
            notifications = (
                await notification_events_collection.find(
                    notification_query,
                    {
                        "_id": 0,
                        "event_type": 1,
                        "related_id": 1,
                        "read_by_user_ids": 1,
                        "created_at": 1,
                    },
                    session=session,
                )
                .sort("created_at", -1)
                .to_list(12)
            )

    candidates: list[dict[str, Any]] = []
    action_paths: dict[str, str] = {}

    def add_dynamic(
        code: str,
        state_value: str,
        destination: str,
        event: dict[str, Any],
        path: str,
    ) -> None:
        candidate, resolved = _dynamic_candidate(
            actor=actor,
            code=code,
            state=state_value,
            destination_category=destination,
            event=event,
            path=path,
        )
        candidates.append(candidate)
        action_paths[resolved[0]] = resolved[1]

    events_by_id = {item["id"]: item for item in events if item.get("id")}
    recap_by_event = {item.get("event_id"): item for item in recaps}
    converted_event_ids = {item.get("created_event_id") for item in conversions}
    travel_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in travel:
        travel_by_event[str(row.get("event_id") or "")].append(row)
    budget_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in budgets:
        budget_by_event[str(row.get("event_id") or "")].append(row)
    pending_planning_by_event: dict[str, int] = defaultdict(int)
    for row in planning_invites:
        pending_planning_by_event[str(row.get("planning_event_id") or "")] += 1
    member_ids_by_email = {
        str(item.get("email_normalized") or item.get("email") or "")
        .strip()
        .lower(): item["id"]
        for item in members
        if item.get("id")
        and str(item.get("email_normalized") or item.get("email") or "").strip()
    }
    organizer_ids = {
        item["id"]
        for item in members
        if item.get("role") in {"host", "organizer"} and item.get("id")
    }
    milestones: list[str] = []

    if organizer:
        holiday_events = [item for item in events if item.get("event_template") == "holiday_meal"]
        for event in holiday_events:
            if event.get("publication_state") == "organizer_draft":
                add_dynamic("finish_holiday_meal_setup", "draft", "gatherings", event, f"/gatherings/{event['id']}")
                continue
            if not event.get("event_invites"):
                add_dynamic("prepare_holiday_invitation", "ready", "gatherings", event, f"/gatherings/{event['id']}")
            if event.get("event_invites") and len(event.get("rsvp_records") or []) < len(event.get("event_invites") or []):
                add_dynamic("review_holiday_response_gaps", "missing", "gatherings", event, f"/gatherings/{event['id']}")
            if any(not item.get("assigned_to_id") and not item.get("assigned_to") for item in event.get("potluck_items") or []) or any(len(item.get("assigned_members") or []) < int(item.get("needed_count") or 1) for item in event.get("volunteer_slots") or []):
                add_dynamic("fill_holiday_contribution_gaps", "open", "gatherings", event, f"/gatherings/{event['id']}")
            add_dynamic("preserve_holiday_recipe", "available", "legacy_threads", event, "/legacy-threads")
            if reunion_completion(event).get("state") == "ready":
                add_dynamic("review_holiday_recap", "ready", "reunion_recap", event, f"/reunion/recap/{event['id']}")
        regular_events = [
            item
            for item in events
            if item.get("event_template") == "reunion"
            and item.get("publication_state") != "organizer_draft"
            and reunion_completion(item).get("state") != "ready"
        ]
        command_states: list[
            tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = []
        for event in regular_events:
            responses_summary = canonical_response_summary(
                event, member_ids_by_email=member_ids_by_email
            )
            deadlines = deadline_summary(event)
            assigned_ids = set(event.get("planning_team_member_ids") or [])
            progress = planning_progress(
                event,
                travel_plans=travel_by_event[event["id"]],
                budgets=budget_by_event[event["id"]],
                planning_team_assigned=len(assigned_ids & organizer_ids),
                planning_team_pending=pending_planning_by_event[event["id"]],
            )
            command_action = next_best_action(
                event,
                responses=responses_summary,
                deadlines=deadlines,
                progress=progress,
            )
            command_states.append((event, responses_summary, deadlines, command_action))
            if responses_summary["responded"] >= 1:
                milestones.append("first_rsvp_received")

        converted_drafts = [
            item
            for item in events
            if item.get("publication_state") == "organizer_draft"
            and item.get("id") in converted_event_ids
        ]
        other_drafts = [
            item
            for item in events
            if item.get("event_template") == "reunion"
            and item.get("publication_state") == "organizer_draft"
            and item.get("id") not in converted_event_ids
        ]
        for event in other_drafts:
            add_dynamic(
                "finish_reunion_draft",
                "draft",
                "reunion_activation",
                event,
                f"/reunion/activate/{event['id']}",
            )
        for event, responses_summary, _deadlines, command_action in command_states:
            if command_action["code"] in {
                "complete_reunion_details",
                "confirm_itinerary",
            }:
                add_dynamic(
                    "finish_reunion_draft",
                    "draft",
                    "reunion_activation",
                    event,
                    f"/reunion/activate/{event['id']}",
                )
            elif command_action["code"] in {
                "create_first_invitation",
                "share_invitations",
            }:
                add_dynamic(
                    "prepare_first_invitation",
                    "ready",
                    "reunion_activation",
                    event,
                    f"/reunion/activate/{event['id']}",
                )
            if responses_summary["missing"]:
                add_dynamic(
                    "resolve_rsvp_attention",
                    "approaching" if _deadlines["approaching"] else "missing",
                    "organizer_command_center",
                    event,
                    f"/reunion/command/{event['id']}",
                )
            if command_action["code"] != "review_reunion_plan":
                add_dynamic(
                    "complete_command_task",
                    "open",
                    "organizer_command_center",
                    event,
                    f"/reunion/command/{event['id']}",
                )
            add_dynamic(
                "open_command_center",
                "available",
                "organizer_command_center",
                event,
                f"/reunion/command/{event['id']}",
            )

        pending_requests = [
            item for item in access_requests if item.get("status") == "pending"
        ]
        for request in pending_requests:
            event = events_by_id.get(request.get("event_id"))
            if event and event.get("publication_state") != "organizer_draft":
                add_dynamic(
                    "review_family_access_requests",
                    "pending",
                    "organizer_command_center",
                    event,
                    f"/reunion/command/{event['id']}#family-access",
                )
            else:
                candidates.append(
                    _static_candidate(
                        "review_family_access_requests",
                        "pending",
                        "gatherings",
                        str(request.get("created_at") or ""),
                    )
                )

        completed_events = [
            item
            for item in events
            if item.get("publication_state") != "organizer_draft"
            and reunion_completion(item).get("state") == "ready"
        ]
        for event in completed_events:
            state_value = recap_state(event, recap_by_event.get(event.get("id")))
            if state_value in {"ready", "unpublished"}:
                add_dynamic(
                    "review_recap",
                    "ready",
                    "reunion_recap",
                    event,
                    f"/reunion/recap/{event['id']}",
                )
        for proposal in proposals:
            if proposal.get("state") == "submitted":
                candidates.append(
                    _static_candidate(
                        "review_gathering_proposal",
                        "pending",
                        "gathering_proposals",
                        "\n".join(
                            (
                                str(proposal.get("created_at") or ""),
                                str(proposal.get("id") or ""),
                            )
                        ),
                    )
                )
        for event in converted_drafts:
            add_dynamic(
                "continue_converted_draft",
                "draft",
                "organizer_command_center",
                event,
                f"/reunion/command/{event['id']}",
            )
        if not regular_events:
            candidates.append(
                _static_candidate("open_command_center", "available", "gatherings")
            )
        viewer_role = actor["role"]
    else:
        own_access = max(
            [
                item
                for item in access_requests
                if item.get("applicant_user_id") == actor["id"]
            ],
            key=lambda item: str(item.get("created_at") or ""),
            default=None,
        )
        viewer_role = (
            "new_member" if (own_access or {}).get("status") == "approved" else "member"
        )
        if own_access and own_access.get("status") == "approved":
            milestones.append("family_access_approved")
            if not own_access.get("applicant_confirmed_at"):
                candidates.append(
                    _static_candidate(
                        "confirm_family_access", "approved", "family_access"
                    )
                )
        elif own_access and own_access.get("status") in {
            "pending",
            "declined",
            "expired",
            "conflict",
        }:
            candidates.append(
                _static_candidate(
                    "check_family_access_status", "waiting", "family_access"
                )
            )

        holiday_events = [item for item in events if item.get("event_template") == "holiday_meal" and item.get("publication_state") != "organizer_draft"]
        for event in holiday_events:
            aliases = member_invite_aliases(event, actor)
            own_rsvp = any(row.get("user_id") in aliases for row in event.get("rsvp_records") or [])
            if not own_rsvp:
                add_dynamic("complete_holiday_rsvp", "missing", "gatherings", event, f"/gatherings/{event['id']}")
            add_dynamic("review_holiday_schedule", "available", "gatherings", event, f"/gatherings/{event['id']}")
            if any(not item.get("assigned_to_id") and not item.get("assigned_to") for item in event.get("potluck_items") or []) or any(len(item.get("assigned_members") or []) < int(item.get("needed_count") or 1) for item in event.get("volunteer_slots") or []):
                add_dynamic("claim_holiday_contribution", "open", "gatherings", event, f"/gatherings/{event['id']}")
            add_dynamic("add_holiday_recipe", "available", "legacy_threads", event, "/legacy-threads")
            if recap_state(event, recap_by_event.get(event.get("id"))) == "published":
                add_dynamic("view_holiday_recap", "published", "reunion_recap", event, f"/reunion/recap/{event['id']}")
        active_events = [
            item
            for item in events
            if item.get("event_template") == "reunion"
            and item.get("publication_state") != "organizer_draft"
            and reunion_completion(item).get("state") == "not_ready"
        ]
        own_memories_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for memory in memories:
            own_memories_by_event[str(memory.get("event_id") or "")].append(memory)
        for event in active_events:
            event_memories = own_memories_by_event[event["id"]]
            hub = build_attendee_hub(
                event,
                actor,
                has_memory=any(
                    item.get("capsule_status") == "published" for item in event_memories
                ),
            )
            if hub["rsvp"]["my_status"] not in {"going", "some", "maybe", "not-going"}:
                add_dynamic(
                    "complete_reunion_rsvp",
                    "missing",
                    "attendee_hub",
                    event,
                    f"/reunion/hub/{event['id']}",
                )
            if any(
                item.get("attendance_requested")
                and item.get("response_open")
                and item.get("my_response") == "no-response"
                for item in hub["itinerary"]["activities"]
            ):
                add_dynamic(
                    "complete_activity_responses",
                    "missing",
                    "attendee_hub",
                    event,
                    f"/reunion/hub/{event['id']}",
                )
            if hub["itinerary"]["activities"] and not hub["itinerary"]["reviewed"]:
                add_dynamic(
                    "review_updated_itinerary",
                    "ready",
                    "attendee_hub",
                    event,
                    f"/reunion/hub/{event['id']}",
                )
            contributions = hub["contributions"]
            if (
                contributions["own_commitments"]["count"]
                or any(not item["claimed"] for item in contributions["potluck"])
                or any(item["openings"] for item in contributions["volunteer"])
            ):
                add_dynamic(
                    "manage_contribution",
                    "available",
                    "attendee_hub",
                    event,
                    f"/reunion/hub/{event['id']}",
                )

        response_proposal_ids = {item.get("proposal_id") for item in responses}
        for proposal in proposals:
            if (
                proposal.get("state") == "published"
                and proposal.get("id") not in response_proposal_ids
            ):
                candidates.append(
                    _static_candidate(
                        "respond_to_gathering_pulse",
                        "open",
                        "gathering_proposals",
                        "\n".join(
                            (
                                str(proposal.get("created_at") or ""),
                                str(proposal.get("id") or ""),
                            )
                        ),
                    )
                )
        for memory in memories:
            event = events_by_id.get(memory.get("event_id"))
            if event and memory.get("capsule_status") == "draft":
                add_dynamic(
                    "continue_memory_contribution",
                    "draft",
                    "memory_capsule",
                    event,
                    f"/reunion/memories/{event['id']}",
                )
        unread_recap_event_ids = {
            item.get("related_id")
            for item in notifications
            if item.get("event_type") == "reunion-recap-published"
            and actor["id"] not in (item.get("read_by_user_ids") or [])
        }
        for event_id in unread_recap_event_ids:
            event = events_by_id.get(event_id)
            if (
                event
                and recap_state(event, recap_by_event.get(event_id)) == "published"
            ):
                add_dynamic(
                    "view_published_recap",
                    "published",
                    "reunion_recap",
                    event,
                    f"/reunion/recap/{event['id']}",
                )
        candidates.append(
            _static_candidate("open_family_home", "available", "family_home")
        )

    projection = build_today_projection(
        viewer_role=viewer_role,
        lifecycle_state="active",
        candidates=candidates,
        recent_changes=safe_recent_changes(notifications, actor["id"]),
        milestone_codes=milestones,
    )
    exposed_references = {
        action.get("action_reference")
        for action in [projection["primary_action"], *projection["secondary_actions"]]
        if action.get("action_reference")
    }
    return projection, {
        reference: path
        for reference, path in action_paths.items()
        if reference in exposed_references
    }


@router.get("/today")
async def family_today(current_user: dict[str, Any] = Depends(get_current_user)):
    projection, _paths = await _snapshot_projection(current_user)
    return projection


@router.get("/today/actions/{action_reference}")
async def resolve_today_action(
    action_reference: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if len(action_reference) != 32 or any(
        char not in "0123456789abcdef" for char in action_reference
    ):
        raise _not_available()
    _projection, paths = await _snapshot_projection(current_user)
    path = paths.get(action_reference)
    if not path:
        raise _not_available()
    return {"destination": path}


def static_today_destination(category: str) -> str | None:
    """Exposed for focused route-inventory tests; never accepts user text."""
    return _STATIC_PATHS.get(category)
