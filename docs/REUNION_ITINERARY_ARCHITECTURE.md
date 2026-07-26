# Reunion itinerary and activity attendance

Status: PR #14 was merged externally. Its post-merge security and integrity
corrections are documented in `docs/REUNION_SECURITY_INCIDENT_CORRECTION.md`;
that corrective branch is not yet merged or deployed.

## Approved product decisions

- Public and invitee-facing “Who’s coming?” remains aggregate-only. Full
  attendee identities remain available only to organizers under the existing
  authorization boundary.
- Household attendance retains party-size counts only. Named household guests
  are deferred until consent, minor-safety, editing, and privacy behavior are
  designed explicitly.
- `invite_created` proves only that an invitation record exists, while
  `invite_link_copied` records sharing intent. A copied link is not treated as
  sent or as activation evidence. Activation requires an invite open, an RSVP,
  or independently verified provider delivery.
- `some` is an additive overall status meaning “attending some activities.” It
  does not replace or reinterpret legacy RSVP values. Native compatibility is a
  pre-merge gate.

## Current-model findings

- A reunion is already represented by one event/gathering.
- Events already own `start_at`, `end_at`, a top-level location, invitations,
  overall RSVP records, and an `agenda`.
- Legacy agenda rows contain only `id`, `time_label`, `title`, and `notes`.
- Existing public invitation tokens are UUID4 bearer capabilities scoped to one
  event invite. They can safely support a combined overall/activity response
  without creating another public credential.
- Existing RSVP records support a party-size count but not named household
  guests. The itinerary implementation retains party size and does not invent a
  public guest-name policy.
- Existing general event responses expose attendee names to authenticated
  community members. Activity rosters therefore use a separate organizer-only
  endpoint; general and public itinerary views receive aggregates only.

## Implemented hierarchy

```
Reunion event
  start_at / end_at / timezone / host city
  agenda[]
    structured activity
      start_at / end_at / timezone override
      venue / room / map / virtual link / location TBA
      capacity / RSVP deadline / attendance requested
      draft / published / archived visibility
  activity_rsvps[]
    respondent scoped to activity
  rsvp_records[]
    overall reunion response
```

Structured activities extend `agenda`; there is no parallel event system.

## API changes

- `POST /api/events/{event_id}/agenda` accepts legacy or structured activity
  fields.
- `PUT /api/events/{event_id}/agenda/{activity_id}` edits an activity and
  preserves responses.
- `POST /api/events/{event_id}/agenda/{activity_id}/duplicate` creates a private
  draft copy.
- `POST /api/events/{event_id}/agenda/{activity_id}/publish` validates and
  publishes a draft.
- `DELETE /api/events/{event_id}/agenda/{activity_id}` requires confirmation
  when responses exist. Confirmed removal archives instead of erasing.
- `POST /api/events/{event_id}/activity-rsvp` records an authenticated member’s
  activity response.
- `GET /api/events/{event_id}/operations` is organizer-only and returns
  authorized rosters, day/activity aggregates, capacity warnings, overlap data,
  unanswered invitations, missing venues, and recent changes.
- `GET /api/public/rsvp/{token}` returns published activities, aggregate counts,
  and only the held invite’s choices.
- `POST /api/public/rsvp/{token}` atomically updates the held invite’s overall
  response and all supplied activity choices.

No endpoint returns another invitation, email address, phone number, minor
detail, private note, or public activity roster.

## Compatibility and migration

No eager migration or production rewrite is required.

- Missing `end_at` keeps an event effectively single-day.
- Missing `timezone` defaults to `UTC`.
- Legacy agenda rows remain valid and continue rendering in existing gathering
  views.
- Activities without structured times are excluded from the published rolling
  itinerary until an organizer completes and publishes them.
- Existing overall statuses (`going`, `maybe`, `not-going`) remain valid.
  `some` is additive and means “attending some activities.”
- Older clients must safely ignore the additive `some` value and itinerary
  fields; native compatibility testing remains required before merge.
- Old public clients may omit `activity_responses`; the default is an empty map.
- Existing UUID invitation links remain the only no-account capability.
- `activity_rsvps` are stored separately, so activity time and venue edits do
  not discard attendance.
- Deleting an unanswered activity removes it. Deleting one with responses
  requires confirmation and archives it with its response history.
- Billing, contributions, add-ons, entitlements, and provider code are outside
  this change.

Rollback is code-only: revert the itinerary routes and clients. Existing events
continue working because all new fields are optional. Newly enriched agenda
objects retain their legacy `title`, `time_label`, and `notes`, so older clients
can still display them. Do not delete `activity_rsvps` during rollback; retaining
them preserves evidence for a later re-enable.

## Privacy model

- The browser-local draft stores only reunion name, date range, primary
  timezone, organizer name, host city, and the multiday flag.
- Private venue details are added only after authentication.
- Public itinerary responses are identified internally by the held invite but
  invitation IDs never enter analytics.
- Public and ordinary invitee views show aggregate activity attendance.
- Only hosts and organizers can retrieve named activity rosters.
- Organizer rosters deliberately omit contact details and private notes.

## Deliberate analytics

Added:

- `reunion_multiday_enabled`
- `itinerary_activity_created`
- `itinerary_activity_published`
- `activity_rsvp_updated`
- `itinerary_viewed`
- `activity_roster_viewed`

Allowed properties are limited to counts, day or position, venue-presence
booleans, response category, and host/invitee role. Titles, locations, names,
contacts, tokens, community IDs, and free-form text are rejected.
