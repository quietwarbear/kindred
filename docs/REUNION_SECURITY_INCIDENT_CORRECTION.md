# Reunion security and integrity correction

Status: corrective branch amended after the external merge of PR #14. The
corrective branch remains draft, unmerged, and undeployed. Production
containment was separately verified by restoring both services to the
pre-reunion commit.

## Production triage

- The PR #14 merge commit remains present on `main`, but is no longer the
  production target.
- Vercel deployment `dpl_3bkDnQrMurHXKmxFTqdoLhoJuTNS` and Railway deployment
  record `5606000894` were independently verified against pre-reunion commit
  `0f61fff0bc464d67905f04349eb3015e7937d827`.
- Vercel and Railway production were restored to matching builds from that
  commit. The public frontend no longer serves reunion bundle markers, while
  direct subscription checkout continues to return HTTP 410.
- The merged generic event schema includes invitation and named RSVP fields.
  Before this correction, ordinary authenticated community-member event
  responses were therefore capable of disclosing organizer-only invitation
  records and bearer invitation credentials.
- Sanitized runtime-log queries did not establish whether a reunion invitation
  route was accessed after deployment. The absence of matching rows is
  inconclusive because the available log source also returned no general
  traffic evidence for the same period.

No production record, invitation credential, or personal information was read
or changed during triage.

## Corrective architecture

Generic event responses now pass through role-aware serialization:

- Hosts and organizers retain the complete event document needed by explicitly
  authorized organizer surfaces.
- Ordinary members receive event details, aggregate RSVP counts, and only their
  own overall/activity response state.
- Invitation records, named RSVP records, bearer credentials, email addresses,
  notes, messages, and organizer roster fields are removed from ordinary-member
  responses.
- The timeline anniversary surface uses the same serializer, and hidden
  gatherings are excluded for the affected member.
- Hidden gatherings are also excluded from timeline exports, recurring
  reminders, member-profile history, digest previews, community health
  aggregates, memory associations, travel and budget records, community
  overview/courtyard projections, legacy previews, and subcommunity gathering
  counts.
- Notifications tied to hidden gatherings are excluded from member reads,
  unread counts, and mark-read writes. New hidden-event invitation and reminder
  notifications are organizer-scoped.
- Public invitation routes continue to return only the held invitation's
  minimal view and aggregate activity attendance.

RSVP writes use a revision-guarded compare-and-swap loop with bounded retry.
Concurrent public and authenticated updates can no longer replace a newer
whole-event RSVP snapshot. Authenticated member visibility is part of the
atomic write predicate, and member-linked public invitations recheck visibility
inside that same write boundary, so an organizer hiding a gathering during an
RSVP request prevents the write.

Member-linked invitations now carry `member_id`. Existing member invitations
without that field reconcile only when both the invitation source is `member`
and its normalized email exactly matches a member in the same community. Guest
invitations never inherit a member identity from email alone.

## Additional hardening

- New invitation links use `/rsvp#token`; the client sends the token only in an
  authorization header to the path-stable `/api/public/rsvp` endpoint.
- Existing `/rsvp/:token` links remain a controlled transition: the client
  immediately rewrites them to fragment form before subsequent API requests.
- The backend no longer registers path-token RSVP API routes; both reads and
  writes require the path-stable endpoint and an authorization header.
- Secure invitation routes suppress every product-analytics entry point,
  Google Tag Manager, Google Analytics, Google Identity, and referrer
  propagation before React starts, including fragment-form invitation URLs.
- Sensitive RSVP pages load no third-party fonts, images, scripts, or other
  external resources. The committed browser campaign enforces a first-party
  origin allowlist and repeats the complete isolation check for the legacy URL
  in a fresh page.
- Useful backend access logging remains enabled. Synthetic browser evidence
  confirms invitation API log lines contain `/api/public/rsvp`, not a token.
- The upgraded service worker treats every RSVP navigation as network-only,
  removes the old cache, and purges any remaining RSVP entries.
- Itinerary and RSVP deadlines reject malformed, nonexistent, or ambiguous
  local times unless an explicit offset resolves the instant.
- Itinerary day grouping uses the resolved instant in the intended timezone.
- Invitation lookup and client creation-retry indexes are startup-enforced.
- Reunion creation has a client-generated idempotency key and a backend unique
  constraint.
- Legacy event arrays and naive timestamps remain safe for the detail page and
  dashboard.
- Local QA can explicitly disable analytics. Apple, Google, and RevenueCat
  initialization cannot be disabled by deployed application switches; provider
  isolation belongs in the test harness.

## Verification evidence

The disposable database campaign uses only synthetic data and refuses to run
unless both MongoDB environment variables identify a database whose name starts
with `kindred_disposable_`. It verifies:

