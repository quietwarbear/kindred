# Kindred invitation exposure decision brief

Assessment date: 2026-07-28  
Repository: `quietwarbear/kindred`  
Corrective merge reviewed: `05696729ec02bbf5d62c01c91e6a9485bfa0db51`

## Decision

**Do not rotate yet. The aggregate-only assessment establishes a conservative
current-document population of 2 invitation records and 2 distinct
credentials. Subsequent explicitly authorized rotation attempts stopped
before selection or modification because mandatory configuration and provider
preflight gates did not pass.**

No individual production invitation record or customer field was returned or
inspected. The server returned only the five authorized integer counts. No
invitation was rotated, invalidated, copied, exported, logged, or retained.

## Authorized rotation attempt

The owner subsequently authorized rotation of the two current guest
credentials, conditional on current commit verification and a functioning,
privacy-safe redelivery channel for both invitations.

The operation failed closed before reading or modifying invitation records:

- The subscription checkout gate passed before the attempted rotation: a
  schema-valid synthetic request returned HTTP 410 with
  `subscription_checkout_migrating`.
- Current Railway commit provenance could not be re-established. The
  authenticated production dashboard connection repeatedly timed out, and the
  existing production tab remained controlled by another browser session.
  The earlier verified deployment evidence was not treated as a substitute for
  the required current gate.
- The deployed application does not contain a functioning invitation email
  sender. Event invitation creation records a `ready-for-email` status, and the
  gathering reminder endpoint only changes invitation fields to
  `email-ready`; neither path sends an invitation message.
- The available generic Resend helper logs the recipient address and subject.
  Using it for redelivery would violate the incident requirement not to log
  customer information.
- An ad hoc, unverified delivery mechanism was not substituted for the
  required authorized channel.

Aggregate-only execution status:

| Status category | Count |
|---|---:|
| Credentials selected | 0 |
| Credentials rotated | 0 |
| Replacements delivered | 0 |
| Old credentials rejected | 0 |
| New credentials validated | 0 |
| Failures | 1 |

No invitation record, recipient field, old credential, or replacement
credential was accessed. Subscription recovery remains paused.

## Second authorized rotation attempt after redelivery hardening

On `2026-07-30T02:45:44Z`, the owner authorized a second narrowly scoped
attempt using stable operation ID
`ca0b9461ea87f191ac145e62607da4e2`.

The production gates established:

- Railway's canonical `production` environment was active at merge commit
  `889965c7315d82d13f0c00d2711ba7fcaaf3563a`.
- The active deployment was the PR #17 concurrency and preflight hardening
  release, not the non-production `new_root` environment.
- A schema-valid synthetic subscription checkout request returned HTTP 410
  with `subscription_checkout_migrating`.

The reviewed production CLI then failed closed during configuration preflight,
before database import, operation creation, invitation selection, encryption,
provider activity, or invitation mutation. It returned only aggregate status:

| Status category | Count |
|---|---:|
| Credentials selected | 0 |
| Credentials rotated | 0 |
| Replacements delivered | 0 |
| Old credentials rejected | 0 |
| New credentials validated | 0 |
| Failures | 1 |

The sanitized error category was `configuration_unavailable`. A names-only
diagnostic, which did not read or return configuration values, established
that production lacks these required redelivery settings:

- `FROM_EMAIL`
- `PUBLIC_API_BASE_URL`
- `APP_URL`
- `INVITATION_REDELIVERY_RECOVERY_KEY`

No configuration was added or changed because the rotation authorization did
not authorize production configuration changes. The supplied operation ID did
not create an operation and remains the required stable ID for any authorized
retry.

After the failed-closed attempt:

- `GET /api/public/rsvp` without a credential returned HTTP 401.
- The same path with an invalid synthetic credential returned HTTP 404.
- Subscription checkout again returned HTTP 410 with
  `subscription_checkout_migrating`.

No invitation or customer record was retrieved or changed, and no provider
call or customer communication occurred. Subscription recovery remains paused.

## Third authorized attempt after production configuration

On `2026-07-30T03:00:38Z`, the owner authorized adding only the four required
redelivery variables to Railway's canonical production service, the resulting
restart, the Resend verification preflight, and one retry using the same stable
operation ID.

The following gates passed before the retry:

- Railway applied exactly four service-variable changes and restarted the
  canonical `production` service.
- The replacement deployment became active and successful from the PR #17
  release.
- The running container reported commit
  `889965c7315d82d13f0c00d2711ba7fcaaf3563a`.
- `GET /api/public/rsvp` without a credential returned HTTP 401.
- A schema-valid synthetic subscription checkout request returned HTTP 410
  with `subscription_checkout_migrating`.

