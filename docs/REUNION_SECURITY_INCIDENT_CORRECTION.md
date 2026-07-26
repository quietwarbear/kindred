# Reunion security and integrity correction

Status: corrective branch prepared after the external merge of PR #14. This
document does not declare the correction deployed or the incident contained.

## Production triage

- The PR #14 merge commit is present on `main`.
- The production frontend deployment identifies that merge commit.
- The reachable backend schema includes the reunion operations, activity RSVP,
  and public RSVP structures introduced by the merge.
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

- Secure `/rsvp/:token` routes suppress every product-analytics entry point,
  Google Tag Manager, Google Analytics, and referrer propagation.
- Backend access logging is disabled so raw bearer paths are not written by the
  application server.
- Itinerary and RSVP deadlines reject malformed, nonexistent, or ambiguous
  local times unless an explicit offset resolves the instant.
- Itinerary day grouping uses the resolved instant in the intended timezone.
- Invitation lookup and client creation-retry indexes are startup-enforced.
- Reunion creation has a client-generated idempotency key and a backend unique
  constraint.
- Legacy event arrays and naive timestamps remain safe for the detail page and
  dashboard.
- Local QA can explicitly disable analytics and provider initialization; this
  does not change production defaults or provider configuration.

## Verification evidence

The disposable database campaign uses only synthetic data and refuses to run
unless both MongoDB environment variables identify a database whose name starts
with `kindred_disposable_`. It verifies:

- Organizer, member, unrelated-user, and anonymous list/detail authorization.
- Absence of bearer credentials and personal information in unauthorized
  responses.
- Sixteen simultaneous public respondents without lost overall responses,
  activity choices, party sizes, or invitation state.
- Legacy member reconciliation and separation of unrelated guest identities.
- Idempotent concurrent reunion creation.
- Unique invitation/idempotency indexes and an `IXSCAN` invitation lookup.
- Malformed, DST-nonexistent, DST-ambiguous, explicit-offset, timezone-override,
  expired, invalid-stored, and valid-future deadline behavior.

Browser checks use disposable local data. Provider initialization, analytics,
external delivery, billing, and email calls are disabled for that QA process.

Final local verification:

- Disposable MongoDB authorization, identity, concurrency, deadline, index,
  and idempotency campaign: 1 passed.
- Focused backend itinerary, activation, commercial-readiness, and billing
  kill-switch regressions: 41 passed.
- Frontend analytics, itinerary, draft/idempotency, pricing, and legacy
  compatibility tests: 25 passed.
- Backend compilation, production frontend build, and public-route prerender:
  passed.
- Android debug build and unsigned iOS generic-device compilation: passed.
- The iOS simulator was not launched because this Mac's CoreSimulator
  framework is older than the installed Xcode build.

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
GCP, production data, and provider configuration are untouched.