- Organizer, member, unrelated-user, and anonymous list/detail authorization.
- Organizer-only named RSVP notification enforcement across activity feed,
  notification history, unread counts, and mark-read writes, including
  actual historical `rsvp-update` event-scoped rows created before the
  organizer scope existed.
- Hidden-event exclusion across pre-existing linked memories, travel plans,
  budgets, notifications, searches, exports, digests, profiles, community
  projections, health aggregates, and legacy previews.
- Hide-versus-write race rejection for authenticated overall/activity RSVP and
  member-linked public invitation RSVP.
- Absence of bearer credentials and personal information in unauthorized
  responses.
- Sixteen simultaneous public respondents without lost overall responses,
  activity choices, party sizes, or invitation state.
- Legacy member reconciliation and separation of unrelated guest identities.
- Mixed-case legacy member reconciliation within the same community.
- Idempotent concurrent reunion creation.
- Unique invitation/idempotency indexes and an `IXSCAN` invitation lookup.
- Malformed, DST-nonexistent, DST-ambiguous, explicit-offset, timezone-override,
  expired, invalid-stored, and valid-future deadline behavior.
- Rejection of timezone updates that would make inherited activity starts,
  ends, or deadlines nonexistent or ambiguous.
- Header-only secure invitation reads/writes, rejection of backend path-token
  API requests, and the legacy web-route transition.

Browser checks use disposable local data. Provider initialization, analytics,
external delivery, billing, and email calls are disabled for that QA process.

Current local verification:

- Disposable MongoDB authorization, notification scope, identity, concurrency,
  timezone, deadline, index, idempotency, and invitation transport campaign:
  1 passed.
- Focused backend itinerary, activation, commercial-readiness, and billing
  kill-switch regressions: 45 passed.
- Frontend analytics, itinerary, draft/idempotency, pricing, and legacy
  compatibility tests: 28 passed.
- Backend compilation, production frontend build, and public-route prerender:
  passed.
- Browser service-worker upgrade from `kindred-v1` to `kindred-v2`: passed;
  the synthetic legacy invitation cache entry was removed.
- Synthetic desktop and mobile fragment/header invitation checks, legacy web
  transition, zero third-party resources on sensitive routes, empty referrer,
  and absence of cached or outbound token-bearing requests: passed. The
  campaign exits cleanly after closing all browser and server handles.
- Android debug build and unsigned iOS generic-device compilation: passed.

## Invitation-rotation recommendation

Do not rotate invitations until the corrective backend is deployed and an
authorized owner approves the user-impact plan. After containment:

1. Count invitation records attached to events that were readable by ordinary
   members during the exposure window.
2. Treat that count as the maximum affected-link population.
3. Rotate those credentials in one controlled operation.
4. Re-deliver replacement links through an approved channel.
5. Verify old links fail and new links resolve to the same event and intended
   respondent.

The principal impact is that every rotated link already copied, bookmarked, or
delivered stops working. Because sanitized logs cannot prove which generic
event responses were fetched or retained, selective rotation based only on
access logs is not sufficient evidence. No rotation was performed in this
corrective branch.

## Privacy-safe invitation redelivery hotfix

A later aggregate-only assessment identified two current guest invitation
credentials for owner-approved rotation. The first authorized production
attempt stopped before reading or changing invitation records because the
existing application did not have a privacy-safe redelivery path. Invitation
creation and reminder routes only prepared delivery state, while the generic
email helper logged recipient information.

This follow-up draft adds a dedicated operator-only redelivery workflow. It is
not exposed as an HTTP endpoint and does not use the generic email helper:

- A provider and header-validation preflight must pass before the workflow
  stages any replacement.
- The operator supplies aggregate selection criteria and an expected count;
  customer or invitation identifiers are not hard-coded.
- Replacement credentials are generated with `secrets.token_urlsafe(32)` and
  staged in a transaction while every old credential remains active.
- Recoverable old/new credential material is encrypted with a dedicated
  incident recovery key. The ciphertext is removed after successful
  header-only validation.
- Provider submission is transactionally claimed before the provider call and
  uses stable idempotency keys. Accepted, pending, submitting, rejected,
  timed-out, ambiguous, failed, and delivered states are recorded only as
  sanitized categories with opaque provider message IDs.
- A partial or ambiguous delivery leaves all old credentials active. Retrying
  a definitively rejected target reuses the same provider idempotency key and
  staged replacement. Ambiguous or interrupted submissions are never
  automatically submitted again, preventing duplicates after an unknown
  provider-acceptance outcome.
- Only after every replacement is confirmed delivered does one MongoDB
  transaction activate the complete set. Event `rsvp_revision` guards prevent
  concurrent RSVP or rotation snapshots from being overwritten.
- The generated web link is `/rsvp#credential`; post-activation validation
  uses only `Authorization: Bearer` against `/api/public/rsvp`.
