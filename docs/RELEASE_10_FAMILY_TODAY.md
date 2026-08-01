# Release 10: unified Family Today

Last verified: 2026-07-31

## Outcome and architecture

Release 10 replaces the broad signed-in landing page with one calm, role-aware Today view while retaining every existing module and URL. The exact baseline is Release 9 merge `24700e90fe3bbdafa3d9d9a51fe2fcfdbdb9a831`.

`GET /api/today` reloads the canonical account, current membership, community role, and lifecycle inside one MongoDB snapshot transaction. It reads authoritative Release 3–9 sources and returns one primary action, at most three unique secondary categories, at most four content-free recent-change categories, bounded navigation/lifecycle state, and two bounded milestone codes. It performs no writes.

Dynamic event destinations use deterministic SHA-256 action references, never IDs. `GET /api/today/actions/{reference}` recomputes a fresh snapshot and returns an existing authorized path only when the reference is still present for that same account and community. A changed, stale, removed, hidden, cross-community, or malformed reference returns 404.

## Today priority and tie-breaking matrix

| Priority | Organizer or host | Member / attendee |
|---:|---|---|
| 1 | Activate provisional family space | Confirm approved family access for a newly approved member; otherwise complete own RSVP |
| 2 | Finish incomplete non-converted reunion draft | Complete missing activity responses |
| 3 | Prepare or share first invitation | Review updated published itinerary |
| 4 | Review pending family-access requests | Choose or release a contribution |
| 5 | Resolve missing/approaching RSVP attention | Respond to a published gathering pulse |
| 6 | Complete next command-center task | Continue own private memory draft |
| 7 | Review recap ready to publish | View newly published authorized recap |
| 8 | Review submitted gathering proposal | Check own family-access status |
| 9 | Continue converted private draft | Open family home fallback |
| 10 | Open active command center fallback | — |

Priority is compared before all tie fields. Within one action code, reunion actions sort by authoritative start, creation, then internal record key; proposal/access fallbacks sort by creation then key. The key and sort values never leave the server. Duplicate action codes collapse before the first four actions are projected, so a lower-priority card cannot displace a higher-priority primary action.

## Role and visibility matrix

| Canonical state | Today result | Visible primary navigation | Denied |
|---|---|---|---|
| Active host/organizer | Organizer priorities | Today, Gatherings, Proposals, Activity | Platform-admin flag cannot add authority |
| Active member/attendee | Own-action priorities | Today, Gatherings, Proposals, Activity | Organizer controls, named gaps, other responses |
| Approved, not-confirmed member | `confirm_family_access`, then own actions | Member navigation | Request identities and organizer review |
| Provisional host/organizer | `activate_family_space` | Today, Family activation, Gatherings | Active-family projections |
| Provisional ordinary member | 404 | None | All Today data |
| Legacy/ambiguous, removed, suspended, deleted, inconsistent membership | 404 | None | All Today data |

The client treats the server role as authoritative and defaults to member-level navigation until a valid projection arrives. Existing role checks on every destination remain authoritative; navigation is discovery, never authorization.

## Projection allowlist and denylist

Allowed output fields are `viewer_role`, `lifecycle_state`, one `primary_action_code`, the bounded primary/secondary `code`, `state`, `destination_category`, optional opaque `action_reference`, categorical `recent_changes` with `is_read`, bounded `navigation_categories`, bounded `milestone_codes`, and categorical `refresh_state`.

Denied output includes names, emails, phones, providers, titles, text, timestamps, exact counts, invitation credentials/continuity claims, event/community/account/database/proposal/request/operation IDs, routes containing IDs, named RSVP/interest rosters, hidden events, organizer drafts, recap/proposal/memory content, travel, budgets, payments, notification recipients, redelivery/incident state, and free-form analytics properties.

## Navigation and route-continuity matrix

| Surface | Release 10 behavior |
|---|---|
| `/home` | Default authenticated Today experience |
| `/dashboard` | Compatible Today alias; no stranded saved URL |
| Primary navigation | Small server-selected role/lifecycle catalog |
| `More` | Keyboard/focus/screen-reader accessible disclosure retaining existing modules |
| Dynamic reunion action | Fresh opaque-reference resolution, then existing command/hub/recap/memory route |
| Static action | Existing family activation/access, gathering, proposal, or activity destination |
| Browser/native | React Router history and deep links retained; mobile safe-area behavior unchanged |
| Offline/unavailable | Existing projection stays visible, actions disable offline, retry is explicit; no invented data |

## Recent-change notification matrix

| Source | Existing authorization reused | Projected category |
|---|---|---|
| Published recap | Recipient/audience and visible-event filters | `reunion_recap` |
| Published gathering pulse | Recipient/audience filters | `gathering_pulse` |
| Access/proposal organizer review | Organizer recipient/audience filters | `organizer_review` |
| Own access status | Explicit recipient filter | `family_access` |
| Visible reunion updates | Existing hidden-event exclusion | `gathering_update` |
| Other authorized activity | Existing feed query | `family_update` |

