# Release 4: Reunion Attendee Hub

## Product outcome

Release 4 turns a confirmed reunion invitation into a calm, mobile-first
attendee experience: see the plan, confirm attendance, choose or release a
contribution, and keep one family story. It preserves the Release 3 organizer
command center as a separate authorized surface.

The attendee hub returns exactly one deterministic next action. It contains no
organizer controls, invitation ledger, named attendance roster, planning data,
or other attendee's response.

## Provenance and scope

- Branch baseline: `origin/main` at
  `c90226b2ed1741f2f8bf82658a625d3eea4ed383`, the merge commit for PR #22.
- Work is limited to the attendee hub, public RSVP confirmation continuity,
  contribution integrity, ordinary-member projection hardening, analytics,
  tests, synthetic evidence, and documentation.
- No production environment, customer record, deployment, provider, store
  console, store listing, or outbound message was accessed or changed.

## Deterministic attendee action priority

Exactly one action code is returned:

| Priority | Stable code | Trigger |
| --- | --- | --- |
| 1 | `respond_to_reunion` | No canonical overall response |
| 2 | `complete_activity_responses` | A published, open activity requests a response and has none |
| 3 | `choose_contribution` | The attendee has no commitment and safe capacity remains |
| 4 | `review_itinerary` | Published activities exist and the attendee has not reviewed them |
| 5 | `share_a_memory` | The attendee has not saved the optional reunion story |
| Fallback | `reunion_plan_complete` | No higher-priority action remains |

## Security and privacy design

- Every attendee route uses the existing session dependency and canonical
  community/hidden-event lookup, then requires `event_template=reunion`.
- Cross-community and hidden reunions return `404`; anonymous requests remain
  `401`.
- The attendee projection includes published activities, the current member's
  own canonical RSVP/activity state, anonymous aggregates, safe contribution
  capacity, and the member's own commitments.
- Contribution mutations use event compare-and-swap updates. Final-capacity
  races have one winner, retries are naturally idempotent, and hidden-event
  predicates remain in the atomic write.
- The optional memory prompt uses the existing private-community memory schema.
  A deterministic MongoDB key makes concurrent retries converge on one record.
  This route does not invoke AI tagging, analytics providers server-side, email,
  or any other external provider.
- Public RSVP keeps credential transport in the request header and does not put
  credentials in the URL, logs, screenshots, or analytics.

See `docs/RELEASE_4_ATTENDEE_PROJECTION_MATRIX.md` and
`docs/RELEASE_4_ROUTE_AND_DATA_INVENTORY.md` for the field and operation
contracts.

## Analytics

The existing analytics allowlist now recognizes:

- `reunion_hub_viewed`
- `attendee_next_action_viewed`
- `contribution_claimed`
- `contribution_released`
- `memory_prompt_started`
- `memory_prompt_completed`

Only the existing low-cardinality safe property allowlist is emitted. Event,
community, invitation, email, story, title, and attendee identifiers are not
analytics properties.

## Verification evidence

- Expanded attendee, organizer, itinerary, activation, store/trust,
  invitation-redelivery, and checkout compatibility campaign: 197 tests passed
  with two dependency deprecation warnings.
- The focused attendee/organizer/itinerary subset passed 44 tests; the Release 4
  attendee unit/static file passed 11 tests.
- Disposable MongoDB security campaign: attendee authorization, strict
  projection, hidden/cross-community isolation, one-winner final contribution
  races, idempotent retry, concurrent one-record memory creation, no AI tags,
  and hidden-event write races passed.
- Invitation-redelivery disposable replica-set campaign: 3 tests passed.
- Frontend: 5 suites and 28 tests passed.
- Production frontend build and prerender succeeded for `/`, `/reunion/start`,
  `/pricing`, `/privacy`, `/terms`, and `/support`.
- Release 4 production-build browser campaign passed at desktop/mobile widths:
  attendee projection, canonical contribution mutation, offline lockout,
  public RSVP confirmation, header-only credential transport, and zero
  external requests.
- Existing offline browser campaign passed RSVP fragment/header transport,
  legacy transition, service-worker bypass/cache purge, reunion activation,
  pricing, and public policy/support routes.
- An independent browser smoke check rendered meaningful production-build home
  content without an error overlay.
- Android web assets synced and `assembleDebug` succeeded with the local Android
  SDK and Java 21 in a disposable copy.
- iOS web assets/CocoaPods synced and an unsigned `iphoneos` Debug build
  succeeded in a disposable copy.
- OpenAPI contains all five new or newly exposed attendee operations; none adds
  a credential, token, invite-code, or email path/query parameter.
- Changed Python sources pass compilation, Black, and Flake8 checks. Diff
  whitespace, sensitive logging, and common high-confidence secret-pattern
  scans pass. The optional `detect-secrets` package is not installed.
- Broad repository Black remains a pre-existing formatting baseline and is not
  rewritten by this release.

All browser and database fixtures are synthetic and disposable.

## Synthetic screenshots

Generated from the real production frontend build with in-process synthetic
responses and all external requests blocked:

- `docs/screenshots/release-4/reunion-attendee-hub-desktop.png`
- `docs/screenshots/release-4/reunion-attendee-hub-mobile.png`
- `docs/screenshots/release-4/public-rsvp-confirmation-mobile.png`

## Known external gates

- No unmerged commit is deployed; production behavior is intentionally
  unverified.
- No Apple App Store or Google Play build, metadata, screenshot, or listing is
  published.
- Production provider configuration, live provider behavior, and customer data
  are deliberately outside this release.
- Existing legal/provider confirmations in `docs/PRIVACY_DATA_MAP.md` remain
  open.
