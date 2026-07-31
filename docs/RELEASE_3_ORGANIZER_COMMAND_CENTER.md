# Release 3: Organizer Command Center

## Product outcome

Release 3 gives an authorized reunion organizer one calm, reunion-specific place
to answer what needs attention next, how responses reconcile, which deadlines
are approaching, where planning is incomplete, and what guests can actually
see. It does not add the full application navigation or expose the wider module
inventory.

The primary action is deterministic. Command-center reports contain aggregate
counts, timestamps, categorical states, and stable action codes only. The
recipient-facing planning-team view is a separate organizer-only endpoint and
never includes invitation codes.

## Authorization model

Every Release 3 event endpoint uses both canonical gates:

1. `ensure_minimum_role(current_user, "organizer")`
2. `get_event_for_user(event_id, current_user)`

The event must also be a reunion. Anonymous callers receive `401`, ordinary
members receive `403`, and cross-community or hidden-event lookups remain
`404`. A platform-administration flag does not grant organizer access.

Planning-team assignment reuses existing `host` and `organizer` community
roles. Assigning an event planner never elevates an ordinary member. Inviting a
new planning helper explicitly creates an existing community invitation with
role `organizer`; concurrent active invitations are protected by unique sparse
keys, and retry keys are independently unique.

## Organizer-versus-guest field matrix

| Surface | May contain | Explicitly excluded |
| --- | --- | --- |
| Organizer command report | Response/deadline counts, categorical progress, optional real-budget state, safe reminder state, recent change kinds/timestamps, stable next-action code | Names, emails, event/community IDs, titles, messages, links, credentials, provider payloads |
| Organizer planning-team view | Assigned organizer IDs/names/roles and pending invitation IDs/emails needed for revocation | Invitation code, invitation link, delivery/provider data, ordinary members outside the assignable list |
| Authenticated family-member event view | Canonical event fields, the member's own RSVP/activity state, aggregate RSVP summary | Invitation ledger, named RSVP records, other respondents' activity records |
| No-account RSVP guest and organizer guest preview | Invitee's own name/status, minimal gathering details, published activities, privacy-safe attendance aggregates, the guest's own activity response | Response gaps, invitation ledger, organizer notes, planning roles/team, budget, travel plans, private activities, credentials |
| Public pages | Marketing, pricing, privacy, terms, and support content | Reunion/event data of any kind |

The guest preview calls the same `serialize_event_for_guest` function used by
the header-only `/api/public/rsvp` response.

## Deterministic next-action priority

Exactly one action is returned.

| Priority | Stable action code | Trigger |
| --- | --- | --- |
| 1 | `complete_reunion_details` | Required title, valid start/timezone, or location is missing |
| 2 | `confirm_itinerary` | The structured itinerary is absent or not fully published |
| 3 | `create_first_invitation` | No active canonical invitations exist |
| 4 | `share_invitations` | Active invitations exist without response/open/share/delivery evidence |
| 5 | `resolve_approaching_deadline` | A valid deadline is within 14 days and responses are missing |
| 6 | `follow_up_missing_responses` | Canonical responses are still missing |
| 7 | `fill_planning_roles` | Existing event roles are unassigned |
| 8 | `resolve_contribution_gaps` | Potluck or volunteer capacity remains unassigned |
| 9 | `review_travel_gaps` | Travel is unstarted and the event is within 30 days |
| 10 | `prepare_story_prompts` | The event is within 14 days |
| Fallback | `review_reunion_plan` | No higher-priority gap exists |

## Response-count reconciliation

- Only active invitation credentials count. Revoked, expired, rotated, and
  superseded records are excluded.
- A member invitation uses its canonical `member_id`. A legacy member
  invitation without that field reconciles through normalized, case-insensitive
  community email lookup.
- Reissued member invitations collapse to one member identity; the newest
  invitation and newest canonical RSVP record win.
- Guests retain invitation-specific identities, so unrelated guests with the
  same or differently cased email are never merged.
- RSVP records are counted only when they resolve to an active invitation
  identity.
- `total == going + some + maybe + not-going + pending`, and
  `missing == pending`.
- Payloads contain counts only, never invitation or respondent identifiers.

Deadlines are parsed in the activity timezone or reunion timezone. Malformed
values and nonexistent or ambiguous DST-local wall times are classified as
invalid and cannot become an approaching deadline.

## Reminder failure-state matrix

| Condition | Safe code/status | Mutation or provider call |
| --- | --- | --- |
| No missing responses | `no_missing_responses` | None |
| Feature disabled or required configuration absent | `delivery_unavailable` | None |
| Configuration present but no reviewed privacy-safe ordinary-reminder adapter | `privacy_safe_sender_unavailable` | None |
| Fake provider explicitly rejects | `provider_rejected` / rejected | None outside the test classifier; controlled retry may be considered |
| Fake provider times out, is ambiguous, or reports conflicting acceptance | `provider_acceptance_ambiguous` / ambiguous | No automatic retry |
| Fake provider accepts unambiguously | `accepted` | Classifier test only |

