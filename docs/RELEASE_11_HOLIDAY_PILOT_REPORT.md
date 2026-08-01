# Release 11 holiday pilot and Legacy Table continuity report

Baseline: `ab85333fca63dacb6393c3dd613e9d5f05aa576a`. This release is a draft, unmerged, undeployed change set. Verification uses synthetic records only.

## Journey and privacy boundary

`holiday_meal` adds editable neutral meal defaults and creates an idempotent `organizer_draft`. Creation produces no invitations, RSVP rows, named role assignments, notifications, or provider calls. An organizer explicitly finishes setup before signed-in members can see it. Existing RSVP, itinerary, potluck, volunteer, memory, recap, and next-gathering foundations are reused. Today emits only categorical action codes and opaque references.

Pilot feedback uses the existing external support path because a private comment store and internal-reader authorization would materially expand this release. The UI supplies bounded rating/category instructions and a warning not to include family data. Kindred stores and analyzes no feedback text.

## Legacy Table threat model and decision

The prior implementation accepted an arbitrary base URL, returned identity and origin details in status, mutated state during preview, let organizers transfer another author's content, added community/teller content automatically, exposed provider bodies/errors, and treated a create attempt as synchronization.

The inspected sibling contract exposes recipe creation but no destination idempotency key or acceptance-reconciliation lookup. Therefore Release 11 follows the specified fail-closed branch: author-only preview and hardened cross-product sign-in may be configured, while live recipe delivery returns `destination_idempotency_contract_required`. The Kindred recipe is never altered.

## Transfer and consent matrix

| Action | Actor | Data leaving Kindred | Mutation | Result |
| --- | --- | --- | --- | --- |
| Status | authenticated member | none | none | categorical state/capability only |
| Recipe preview | exact recipe author | none | none | selected title/body plus categorical behavior |
| Abandon/decline | exact recipe author | none | none | unchanged |
| Cross-product sign-in | authenticated member | identity required by sibling | one-time code | only when exact configuration and sibling contract pass |
| Recipe delivery | exact recipe author | blocked | none | unavailable pending safe destination contract |
| Bulk/member/event export | anyone | blocked | none | HTTP 410 or absent |

Consent is not prechecked. Preview never initiates sign-in or delivery. Organizer status alone grants no author capability. Guests without an authenticated member identity cannot access the route.

## URL and SSRF validation matrix

Only exact compile-time HTTPS origins are accepted. The validator rejects HTTP; malformed URLs; credentials; paths, query strings, and fragments; unexpected ports; loopback, private, link-local, reserved, multicast, unspecified, and metadata addresses; and every non-allowlisted host. HTTP clients disable redirects, and any redirect response fails closed. Configured origins are never returned to members.

## SSO state machine

`unconfigured/invalid -> unavailable`; valid exact server configuration -> `ready`; trusted server presents secret + exact source origin + audience -> random 256-bit-class authorization code; database stores only SHA-256 digest, user reference, audience, origin, expiry, and categorical use state; landing page extracts and removes the query before third-party initialization; redeem atomically matches digest + audience + unexpired + unused; success unsets digest and marks used. Reuse, expiry, wrong audience, wrong landing origin, redirect, ambiguous normalized identity, or missing user fails closed. The landing response is no-store/no-referrer/noindex and application/static analytics are suppressed.

The older shared-secret `/auth/exchange` contract is retired with HTTP 410 because it returned a full session directly and bypassed the authorization-code state machine.

## Role and visibility matrix

| Surface | Organizer | Recipe author member | Other member | RSVP-only guest |
| --- | --- | --- | --- | --- |
| Holiday organizer draft | view/edit/finish | hidden | hidden | hidden |
| Published meal | authorized event view | authorized event view | authorized event view | invitation-scoped only |
| Named response management | organizer-only existing controls | own response only | own response only | own invitation response only |
| Contribution claims | manage + own claims | own claims/releases | own claims/releases | unavailable until authenticated |
| Recipe preview | own recipe only | own recipe only | no | no |
| Legacy status | categorical | categorical | categorical | no |

## Logging, analytics, retention, and deletion

No code logs names, email addresses, event/community titles, recipes, feedback text, invitations, SSO codes/tokens/secrets/headers, provider bodies, remote identifiers, destination URLs, or customer-operation mappings. Today analytics accepts only allowlisted categorical action codes; SSO and invitation routes suppress analytics before application execution. Preview has zero persistence. SSO records expire through the existing TTL and are removed on account deletion. Obsolete community Legacy Table configuration is removed with owner-scoped community deletion. Recipe content remains a Kindred Legacy Thread unless the author/account lifecycle removes it under existing policy.

## Finding-to-test matrix

| Finding | Control | Evidence |
| --- | --- | --- |
| Arbitrary origin / SSRF | exact validator + redirects disabled | prohibited-origin parameter campaign |
| Identity/content status leak | categorical projection | status schema test/review |
| Mutating preview | no collection writes in route | before/after preview unit test |
| Organizer transfers another author | exact `created_by == user.id` | organizer-denial unit test |
| Destination duplicate ambiguity | live transfer unavailable | HTTP 503 contract error and unchanged source |
| SSO URL/telemetry exposure | early query scrub + no-store + analytics suppression | frontend build/test and static review |
| Draft leakage | `organizer_draft` visibility query | existing hidden/draft authorization campaigns |
| Retry duplicate | required holiday request ID + existing unique index | event idempotency path and regression suite |

## Known limitations and live gates

- Live Legacy Table recipe delivery is intentionally unavailable. Enabling it requires a separately reviewed sibling API with destination idempotency, immutable revision binding, acceptance lookup, ambiguous-timeout recovery, and opaque references.
- No production SSO origins/secrets were configured and no live provider was called.
- Real pilot creation, participant invitations, deployment, native publication, and production validation require separate authorization.
- Full live API browser campaigns requiring a disposable Mongo replica set or running backend must be executed in the owner-approved release environment; never substitute production data.

## Verification evidence

- Focused Release 11 synthetic privacy/SSRF/preview/ownership/Today/SSO tests: `16 passed`.
- Full offline backend unit and static regression selection: `286 passed`.
- Existing attendee-hub and recap continuity with the focused suite: `41 passed`.
- Frontend Jest regression, including SSO analytics isolation: `35 passed`.
- Optimized frontend production build and public prerender: compiled and prerendered successfully.
- OpenAPI: `186` paths and `213` methods; Release 11 status, preview, and holiday-draft transition are present.
- Android: Capacitor sync and `assembleDebug` completed with `BUILD SUCCESSFUL` under Java 21 in a disposable copy. No repository Android asset was modified or published.
- iOS: Capacitor sync and unsigned generic `iphoneos` Debug compilation completed with `BUILD SUCCEEDED` in the same disposable copy. Pre-existing unassigned icon, always-run CocoaPods phase, and absent AppIntents metadata warnings remain.
- Python compilation, fatal Flake8 checks, credential/provider/logging/analytics/static-origin scans, generated-artifact review, and `git diff --check`: passed.
- The full aggregate pytest command also identified eight live-API modules gated on `REACT_APP_BACKEND_URL`; they were not pointed at production. Seven disposable campaigns were likewise skipped without `KINDRED_DISPOSABLE_MONGO_URL`.
- Standalone ESLint was not available because this repository has no ESLint configuration; the Create React App compiler completed without lint/build errors.
- Desktop/mobile authenticated browser campaigns were not fabricated without a running synthetic backend. They remain an owner-environment gate alongside the disposable Mongo campaigns.

See `docs/RELEASE_11_HOLIDAY_PILOT_RUNBOOK.md` for operations and closeout.
