# Release 7: organizer-approved guest family access

Last verified: 2026-07-31

## Outcome

Release 7 adds an optional, organizer-approved bridge from a completed no-account reunion RSVP into the existing Release 6 family space. RSVP remains fully usable without registration. Creating or signing into an account still grants no family access by itself.

The implementation started from the exact Release 6 merge commit `1ab74c26e025c3e3e8a9fd1638c90f5c639f34af` on `origin/main`. The code implementation commit is `b093f50633e9e336e4e792273c5708aeebbe0d76`; this report is part of the separate documentation closeout commit.

No production data, provider console, invitation-redelivery operation, deployed configuration, payment state, store listing, message delivery, production deployment, promotion, or merge was touched. After the draft PR branch was pushed, the repository's existing GitHub integration automatically produced an unpromoted Vercel preview; it was not opened or validated as part of this release.

## User journey

1. A guest opens `/rsvp#<invitation credential>` and submits a reunion response exactly as before.
2. Only an eligible responded guest for an active family space sees “Ask to join the family space.” The CTA is optional and explicitly says the RSVP is already saved.
3. The browser requests a short-lived continuity claim using the existing header-only invitation authorization. The claim is stored only in `sessionStorage`; the invitation fragment is removed before navigation.
4. The guest signs in with Apple, Google, or an existing password account, or creates a password account with no community membership.
5. `/family/join` submits the claim in `X-Kindred-Guest-Claim`, never in a URL. Successful submission clears the claim and its retry key from browser storage.
6. A host or organizer reviews the named request in the organizer command center and approves or declines it.
7. Approval transactionally attaches the authenticated account as the one canonical member and continues to the existing `/home` family space. Pending, declined, cancelled, expired, and conflict states remain safe status views.

## Identity and security boundary

- The invitation credential remains fragment-only on the web and header-only at `/api/public/rsvp` and `/api/public/family-access-claim`.
- The continuity claim is a different 256-bit random credential. MongoDB stores only its SHA-256 digest; it expires after 24 hours and is accepted only in a dedicated request header.
- Invitation credential replacement preserves the durable invite record. Release 7 fingerprints that stable event relationship from immutable internal attributes, so a claim issued before credential replacement can still be submitted. The fingerprint contains no raw credential or readable email.
- Email is never continuity proof. Release 7 social-auth intent explicitly disables the legacy pending-email-invite autojoin branch for newly created Apple/Google accounts. A password account created from this flow starts with `community_id=""` and `community_ids=[]`.
- Existing same-community membership converges to approved status. Any other, multiple, inconsistent, ambiguous, revoked, expired, malformed, deleted, or hidden-event relationship fails closed without cross-community merging.
- Platform-administrator flags do not bypass the canonical `host`/`organizer` role check.
- Public and applicant projections never return invitation credentials, continuity claims, emails, phone numbers, profile fields, other applicants, community/event/user database identifiers, relationship fingerprints, decision actor IDs, or operation hashes.

## Durable state and concurrency

The request state machine is `pending -> approved | declined | cancelled | expired | conflict`. Terminal states are immutable.

- A unique `(community_id, applicant_user_id)` index prevents duplicate canonical requests.
- Public action references are opaque and separately unique; decisions send them in a JSON body rather than an action URL.
- Submission, decision, and cancellation use validated idempotency keys stored only as one-way hashes.
- Submission atomically claims the continuity credential and creates the request.
- Approval uses a MongoDB transaction to re-read request state, re-check account/community consistency, update exactly one account membership, update the request revision, and add the applicant status notification.
- Compare-and-set revision guards make concurrent approval/decline and cancellation/decision races single-winner. Identical completed retries converge; divergent or stale retries return a categorical conflict.
- Missing accounts and cross-community state transition to `conflict`; no replacement user or duplicate membership record is created.

## Notifications and analytics

- Pending named-request notifications use `audience_scope="organizer"` and explicit host/organizer recipients.
- Applicant outcome notifications use `audience_scope="user"` and the applicant’s user ID. The shared notification query now enforces recipient IDs for all user-scoped records.
- Ordinary members cannot call the organizer list and cannot read named request notifications. Applicants can query only the request attached to their authenticated user ID.
- Release 7 analytics are limited to five approved funnel event names and bounded categories: source, request state, and approved/declined decision. Request references, account/community/event IDs, names, emails, credentials, free text, URLs, and provider identifiers are dropped.
- `/family/join`, reunion workspaces, and invitation routes suppress autocapture/replay snapshots; invitation routes continue to suppress all PostHog entry points.

## Preservation

Release 7 does not change invitation-redelivery selection, vaulting, provider delivery, activation, validation, reporting, or incident state. It also preserves hidden-event confidentiality, RSVP compare-and-swap behavior, activity RSVP isolation, the service-worker credential denylist, Apple/Google providers, RevenueCat initialization and purchase paths, and the `subscription_checkout_migrating` HTTP 410 web-checkout kill switch.

## Verification

- Focused and Release 1–6 offline regression suite: `235 passed` after correcting two copy-preservation assertions, then the two corrected assertions plus Release 7 suite: `7 passed`.
- Focused policy/auth/activation/organizer suite: `53 passed`.
- Disposable local MongoDB replica-set campaign: `1 passed`; it covered duplicate concurrent submission, one canonical request, concurrent approve/decline single-winner behavior, identical retry, relationship survival after credential replacement, ordinary-member denial, named-notification isolation, cross-community conflict, and revocation-after-claim denial.
- Frontend unit tests: `31 passed`.
- Optimized frontend build and prerender: passed.
- Capacitor sync completed for iOS and Android; the unsigned iOS Simulator Debug build and Android `assembleDebug` build both passed against the existing RevenueCat and native plugin stack. The iOS build retained the pre-existing unassigned app-icon and always-run CocoaPods script warnings; Android retained existing flat-directory, manifest, packaging, and Gradle deprecation warnings.
- Synthetic browser campaign: passed on a 390x844 mobile viewport; confirmed no invitation or continuity credential in API URLs, continuity header transport, claim clearing, and pending/approved status surfaces. Evidence is under `docs/screenshots/release-7/`.
- Existing Release 3–6 browser workflows were rerun after updating the organizer command-center harness for the new read-only request endpoint; results are recorded in the draft PR.
- Python compilation, `git diff --check`, and fatal flake8 checks passed.

All database and browser evidence used synthetic local records. Production was not accessed.

## Known limitations

- Claims have a 24-hour application expiry and requests have a 30-day lazy expiry; there is no background expiry worker or TTL deletion because terminal audit state is retained.
- Applicant decisions are in-app/status-page only. This release deliberately adds no email, SMS, or push delivery.
- A family space must already be explicitly `active`; provisional and ambiguous legacy communities do not offer this bridge.
- Cross-community accounts deliberately fail closed even though other Kindred surfaces support community switching.
- Account-deletion cascade coverage for the two new collections is documented but not added in this release.
- Production deployment/promotion, provider configuration, live customer data, and live native OAuth callbacks were intentionally not exercised. The automatically generated draft-PR preview was not treated as production evidence.
