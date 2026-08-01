"""Focused pure-policy tests for the unified Family Today projection."""

from today import (
    MEMBER_PRIORITY,
    ORGANIZER_PRIORITY,
    build_today_projection,
    opaque_action_reference,
    safe_recent_changes,
)


def candidate(code, position=0):
    organizer = code in ORGANIZER_PRIORITY
    destinations = {
        "activate_family_space": "family_activation",
        "review_gathering_proposal": "gathering_proposals",
        "respond_to_gathering_pulse": "gathering_proposals",
        "confirm_family_access": "family_access",
        "check_family_access_status": "family_access",
        "open_family_home": "family_home",
    }
    return {
        "code": code,
        "state": "provisional" if code == "activate_family_space" else "available",
        "destination_category": destinations.get(
            code, "organizer_command_center" if organizer else "attendee_hub"
        ),
        "action_reference": f"{position + 1:032x}",
        "tie_breaker": f"{position:04d}",
    }


def projection(role, candidates):
    return build_today_projection(
        viewer_role=role,
        lifecycle_state="active",
        candidates=candidates,
        recent_changes=[],
    )


def test_every_organizer_priority_displaces_only_lower_actions():
    for index, expected in enumerate(ORGANIZER_PRIORITY):
        result = projection(
            "organizer",
            [
                candidate(code, position)
                for position, code in enumerate(ORGANIZER_PRIORITY[index:])
            ],
        )
        assert result["primary_action_code"] == expected
        assert result["primary_action"]["code"] == expected


def test_every_member_priority_displaces_only_lower_actions():
    for index, expected in enumerate(MEMBER_PRIORITY):
        result = projection(
            "member",
            [
                candidate(code, position)
                for position, code in enumerate(MEMBER_PRIORITY[index:])
            ],
        )
        assert result["primary_action_code"] == expected
        assert result["primary_action"]["code"] == expected


def test_host_uses_organizer_priority_and_ties_are_stable():
    later = candidate("complete_command_task", 2)
    earlier = candidate("complete_command_task", 1)
    result = projection("host", [later, earlier, candidate("open_command_center", 3)])
    assert result["primary_action"]["action_reference"] == earlier["action_reference"]


def test_projection_has_one_primary_and_at_most_three_unique_secondaries():
    candidates = [
        candidate(code, position) for position, code in enumerate(MEMBER_PRIORITY)
    ]
    candidates.append(candidate(MEMBER_PRIORITY[0], 99))
    result = projection("member", candidates)
    assert result["primary_action_code"] == MEMBER_PRIORITY[0]
    assert len(result["secondary_actions"]) == 3
    assert (
        len(
            {
                result["primary_action_code"],
                *(item["code"] for item in result["secondary_actions"]),
            }
        )
        == 4
    )


def test_provisional_navigation_is_bounded():
    result = build_today_projection(
        viewer_role="host",
        lifecycle_state="provisional",
        candidates=[candidate("activate_family_space")],
        recent_changes=[],
    )
    assert result["navigation_categories"] == [
        "today",
        "family_activation",
        "gatherings",
    ]


def test_opaque_reference_is_stable_and_subject_bound():
    first = opaque_action_reference(
        community_id="family-a",
        user_id="member-a",
        action_code="complete_reunion_rsvp",
        subject="event-a",
    )
    assert first == opaque_action_reference(
        community_id="family-a",
        user_id="member-a",
        action_code="complete_reunion_rsvp",
        subject="event-a",
    )
    assert first != opaque_action_reference(
        community_id="family-a",
        user_id="member-a",
        action_code="complete_reunion_rsvp",
        subject="event-b",
    )
    assert len(first) == 32 and set(first) <= set("0123456789abcdef")


def test_recent_changes_are_content_free_bounded_and_preserve_read_state():
    rows = [
        {
            "id": "private-id",
            "event_type": "reunion-recap-published",
            "title": "Private title",
            "description": "Private message",
            "related_id": "private-event",
            "recipient_user_ids": ["member-a", "member-b"],
            "read_by_user_ids": ["member-a"],
            "created_at": "2028-01-01T00:00:00Z",
        },
        {"event_type": "family-access-request", "read_by_user_ids": []},
        {"event_type": "gathering-proposal-published", "read_by_user_ids": []},
        {"event_type": "event-update", "read_by_user_ids": []},
        {"event_type": "announcement-create", "read_by_user_ids": []},
    ]
    result = safe_recent_changes(rows, "member-a")
    assert result == [
        {"category": "reunion_recap", "is_read": True},
        {"category": "organizer_review", "is_read": False},
        {"category": "gathering_pulse", "is_read": False},
        {"category": "gathering_update", "is_read": False},
    ]
    serialized = str(result)
    for forbidden in (
        "Private title",
        "Private message",
        "private-event",
        "member-a",
        "2028-01-01",
    ):
        assert forbidden not in serialized


def test_projection_allowlist_excludes_internal_candidate_data():
    value = candidate("complete_reunion_rsvp") | {
        "event_id": "private-event",
        "community_id": "private-community",
        "title": "Private title",
        "email": "private@example.invalid",
        "destination_path": "/reunion/hub/private-event",
        "response_roster": ["Private Person"],
    }
    result = projection("member", [value])
    serialized = str(result)
    for forbidden in (
        "private-event",
        "private-community",
        "Private title",
        "private@example.invalid",
        "Private Person",
        "destination_path",
        "response_roster",
    ):
        assert forbidden not in serialized
