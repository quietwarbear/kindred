# Reunion-first activation

Date: 2026-07-25
Branch base: `0f61fff` (`origin/main`)
Status: locally verified draft PR candidate; not merged or deployed

## Verified starting funnel

Before this branch, the homepage led an anonymous organizer toward pricing rather than an immediate task. Password registration required full name, email, password, community type, permanent community name, location, motto, and a description. Social sign-in created a provisional community but then required a five-step onboarding sequence covering profile enrichment, community naming, subyards, a gathering, and community invitations. Successful password login or registration redirected to subscription management.

Gathering creation itself was already capable: organizers could create a reunion template with an automatic checklist, agenda, volunteer roles, potluck items, travel coordination, and private event invites. Each event invite received an unguessable UUID RSVP link. Invitees could view minimal event details and RSVP on the web without an account or app. Signed-in members could claim potluck items and volunteer roles, while memories could be attached to the gathering.

## Architectural and privacy constraints

- Events are always owned by an authenticated community and organizer. Creating a server-backed anonymous event would weaken current ownership and data-integrity invariants.
- Public RSVP tokens are bearer capabilities scoped to one invite. They intentionally expose no member list, other invitations, community content, or account access.
- A true pre-account draft is therefore browser-local only. It contains the
  reunion name, date range, primary timezone, organizer name, optional host
  city, and multiday flag, and is never shareable. Attendee data, invitation
  tokens, private venue details, and activity notes are excluded.
- Authentication remains required before server persistence and invite-token creation.
- Password registration creates a clearly provisional internal planning-space name derived from the gathering. Permanent family-space naming, taxonomy, profiles, subyards, and module selection remain deferred.
- Existing Google and Apple accounts can persist the same draft. New social users may reach the reunion activation screen before completing the broader community onboarding sequence.
- Public RSVP remains web-first. A guest is invited to sign in only for enduring features; a new guest still needs a separate private community invitation before receiving community access.

## Implemented flow

```text
Homepage
  → Start planning
  → Browser-local reunion draft
  → Checklist / RSVP / potluck / volunteer / memory preview
  → Exact invitation preview
  → Lightweight account boundary
  → Authenticated reunion event
  → Optional multiday itinerary with structured activities and venues
  → Organizer creates private invite records and copies RSVP links
  → Guest opens gathering-centered web invitation
  → Guest submits one overall + activity-level RSVP without an account or app
  → Optional sign-in for chat, photos, stories, and ongoing access
```

No payment is required to create, preview, persist, or coordinate the initial gathering. The production web-subscription suspension and HTTP 410 checkout control are unchanged.

A reunion may now span multiple days while remaining one gathering. The
existing agenda is extended into a structured itinerary with individual
activities, venues, and activity attendance. See
`docs/REUNION_ITINERARY_ARCHITECTURE.md`.

## Deliberate measurement

The application emits:

- `reunion_start_clicked`
- `reunion_draft_created`
- `reunion_preview_viewed`
- `invite_created`
- `invite_link_copied`
- `invite_opened`
- `rsvp_completed`
- `guest_account_started`
- `community_activated`
- `memory_prompt_completed`
- `reunion_multiday_enabled`
- `itinerary_activity_created`
- `itinerary_activity_published`
- `activity_rsvp_updated`
- `itinerary_viewed`
- `activity_roster_viewed`

Properties are restricted to a small allowlist of source/status/count/elapsed-day values. Names, emails, invitation tokens, provider identifiers, community IDs, and family content are rejected. Autocaptured text and element attributes are masked, and sensitive reunion/auth/RSVP surfaces opt out of autocapture.

`invite_created` means only that an invitation record exists.
`invite_link_copied` records sharing intent; copying a link does not prove that
the invitation was sent or received. Activation is evaluated when the host
views the reunion activation page within seven days and at least three
invitations have stronger evidence: an invite open, an RSVP response, or
independently verified provider delivery. At least two responses must be
`going` or `some`, and at least one non-host RSVP, potluck, or volunteer action
must exist. The event is emitted once per browser session for that gathering.
The current implementation can prove RSVP responses; persisted open and
provider-delivery markers are accepted only when those independently verified
fields exist.

## Verification artifacts

Expected local-only screenshots:

- `docs/screenshots/reunion-home-desktop.png`
- `docs/screenshots/reunion-draft-desktop.png`
- `docs/screenshots/reunion-home-mobile.png`
- `docs/screenshots/reunion-draft-mobile.png`
- `docs/screenshots/reunion-itinerary-desktop.png`
- `docs/screenshots/reunion-itinerary-mobile.png`
- `docs/screenshots/reunion-public-rsvp-desktop.png`
- `docs/screenshots/reunion-public-rsvp-mobile.png`

Do not capture real invitation tokens, email addresses, family content, or authenticated customer data in these artifacts.

## Remaining decisions

1. Decide whether public RSVP guests should be able to request a community invitation from the organizer without exposing the organizer’s contact information.
2. Decide when the provisional planning-space name should be replaced and whether the prompt should follow the first accepted RSVP or another meaningful action.
3. Confirm whether the first memory prompt should invoke AI tagging immediately or defer provider processing until the organizer enters the full archive.
4. Validate the account boundary and persisted activation page against an isolated test backend before any deployment.
5. Verify that native clients safely ignore the additive `some` status and itinerary fields before merge.
