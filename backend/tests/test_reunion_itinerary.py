from pathlib import Path

from itinerary import (
    activity_response_summary,
    activity_summaries,
    derive_overall_suggestion,
    normalize_activity,
    overlap_pairs,
    parse_local_datetime,
    published_activities,
    replace_respondent_activity_responses,
    valid_timezone,
    validate_activity,
)

ROOT = Path(__file__).resolve().parents[1]


def activity(activity_id: str, start: str, end: str, **overrides):
    return normalize_activity(
        {
            "title": overrides.pop("title", activity_id),
            "start_at": start,
            "end_at": end,
            "timezone": "America/New_York",
            "visibility": "published",
            **overrides,
        },
        activity_id=activity_id,
    )


def test_existing_single_day_event_payload_requires_no_migration_fields():
    models = (ROOT / "models.py").read_text()
    assert 'end_at: str = ""' in models
    assert 'timezone: str = "UTC"' in models
    assert "agenda: list[dict] = Field(default_factory=list)" in models


def test_legacy_agenda_item_remains_valid_and_unstructured():
    item = normalize_activity(
        {"time_label": "2:00 PM", "title": "Opening circle", "notes": "Welcome"},
        activity_id="legacy",
    )
    assert item["time_label"] == "2:00 PM"
    assert item["title"] == "Opening circle"
    assert item["start_at"] == ""
    assert validate_activity(item, "UTC") == [
        "Activity start date and time are required.",
        "Activity end date and time are required.",
    ]


def test_multiday_midnight_and_overlap_behavior():
    welcome = activity("welcome", "2027-07-18T20:00:00", "2027-07-19T00:30:00")
    dance = activity("dance", "2027-07-18T22:00:00", "2027-07-19T01:00:00")
    breakfast = activity("breakfast", "2027-07-19T08:00:00", "2027-07-19T09:00:00")
    assert validate_activity(welcome, "America/New_York") == []
    assert overlap_pairs([welcome, dance, breakfast], "America/New_York") == [
        ("welcome", "dance")
    ]


def test_multiple_venues_capacity_and_location_tba_are_activity_scoped():
    dinner = activity(
        "dinner",
        "2027-07-18T18:00:00",
        "2027-07-18T21:00:00",
        venue_name="Heritage Hall",
        venue_address="100 Reunion Way",
        venue_detail="Ballroom",
        capacity=40,
    )
    outing = activity(
        "outing",
        "2027-07-18T13:00:00",
        "2027-07-18T16:00:00",
        venue_name="Lakeside Park",
        venue_address="5 Lake Drive",
        location_tba=False,
    )
    draft = activity(
        "draft",
        "2027-07-19T10:00:00",
        "2027-07-19T11:00:00",
        location_tba=True,
    )
    assert dinner["venue_name"] != outing["venue_name"]
    assert dinner["capacity"] == 40
    assert draft["location_tba"] is True


def test_dst_boundary_uses_primary_timezone():
    before = parse_local_datetime("2027-03-14T01:30:00", "America/New_York")
    after = parse_local_datetime("2027-03-14T03:30:00", "America/New_York")
    assert before is not None
    assert after is not None
    assert after > before
    assert valid_timezone("America/New_York")
    assert not valid_timezone("Mars/Olympus")


def test_only_published_structured_activities_reach_public_itinerary():
    visible = activity("visible", "2027-07-18T10:00:00", "2027-07-18T11:00:00")
    draft = {**activity("draft", "2027-07-18T12:00:00", "2027-07-18T13:00:00"), "visibility": "draft"}
    legacy = {"id": "legacy", "title": "Legacy", "time_label": "Later"}
    assert [item["id"] for item in published_activities({"agenda": [draft, legacy, visible]})] == [
        "visible"
    ]


def test_activity_counts_party_size_capacity_and_no_response():
    responses = [
        {"activity_id": "dinner", "status": "coming", "party_size": 3},
        {"activity_id": "dinner", "status": "coming", "party_size": 1},
        {"activity_id": "dinner", "status": "maybe", "party_size": 2},
        {"activity_id": "other", "status": "coming", "party_size": 5},
    ]
    summary = activity_response_summary("dinner", responses, invite_count=6)
    assert summary == {
        "coming": 2,
        "maybe": 1,
        "not_coming": 0,
        "no_response": 3,
        "party_size": 4,
    }
    event = {
        "agenda": [activity("dinner", "2027-07-18T18:00:00", "2027-07-18T21:00:00")],
        "activity_rsvps": responses,
        "event_invites": [{}, {}, {}, {}, {}, {}],
    }
    assert activity_summaries(event)["dinner"]["party_size"] == 4


def test_activity_choices_suggest_but_do_not_overwrite_explicit_overall_response():
    assert derive_overall_suggestion("", {"a": "coming", "b": "not-coming"}) == "some"
    assert derive_overall_suggestion("", {"a": "not-coming", "b": "not-coming"}) == "not-going"
    assert derive_overall_suggestion("going", {"a": "not-coming"}) == "going"
    assert derive_overall_suggestion("maybe", {"a": "coming"}) == "maybe"


def test_mixed_activity_responses_can_be_edited_without_touching_other_people():
    existing = [
        {"activity_id": "dinner", "respondent_id": "invite:a", "status": "maybe"},
        {"activity_id": "outing", "respondent_id": "invite:a", "status": "coming"},
        {"activity_id": "dinner", "respondent_id": "invite:b", "status": "coming"},
    ]
    updated = replace_respondent_activity_responses(
        existing,
        "invite:a",
        [{"activity_id": "dinner", "respondent_id": "invite:a", "status": "coming"}],
    )
    assert next(
        item for item in updated
        if item["activity_id"] == "dinner" and item["respondent_id"] == "invite:a"
    )["status"] == "coming"
    assert next(
        item for item in updated
        if item["activity_id"] == "outing" and item["respondent_id"] == "invite:a"
    )["status"] == "coming"
    assert next(
        item for item in updated
        if item["activity_id"] == "dinner" and item["respondent_id"] == "invite:b"
    )["status"] == "coming"


def test_routes_preserve_history_and_keep_public_rosters_aggregate_only():
    events_route = (ROOT / "routes" / "events.py").read_text()
    public_route = (ROOT / "routes" / "public.py").read_text()
    assert '@router.put("/events/{event_id}/agenda/{activity_id}"' in events_route
    assert '"revision_history": list(source.get("revision_history") or [])' in (
        ROOT / "itinerary.py"
    ).read_text()
    assert '"visibility"] = "archived"' in events_route
    assert "confirm_responses: bool = Query(False)" in events_route
    assert '@router.get("/events/{event_id}/operations")' in events_route
    assert '"activity_rosters": rosters' in events_route
    assert '"attendance": summaries.get(activity_id, {})' in public_route
    assert '"activity_rosters"' not in public_route
    assert '"activity_rsvps": activity_responses' in public_route


def test_billing_and_contribution_routes_are_not_part_of_itinerary_implementation():
    events_route = (ROOT / "routes" / "events.py").read_text()
    public_route = (ROOT / "routes" / "public.py").read_text()
    assert "subscriptions/checkout" not in events_route
    assert "subscriptions/checkout" not in public_route
    assert "stripe" not in events_route.lower()
    assert "revenuecat" not in events_route.lower()