The authorized Resend domain-verification preflight returned HTTP 401. The
redelivery CLI failed closed with sanitized code `provider_unavailable` before
database import, operation creation, target selection, encryption, provider
submission, or invitation mutation.

Aggregate-only execution status:

| Status category | Count |
|---|---:|
| Credentials selected | 0 |
| Credentials rotated | 0 |
| Replacements delivered | 0 |
| Old credentials rejected | 0 |
| New credentials validated | 0 |
| Failures | 1 |

Post-failure containment checks reconfirmed:

- `GET /api/public/rsvp` without a credential returned HTTP 401.
- The same path with an invalid synthetic credential returned HTTP 404.
- Subscription checkout returned HTTP 410 with
  `subscription_checkout_migrating`.

No invitation or customer record was retrieved or changed. No replacement
link was created, no delivery submission occurred, and no customer
communication was sent. The stable operation ID remains the only authorized
recovery identifier. Rotation remains blocked pending correction or
replacement of the production Resend credential under separate explicit
authorization. Subscription recovery remains paused.

## Authorized aggregate-only follow-up

The owner subsequently authorized authenticated Railway deployment-metadata
access and one server-side, aggregate-only production query.

- Authenticated Railway metadata identified active deployment
  `549fd2a2-a3eb-414a-a453-5aadf7dc9e8e` for the canonical production service
  `ae44008e-7787-45a2-80ab-8e07822e7ef1` in environment
  `7f71207e-b7a5-4da5-91bd-81753db88576`.
- The deployment was successful and active, was sourced from
  `quietwarbear/kindred` branch `main` with root directory `/backend`, and
  linked directly to commit
  `05696729ec02bbf5d62c01c91e6a9485bfa0db51`.
- Only after that provenance gate passed, one MongoDB aggregation was executed
  inside the running production service. It returned only the five authorized
  non-negative integers.

## Production state

- Vercel production deployment `dpl_DqkXbmXN7Z9jF23MCrbVr4iPrD6t` is READY,
  production-aliased to `www.heykindred.org`, and reports corrective merge
  `05696729ec02bbf5d62c01c91e6a9485bfa0db51`.
- Railway production deployment
  `549fd2a2-a3eb-414a-a453-5aadf7dc9e8e` is active and reports corrective merge
  `05696729ec02bbf5d62c01c91e6a9485bfa0db51`.
- The canonical Railway backend is healthy and exposes the corrected stable
  invitation endpoint:
  - `GET /api/public/rsvp` without a credential returned HTTP 401.
  - The same path with a synthetic invalid credential returned HTTP 404.
- A schema-valid synthetic subscription checkout request returned HTTP 410 with
  `subscription_checkout_migrating`.
- The HTTP 410 response and `subscription_checkout_migrating` code were
  reconfirmed after the aggregate-only query. Subscription recovery remains
  paused.

## Exposure window

Use this operational window for any subsequent aggregation:

- **Start, inclusive:** `2026-07-26T06:34:45Z`
  - Successful Railway production status for vulnerable PR #14 merge
    `ecb978c3d20d99c0ed5574d2f325c6c72353cea9`.
- **End, exclusive:** `2026-07-28T19:04:14Z`
  - Successful Railway production rollback status for pre-reunion commit
    `0f61fff0bc464d67905f04349eb3015e7937d827`.
- **Duration:** 60 hours, 29 minutes, 29 seconds.

The vulnerable Vercel deployment completed at `2026-07-26T06:35:00Z`, fifteen
seconds after the backend status. The earlier backend timestamp is used because
authenticated mobile/direct API clients could reach the generic event API
without waiting for the frontend deployment.

These are deployment-status boundaries, not evidence of the first or last
actual request. The incident document states that sanitized logs were
inconclusive, so access-log evidence must not narrow the population.

## Selection criteria

The vulnerable response schema applied to generic events, not only events whose
template was `reunion`. A later aggregate must therefore include every
invitation record that met all of these conditions:

1. It was attached to any generic event for some portion of the exposure
   window.
2. The event was readable by at least one ordinary authenticated member in the
   same community at that time.
3. The invitation credential existed before the window ended.

For counts only:

- Classify `invite_source == "member"` as a member invitation.
- Classify `invite_source == "guest"` as a guest invitation.
- Report missing or other values as `unknown`; do not infer identity from
  email, name, or `member_id`.
- Return only integer counts for member, guest, unknown, total invitations, and
  distinct credentials.
- Do not return samples, document identifiers, event identifiers, community
  identifiers, credentials, or any customer field.

