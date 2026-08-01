# Release 13 — Thanksgiving Pilot Readiness

## Release boundary

- Baseline: `265627e1f6059eb9df959dd9bcfbf42969bb5fd5`
- Scope: the synthetic Thanksgiving organizer journey built on the Release 11 holiday-meal template
- Production data, customer records, live providers, invitations, messages, configuration, deployments, and store listings: not accessed or changed
- Legacy Table remains governed by the Stage 12B delivery bridge. This release does not enable or exercise a live recipe transfer.
- Subscription recovery remains paused. The checkout HTTP 410 kill switch is unchanged.

## Outcome

Release 13 turns the existing private holiday-meal draft into an explicit pilot workflow:

1. `draft` — organizer-only setup and aggregate invitation-plan preview;
2. `ready_to_invite` — the organizer completed required setup and may prepare credentials;
3. `invitations_sent` — bounded delivery evidence exists;
4. `active` — the gathering start has passed;
5. `completed` — the gathering end has passed;
6. `archived` — the event has an archive marker.

The organizer sees a content-free checklist, bounded counts, and one next-action category. Members and guests do not receive pilot confirmations, readiness state, or the internal setup revision.

## Security correction discovered during implementation

The Release 11 organizer draft was hidden from authenticated member views, but the invitation-creation endpoint did not reject `organizer_draft`, and the public RSVP token lookup did not independently reject it. An organizer could therefore create credentials before completing private setup, and a holder of such a credential could resolve the draft.

Release 13 closes both paths:

- invitation credentials cannot be created while `publication_state` is `organizer_draft`;
- the public RSVP lookup fails closed for organizer drafts even if a legacy or malformed record already contains an invitation;
- the browser draft flow provides only a local aggregate plan preview and performs no invite mutation;
- finish-setup uses an atomic setup-revision compare-and-swap so concurrent edits or checklist changes cannot publish a stale review.

## Readiness policy

Required before finish setup:

- essential title, location, and positive capacity;
- valid start, end, and IANA timezone with end after start;
- a valid, unambiguous RSVP deadline no later than the start;
- explicit privacy review;
- explicit guest-plan review;
- explicit organizer preview.

Recommended after setup:

- food/help coordination;
- reminder-plan review;
- confirmation that invitations were shared, which remains unavailable until at least one active invitation exists.

Checklist writes contain only an allowlisted status code and boolean. The server-derived readiness response contains only stable codes, booleans, and bounded integer counts—never names, emails, titles, locations, notes, links, credentials, message bodies, or provider payloads.

## Continuity preserved

- invitation credentials remain fragment-to-header only for public RSVP;
- organizer draft list/detail confidentiality remains role-filtered;
- hidden gathering visibility rules remain unchanged;
- event-level RSVP deadline validation uses the existing DST-safe local-time parser;
- invitation RSVP concurrency and idempotency code is unchanged;
- reminders and delivery providers are not called by draft creation, preview, checklist, or finish setup;
- agenda, roles, volunteer slots, potluck items, attendee hub, reminder preparation, recap, memory capsule, and Legacy Table preview remain the existing bounded surfaces;
- no new analytics event was added to the private pilot surface;
- no HTTP redelivery or recipe-delivery route was added;
- Apple, Google, RevenueCat, and provider initialization are unchanged.

## Finding-to-test matrix

| Risk | Control | Evidence |
|---|---|---|
| Draft credential creation | Backend blocks invite creation; UI previews counts only | focused unit route test; built-browser mutation count |
| Draft resolution by credential | Public lookup rejects organizer drafts | focused public lookup test |
| Stale concurrent publish | Setup revision CAS on edit, checklist, and finish setup | focused conflict test; disposable Mongo concurrent publish campaign |
| Malformed/nonexistent/ambiguous time | Existing timezone parser validates start, end, deadline before persistence | parameterized existing itinerary coverage plus Release 13 ambiguous deadline no-insert test |
| Pilot state exposed to members | Sensitive-field projection strips confirmations, readiness, revision | member projection test |
| Content in checklist/report | Allowlisted code/boolean input; code/count-only output | content-marker test and built-browser request-body assertion |
| Accidental provider or third-party activity | No provider call in workflow; browser aborts and records all external requests | built-browser third-party-isolation campaign |
| Checkout re-enabled | Existing HTTP 410 contract unchanged | subscription kill-switch regression |

## Verification evidence

- Focused Release 11 plus Release 13 holiday/privacy tests: `24 passed`.
- Full offline backend unit/static selection: `309 passed`.
- Existing checkout/provider/static safety selection: `31 passed`.
- Disposable Mongo campaigns: nine campaign files, `11 passed`, each run in its own process to respect their existing Motor event-loop isolation.
- Frontend Jest: `41 passed`.
- Optimized frontend production build and public prerender: passed for `/`, `/reunion/start`, `/pricing`, `/privacy`, `/terms`, and `/support`.
- Built-browser campaigns: Releases 3–10, commercial readiness, and Release 13 passed with synthetic responses. The Release 13 campaign verified draft mutation blocking, count-only invitation preview, explicit checklist/publish actions, empty API query strings, and zero third-party requests.
- OpenAPI: `191` paths and `221` methods; both Release 13 organizer routes and header-only public RSVP are present, with no path-token RSVP API.
- Android: Capacitor sync plus debug build passed in a disposable copy with `340` actionable tasks.
- iOS: Capacitor sync plus unsigned generic `iphoneos` Debug build passed in the disposable copy. Existing CocoaPods always-run and absent AppIntents metadata warnings remain non-blocking.
- Black `26.1.0`, Python compilation, fatal Flake8 checks, secret-marker scan, logging/analytics/provider-disable review, generated-artifact cleanup, and `git diff --check`: passed.
- Eight explicitly environment-gated API collections and other live-URL test modules were not pointed at production. Production was not probed for this implementation task.

## Verdict

**Ready for a small consenting pilot after merge, deployment, and the separate production checklist.** This branch remains unmerged and undeployed. It does not authorize creation of the real dinner, invitations, provider calls, messages, Legacy Table delivery, subscription recovery, or store publication.