The release intentionally stops at fail-closed preflight. It does not reuse the
generic email helper, call a provider, rotate credentials, or mutate invitation
state. Stable operation idempotency keys are required before preflight and
planning-team mutations.

## Changed-file inventory

Backend:

- `backend/organizer_command_center.py`
- `backend/organizer_reminders.py`
- `backend/routes/organizer.py`
- `backend/event_privacy.py`
- `backend/routes/public.py`
- `backend/models.py`
- `backend/server.py`
- `backend/tests/test_organizer_command_center.py`
- `backend/tests/test_reunion_security_disposable_db.py`
- `backend/tests/test_reunion_itinerary.py`
- `backend/tests/test_reunion_activation_static.py`

Frontend and verification:

- `frontend/src/components/OrganizerCommandCenterPage.jsx`
- `frontend/src/components/ReunionActivationPage.jsx`
- `frontend/src/components/gatherings/GatheringInvites.jsx`
- `frontend/src/App.js`
- `frontend/src/lib/analytics.js`
- `frontend/src/lib/analytics.test.js`
- `frontend/scripts/verify-organizer-command-center.js`
- `frontend/scripts/verify-commercial-readiness.js`
- `docs/screenshots/release-3/organizer-command-center-desktop.png`
- `docs/screenshots/release-3/organizer-command-center-mobile.png`
- `docs/RELEASE_3_ORGANIZER_COMMAND_CENTER.md`

## Verification evidence

- Baseline: `origin/main` was exactly
  `34a3efc122519923edcb8440f0efb39d4d8a4afd`, containing PR #20 merge
  `0962195b304339bd3300c6cd0d083c052308daf4` and the Release 2 report/assets.
- Focused backend: 186 tests passed with two dependency deprecation warnings.
- Disposable MongoDB replica set:
  - reunion authorization, confidentiality, response integrity, organizer
    report, planning-team concurrency/idempotency/revocation, and reminder
    non-mutation campaign: 1 passed;
  - invitation-redelivery transactional campaign: 3 passed.
- Frontend: 5 suites and 28 tests passed.
- Production frontend build and prerender: compiled successfully; `/`,
  `/reunion/start`, `/pricing`, `/privacy`, `/terms`, and `/support` were
  prerendered.
- Release 3 built-browser campaign: desktop/mobile command center, organizer
  denial, guest preview, aggregate status, budget omission, safe-area layout,
  header authorization, credential-free URLs, and zero external requests
  passed with synthetic local responses.
- Existing offline built-browser campaign: RSVP fragment/header transport,
  legacy-link transition, third-party isolation, service-worker bypass and
  legacy-cache purge, reunion activation, pricing, and public legal/support
  routes passed at desktop/mobile widths.
- Android: web assets synced in a disposable copy and `assembleDebug` succeeded
  with Java 21.
- iOS: web assets and CocoaPods synced in a disposable copy; unsigned
  `iphoneos` Debug build succeeded with code signing disabled.
- OpenAPI: all eight new operations were present; no credential, token, or
  email path/parameter was introduced.
- Changed-source secret scan, built web/native sensitive-marker scans, logging
  scan, analytics allowlist tests, Python compilation, Black check, Flake8
  check (with Black-compatible `E501,W503` exclusions), JavaScript build
  compilation, and `git diff --check` passed.
- Subscription regression: every tested web paid-plan/cycle combination
  remained HTTP `410` with `subscription_checkout_migrating`.

All database and browser records were synthetic and disposable. No production
customer data, invitation record, provider, deployment, store console, or
customer communication was accessed or changed.

## Screenshots

The checked-in images are generated from the real production frontend build
against in-process synthetic responses:

- `docs/screenshots/release-3/organizer-command-center-desktop.png`
- `docs/screenshots/release-3/organizer-command-center-mobile.png`

The generator blocks every external request. The fixtures use reserved or
synthetic identifiers and contain no customer records or credentials.

## Known limitations and external gates

- Ordinary reminder delivery remains intentionally unavailable until a
  separately reviewed privacy-safe sender exists. Configuration alone does not
  open the gate.
- No production health probe or deployment was run because this is an unmerged
  draft release.
- No Apple App Store or Google Play metadata/build was published.
- The optional `agent-browser` CLI was not installed or exposed in this
  environment. The repository's Puppeteer-based built-browser campaign and
  direct visual inspection were used instead.
- Production delivery configuration, live provider behavior, and customer data
  were deliberately not used for verification.