Current mutable documents cannot by themselves prove historical visibility,
removed invitations, role history, or changes to `hidden_from_user_ids`.
Historical backups or audit records must be included if they exist. If history
is unavailable, use the conservative upper bound: all invitation credentials
on all events that existed by the end boundary, plus any deleted records
recoverable from authorized historical sources.

The executed current-document aggregate used the following conservative
criteria:

- Collection: generic `events`; no `event_template` restriction.
- Event timestamp: include parsed `created_at` values at or before
  `2026-07-28T19:04:14Z`; include missing or malformed timestamps rather than
  exclude them.
- Invitation timestamp: apply the same end-boundary rule to each embedded
  `event_invites` record.
- Visibility: include all otherwise qualifying events, rather than attempting
  to reconstruct historical member visibility from mutable fields.
- Classification: exact `invite_source` values `member` and `guest`; every
  other or missing value is `unknown`.
- Credential distinctness: server-side set cardinality over non-null,
  non-empty invitation credential values.

The documented incident window remains start-inclusive and end-exclusive. The
aggregate deliberately used an inclusive end comparison as a conservative
upper-bound treatment of boundary ambiguity. Therefore, a record stamped
exactly `2026-07-28T19:04:14Z`, if one existed, would be included rather than
risk an undercount.

## Affected-link count

| Population | Count |
|---|---:|
| Member invitations | 0 |
| Guest invitations | 2 |
| Unknown/legacy source | 0 |
| Total invitation count / conservative current-document population | 2 |
| Distinct credential count | 2 |

Confidence:

- High confidence in Vercel commit and current endpoint/checkout behavior.
- High confidence in the vulnerable backend start and rollback completion
  timestamps recorded by GitHub deployment statuses.
- High confidence in exact Railway corrective commit provenance.
- High confidence that the five integers accurately represent the conservative
  current `events`-collection criteria above.
- Limited confidence that current mutable documents capture invitations
  deleted before assessment. No historical backup or audit source was queried
  under the one-query authorization, so the count cannot exclude an additional
  deleted-record population.

Validation:

- All five returned values were non-negative integers.
- `0 member + 2 guest + 0 unknown = 2 total`.
- `2 distinct credentials <= 2 total invitations`.
- The result contained no record samples, database identifiers, event fields,
  customer fields, or credential values.

## Rotation recommendation

Subject to separate explicit owner approval, the recommended current-document
scope is all 2 distinct credentials in the conservative affected population.
Do not narrow the scope using access logs. If an authorized historical source
later establishes deleted invitation records that met the incident criteria,
add their distinct credentials to the scope before rotation.

Before execution, an owner must explicitly approve:

1. The final aggregate counts and selection window.
2. The expected invalidation of 0 member, 2 guest, and 0 unknown-source
   invitation records, representing 2 distinct credentials in the current
   population.
3. The redelivery channel and support plan.
4. The controlled rotation operation and verification checklist.

## Rotation impact and redelivery

- Every affected link already delivered, copied, bookmarked, or stored will
  stop working.
- Each intended respondent needs exactly one replacement fragment-form link
  delivered through an approved private channel.
- Redelivery must not place credentials in HTTP paths, query strings,
  analytics, referrers, screenshots, exports, or operator logs.
- Unknown/legacy-source invitations require an owner-approved handling rule;
  identity must not be inferred from email casing or display name.
- Support messaging and delivery retries must be approved before rotation, not
  improvised after invalidation.

## Rollback considerations

- Do not roll application code back to the vulnerable PR #14 behavior.
- Do not restore invalidated credentials after a partial rotation; resume the
  controlled operation instead.
- Make the rotation idempotent and checkpointed by aggregate state, without
  emitting credential mappings.
- Preserve the subscription HTTP 410 kill switch throughout. Subscription
  recovery remains outside this incident operation.

## Verification plan after approval

1. Reconfirm exact Vercel and Railway production commits.
2. Re-run credential-free and synthetic-invalid checks on
   `/api/public/rsvp`; expect 401 and 404 respectively.
3. Reconfirm checkout returns 410 and `subscription_checkout_migrating`.
4. Run the reviewed aggregate-only count and record only integer outputs.
5. Obtain explicit owner approval for the stated count and user-impact plan.
6. Execute a synthetic dry run of the idempotent rotation mechanism.
7. Rotate the approved population in a controlled operation.
8. Verify server-side, using aggregate assertions only, that:
   - the expected number of old credentials no longer resolves;
   - the same number of unique replacement credentials exists;
   - respondent/event associations and member/guest classifications are
     unchanged;
   - no duplicate credentials were created.
9. Deliver replacement links through the approved private channel.
10. Reconfirm invitation endpoint behavior, path-safe logging, and the
    subscription 410 response.

No rotation or invalidation may begin without explicit owner approval.
