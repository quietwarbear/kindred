# Release 4 route and data inventory

## New authenticated attendee routes

| Method and route | Authorization | Reads | Writes | Idempotency and concurrency | External calls |
| --- | --- | --- | --- | --- | --- |
| `GET /api/events/{event_id}/attendee-hub` | Existing session plus canonical community/hidden-event gate; reunion only | Event and current member's prompt-memory existence | None | Read-only | None |
| `POST /api/events/{event_id}/attendee-hub/itinerary-reviewed` | Same | Event | Adds the current member ID to `attendee_hub_reviewed_by` | Event compare-and-swap; duplicate review is a no-op | None |
| `POST /api/events/{event_id}/attendee-hub/memory` | Same | Event and current member's prompt memory | One existing-schema community memory | Deterministic operation hash and MongoDB `_id`; concurrent retries converge on one record | None; AI tagging is bypassed |

## Existing contribution routes strengthened

| Method and route | Outcome | Race behavior |
| --- | --- | --- |
| `POST /api/events/{event_id}/potluck-claim` | Claim an open item for the current member | Compare-and-swap; exactly one winner for a final item; the winner's retry is idempotent |
| `POST /api/events/{event_id}/potluck-release` | Release only the current member's item | Compare-and-swap; does not reveal or change another member's claim |
| `POST /api/events/{event_id}/volunteer-signup` | Claim an open volunteer slot | Compare-and-swap; final capacity cannot be overfilled; the member's retry is idempotent |
| `POST /api/events/{event_id}/volunteer-release` | Release only the current member's slot | Compare-and-swap; does not reveal or change another member's commitment |

All four mutations preserve the canonical community and hidden-event predicates
inside the atomic write. Stable `404`/`409` responses do not disclose whether a
cross-community or hidden event exists.

## Frontend routes and network boundary

- `/reunion/hub/:eventId` is a focused attendee surface without the organizer
  application shell.
- Member gathering lists route reunions to the attendee hub and do not preload
  member rosters, travel, budget, planning-team, or invitation endpoints.
- A member who reaches the older reunion detail route is redirected after the
  minimal event lookup.
- Public RSVP continues to use the header-only credential transport. Its
  confirmation shows only the invitee's response, published itinerary,
  aggregate attendance, and a neutral explanation that an account does not
  grant community access.

No Release 4 route accepts an invitation credential, email address, or member
identifier in its path or query string.
