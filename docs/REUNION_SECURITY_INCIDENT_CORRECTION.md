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
  aggregates, memory associations, and subcommunity gathering counts.
- Public invitation routes continue to return only the held invitation's
  minimal view and aggregate activity attendance.

RSVP writes use a revision-guarded compare-and-swap loop with bounded retry.
Concurrent public and authenticated updates can no longer replace a newer
whole-event RSVP snapshot.

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
  historical event-scoped RSVP rows created before the organizer scope existed.
- Hidden-event exclusion across every event-derived member surface.
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
  transition, and zero analytics/identity scripts on sensitive routes: passed.
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

## Unchanged systems

The subscription HTTP 410 kill switch, RevenueCat, Stripe, Apple, Google Play,
GCP, production data, and provider configuration are untouched. Subscription
recovery remains paused.