The projection calls the same `notification_query_for_user` used by feed/history/unread/mark-read and adds no weaker query. It returns no more than four category/read booleans. Opening Today never marks a notification read; the existing mark-read endpoint is invoked only by the explicit button.

## Analytics event and property matrix

| Funnel event | Allowed properties |
|---|---|
| Today viewed; primary shown/selected | Bounded `source`, `viewer_role`, `lifecycle_state`, `action_code` |
| Reunion draft saved; first invitation prepared/shared | Bounded source/role only |
| First RSVP received; organizer return after first RSVP | Bounded source/role only |
| Memory contribution completed | Bounded source/role only |
| Family access approved | Existing bounded access categories only |
| Recap viewed | Existing bounded recap categories only |
| Gathering pulse completed | Existing bounded proposal categories only |
| Next private draft started | Bounded source/role only |

All other properties are dropped. IDs, URLs, timestamps, exact counts, content, credentials, and free-form values are rejected. `/home` and `/dashboard` join the sensitive route set: pageview, autocapture, and replay snapshots are dropped, while text and element attributes remain globally masked. No dashboard, production analytics access, or QA-disable switch was added.

## Route and data inventory

| Route | Role | Mutation |
|---|---|---|
| `GET /api/today` | Fresh canonical active member; provisional organizer only | None; snapshot read |
| `GET /api/today/actions/{opaque_reference}` | Same freshly authorized actor | None; snapshot read |
| `POST /api/family-access/confirm` | Own approved request in current active family | Idempotent confirmation timestamp |

Today adds no collection, provider, credential transport, notification writer, background job, migration, or payment path. It reads existing users, communities, events, memories, recaps, proposals/responses/conversions, family-access requests, travel/budget/planning records, and authorized notifications. The one approved-access confirmation field is covered by existing access-request retention and deletion behavior.

## Finding-to-test matrix

| Risk | Verification |
|---|---|
| Priority inversion or unstable tie | Every organizer/member priority pure tests plus real replica-set sequence |
| Stale role/platform-admin bypass | Disposable canonical-role override and inactive/legacy/provisional denial |
| Mixed snapshot during change | Concurrent pulse close/read accepts only complete old/new safe projection |
| Hidden draft/event or named response leak | Disposable hidden-event notification and serialized projection denylist |
| Cross-community action reuse | Same-user fresh resolution and outsider 404 |
| Read mutation or implicit mark-read | Before/after access record plus explicit notification read assertions |
| Navigation regression | Desktop/mobile built-browser role, More, `/dashboard`, deep-link, back/forward, offline checks |
| Analytics leakage | Allowlist rejection and sensitive route pageview/autocapture/snapshot tests |
| Releases 1–9 regression | Full backend/frontend, disposable campaigns, continuity browsers, native builds, and checkout 410 test |

## Verification evidence

All records, sessions, and providers were synthetic/local. No production customer data, provider delivery, invitation incident operation, subscription recovery, deploy, store change, native publication, or merge was performed.

| Campaign | Result |
|---|---|
| Focused Today policy + checkout kill switch | `17 passed` |
| Today analytics Jest suite | `16 passed` |
| Today disposable Mongo snapshot/authorization campaign | `1 passed` |
| Existing reunion security/redelivery/activation/access/recap/proposal disposable campaigns | `8 passed` |
| Built-browser Today desktop/mobile campaign | Passed; role nav, opaque resolution, history, `/dashboard`, explicit mark-read, offline, external isolation |
| Production frontend build and public prerender | Compiled and prerendered successfully |
| Full relevant backend regression | `270 passed` |
| Full frontend Jest regression | `34 passed` |
| Releases 3–9 plus commercial-readiness built-browser campaigns | Passed at desktop/mobile widths with synthetic responses |
| Android debug | Capacitor sync passed; `BUILD SUCCESSFUL` with Java 21 in a disposable copy |
| Unsigned generic iOS device | Capacitor sync passed; `BUILD SUCCEEDED` with signing disabled in a disposable copy |
| OpenAPI inventory | `185` paths and `212` methods; three new paths/methods |
| Compilation, formatting, fatal lint, scans, diff whitespace | Passed |

## Known limitations and deferred work

- Today intentionally summarizes categories rather than family content; users open an existing authorized destination for details.
- Refresh is request-driven. There is no Today websocket, background refresh, notification writer, or offline mutation queue.
- The member fallback opens existing private family activity because `/home` is Today itself.
- Approved-access confirmation records only the applicant timestamp; it does not re-decide access or create a second membership.
- Production analytics evaluation, owner dashboard, pricing/paywall work, incident redelivery, subscription recovery, deploy, merge, and store/native publication remain explicitly out of scope.
