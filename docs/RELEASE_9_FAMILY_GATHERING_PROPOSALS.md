# Release 9: private family gathering proposals

Last verified: 2026-07-31

## Outcome and architecture

Release 9 lets an authenticated member of an active family space submit a private gathering suggestion, lets an existing host or organizer publish an approved anonymous interest pulse, and lets an organizer explicitly convert one accepted proposal into one private reunion draft. The exact baseline is Release 8 merge `3483df74487a8eb7479471894d83f5c0d23fd03d`.

`gathering_proposals` stores lifecycle, private suggestion fields, proposer ownership, revisions, and bounded operation hashes. `gathering_proposal_responses` stores one response per proposal/member under a unique index. `gathering_proposal_conversions` has a unique proposal key and created-event key; it is the private crash-recovery linkage, while the created event contains no proposal identifier.

Every route rechecks the authenticated account against the current same-community user record and requires an explicitly active family space. Missing, provisional, legacy, suspended, removed, deleted, or cross-community state fails closed. Platform-administrator flags grant no proposal authority.

## Lifecycle and concurrency

The lifecycle is `submitted -> published -> converted|declined|expired`, with `submitted -> withdrawn|declined`. `conflict` is reserved for structurally unusable legacy state. Terminal states never transition back.

- Submission uses a payload-bound idempotency hash and unique index.
- Publish, decline, close, and withdrawal use expected revision, compare-and-set, and bounded payload-bound operation history.
- Interest writes run in a transaction that rechecks the active user and `published` state. The `(proposal_id, user_id)` unique index guarantees one canonical response.
- Conversion rechecks the proposal, converting organizer, selected organizer, active community, exact preview digest, timezone, and DST boundaries inside one transaction.
- The transaction inserts the unique conversion record and deterministic private event, then marks the proposal converted. Concurrent requests with different keys recover the same draft.

## Privacy projection and aggregate reconciliation

Members see published family pulses and their own unpublished/terminal submissions. They never see other unpublished proposals, proposer identity, organizer notes, moderation history, response identities, internal IDs, operation hashes, or conversion linkage.

Organizers may see the proposer display name only as an already-authorized current family member. Organizers receive anonymous totals, not a reusable named roster. Totals query current eligible same-community accounts and ignore deleted, removed, suspended, or cross-community response owners. `interested + maybe + not_available = total`; no respondent timestamp, label, or ordering is returned.

## Conversion allowlist and denylist

The organizer explicitly selects a new title, start, end, IANA timezone, general location, gathering format, capacity, and active host/organizer. These exact fields appear in a mutation-free digest preview.

The new event is a `publication_state="organizer_draft"` reunion with zero invitations, credentials, RSVP/activity responses, agenda rows, contributions, assignments, memories, planning assignments, notifications, provider/payment state, or hidden-user list. It contains no proposal ID, proposer identity, interest identity, old event/activity ID, private note, broad date suggestion, family-access record, or incident marker.

## Notifications and analytics

- Submission creates one generic organizer-only in-app notification.
- Publication creates one generic recipient-scoped notification for current eligible family members.
- Decline and conversion may create one generic proposer-only notification.
- Notifications contain no proposal reference, title, note, location/date text, response identity, event/community/account ID, or operation reference; Stage 9 `related_id` is empty.
- Withdrawal, decline, close, and conversion remove the publication notification.
- No email, SMS, push, Resend, or live provider is called.

Only `gathering_proposal_submitted`, `gathering_pulse_viewed`, `gathering_interest_recorded`, and `gathering_proposal_converted` are allowed. Only bounded viewer-role, proposal-state, response-category, and next-action values survive. Proposal routes suppress autocapture and replay.

## Deletion, retention, and export

Account deletion removes the member's response documents. An owned `submitted` or `published` proposal becomes `withdrawn`; title, date window, location, organizer note, proposer ID, and proposer name are removed, leaving only a categorical proposer tombstone for audit integrity. Conversion actor links are likewise tombstoned. An already-created draft remains intact and contains no proposer identity. Notification recipient/read arrays remove the deleted account. Sole-owner community deletion removes all three Stage 9 collections.

The existing timeline export does not include proposal records; therefore it excludes organizer-only notes, moderation reasons, response identities, and operation hashes. No provider deletion is claimed because the feature calls no provider.

## Known limitations

- Interest is limited to `interested`, `maybe`, and `not_available`.
- Decline reasons are categorical; there is no free-form moderation message.
- Closing uses terminal `expired` with internal category `closed_by_organizer`; there is no background expiry worker.
- There are no comments, reactions, rankings, named rosters, chat, media, AI, public links, or provider delivery.
- Organizers enter exact conversion boundaries; a broad member suggestion never silently becomes an event date.

## Finding-to-test matrix

| Risk | Verification |
|---|---|
| Unpublished or cross-family disclosure | Disposable Mongo authorization/visibility campaign and projection denylist tests |
| Named or mathematically inconsistent pulse results | Eligible-account reconciliation unit tests plus real-database own-response and aggregate assertions |
| Stale moderation overwrites | Publish/decline and withdraw/publish concurrency races with revision compare-and-set |
| Duplicate or contaminated reunion draft | Concurrent different-key conversion, unique indexes, deterministic event ID, exact preview digest, allowlist/denylist assertions |
| Notification audience or identifier leakage | Recipient-query checks; feed/history projection checks; unread/mark-read checks; terminal pulse cleanup |
| Deleted identity retention | Individual account tombstone campaign and sole-owner three-collection cascade campaign |
| Regression of invitation, RSVP, hidden-draft, or checkout protections | Existing reunion-security/redelivery campaigns, Releases 3–8 browser continuity, commercial-readiness browser campaign, and HTTP 410 tests |

## Verification evidence

All records and providers were synthetic/local. No production data, provider delivery, deployment, store publishing, or merge was performed.

| Campaign | Result |
|---|---|
| Focused Stage 9 helpers plus checkout kill switch | `20 passed` |
| Full relevant backend regression | `262 passed, 1 skipped` |
| Stage 9 disposable Mongo replica-set campaign | `1 passed` |
| Existing reunion-security, redelivery, guest-access, activation, and recap disposable campaigns | `7 passed` total |
| Frontend Jest suites | `33 passed` |
| Production build and public-page prerender | Compiled and prerendered successfully |
| Releases 3–9 and commercial-readiness built-browser campaigns | Passed at desktop/mobile widths with synthetic responses |
| Android debug build | `BUILD SUCCESSFUL` |
| Unsigned generic iOS device build | `BUILD SUCCEEDED` |
| OpenAPI inventory | `182` paths total; `10` Stage 9 paths and `11` Stage 9 methods |
| Python compilation, fatal lint, diff whitespace | Passed |