- Reports and logs contain only aggregate counts, opaque operation/target IDs,
  safe status categories, and sanitized error codes. They never contain
  recipient data, event details, credentials, links, bodies, provider payloads,
  or raw exception text.
- The CLI requires the exact deployed commit and fails closed if the provider,
  verified sender domain, recovery key, stable application URL, or header-only
  validation endpoint is unavailable.

All hotfix verification uses synthetic disposable records and fake or mocked
delivery providers. No production invitation was rotated and no real email was
sent while preparing this draft.

Hotfix verification:

- Dedicated state-machine, privacy, provider-payload, header-transport, and
  static deployment-boundary tests: 19 passed.
- Existing itinerary, activation, commercial-readiness, and subscription
  kill-switch regressions combined with the new tests: 64 passed.
- Real privacy-safe outbox/activation transaction against a disposable MongoDB
  replica set: 1 passed.
- Existing disposable invitation confidentiality, notification scope,
  timezone/DST, concurrency, idempotency, and index campaign: 1 passed.
- Frontend invitation transport, analytics, itinerary, draft/idempotency, and
  pricing tests: 28 passed.
- Python compilation, formatting, Flake8, and mypy checks: passed.
- Production frontend build and public-route prerender: passed.
- Real-built-application browser campaign at desktop/mobile widths, including
  fragment/header transport, legacy transition, third-party isolation, and an
  installed `kindred-v1` worker upgrade that purges an RSVP request: passed.
- Android debug build and unsigned iOS generic-device build: passed.
- Generated web, Android, and iOS artifacts contain none of the synthetic
  invitation, recipient, recovery-key, or legacy-cache markers: passed.
- The public subscription checkout endpoint still returns HTTP 410 with
  `subscription_checkout_migrating`.

## Invitation-redelivery concurrency and preflight correction

Independent post-merge review identified three release blockers in the first
redelivery implementation. Production rotation remains prohibited until this
follow-up is independently reviewed and approved.

This correction:

- requires an explicit, stable, owner-approved operation ID and validates it
  before any persistence or provider activity;
- atomically claims one canonical incident-selection fingerprint and writes a
  durable per-invitation rotation marker, so a replacement credential cannot
  become eligible for another operation;
- preserves recovery through the original operation ID while rejecting a new
  operation ID for an already claimed or completed population;
- makes final validation a revision-checked transition from `activated` only,
  keeps terminal `completed` state immutable, and deletes recovery ciphertext
  only in the same successful transaction that records completion;
- records transient validation failures without downgrading a completed
  operation or destroying recovery material; and
- validates the application URL, delivery provider, validator, encryption
  material, transaction capability, and all required environment settings
  before creating an operation, claiming a target, writing an outbox record,
  changing an invitation, or calling the provider.

Synthetic verification covers missing and unsafe operation IDs, same- and
different-ID retries, activation crashes, competing operations, completed
retries, concurrent validators, transient validation failures, recovery
ciphertext lifetime, and parameterized configuration failures. Disposable
MongoDB tests verify the transaction and index behavior against a replica set.
No production invitation, customer record, provider, deployment, or
configuration was accessed or changed by this follow-up.

## Unchanged systems

The subscription HTTP 410 kill switch, RevenueCat, Stripe, Apple, Google Play,
GCP, production data, and provider configuration are untouched. Subscription
recovery remains paused.

## Restricted-key delivery-confirmation recovery

The authorized production attempt failed closed after the delivery provider
accepted both submissions because the least-privilege Sending-access key cannot
read individual message status. No credential was activated. The previous
status-polling design therefore left the recoverable operation waiting even
though opaque provider message references had been durably recorded.

This follow-up correction removes all provider message-status reads and adds a
signed, provider-only delivery callback. The callback is not a redelivery
trigger and cannot submit email or rotate an invitation. It verifies the raw
request body with the provider webhook secret before extracting only an opaque
event ID, opaque provider message ID, terminal safe status, and timestamp.
Recipient fields, message content, links, credentials, event details, and the
remaining provider payload are discarded.

Verified terminal events are applied transactionally and monotonically:

- duplicate events are idempotent;
- failure events cannot downgrade a delivered target;
- ambiguous or accepted targets can recover to delivered;
- a provider reference that resolves to zero or multiple operations is ignored;
- terminal activated or completed operations cannot be rewritten; and
- activation remains impossible until every selected target is durably
  confirmed delivered.

The operator CLI now requires the webhook signing secret during preflight,
before database import or mutation. A restricted Sending-access key remains
sufficient: it submits the privacy-safe invitation message, while signed
provider callbacks establish delivery. Deployment, provider webhook
configuration, event replay, operation resumption, and production rotation are
separate authorization gates and were not performed while preparing this
correction.
