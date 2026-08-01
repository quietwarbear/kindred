# Release 14 — Privacy-safe activation signals, gated delivery, and push

## Release boundary

- Baseline: `cf5e95e` (origin/main, the merge of Release 13 / PR #32).
- Branch: `agent/release-14-activation-and-delivery`. Draft, unmerged, undeployed.
- Production data, customer records, live providers, invitations, messages,
  configuration, deployments, and store listings: not accessed or changed.
- Subscription recovery remains paused; the checkout HTTP 410 kill switch is
  unchanged. Legacy Table delivery remains governed by the Stage 12B bridge and
  is untouched.
- No live email, push, or provider call was made. Tiers 2 and 3 are disabled by
  default and inert until an owner explicitly configures them.

## Why this release exists

Release 13's pilot state machine advances to `invitations_sent` only when
`_has_delivery_evidence()` sees `shared_at` / `opened_at` / `link_copied_at` /
`delivered_at` on an invitation — but nothing in the codebase ever wrote those
fields, device push tokens were stored yet never sent, and the only invitation
delivery path was the credential-rotation incident pipeline. Activation was
therefore unmeasurable, re-engagement impossible, and first-send manual.

Release 14 closes those gaps while preserving the program's absolute privacy
contract: every new surface emits only categorical codes, booleans, and bounded
integer counts — never names, emails, titles, notes, links, credentials,
message bodies, or provider payloads.

## Tier 1 — Privacy-safe activation signals (active)

- **Organizer signal endpoint.** `POST /api/events/{id}/invites/{invite_id}/activation-signal`
  accepts only an allowlisted categorical `signal` (`shared` | `link_copied`)
  and writes a monotonic first-write-wins `shared_at` / `link_copied_at` on the
  one invitation. Organizer-only; blocked while `publication_state` is
  `organizer_draft`; routed through the RSVP `compare_and_swap_event` so it can
  never clobber a concurrent response.
- **Verifiable-open signal.** A successful header-authenticated public RSVP
  resolve (`GET /api/public/rsvp`) stamps `opened_at` once. A GET here always
  carries the credential in an Authorization header (the token lives in the URL
  fragment and is only promoted to a header by the app), so a link scanner or
  mail-client prefetch of a page URL can never reach it — a resolve is a genuine
  recipient open. Responding also stamps `opened_at` atomically inside the RSVP
  write, so the signal cannot be lost to a race.
- **Aggregate readiness view.** `build_holiday_pilot_readiness` now reports
  bounded, capped `invitations_shared`, `invitations_opened`, and
  `invitations_delivered` counts alongside the existing counts. The organizer
  panel renders a content-free "shared · opened · delivered" row.

## Tier 2 — Gated first-send delivery (disabled by default)

`invitation_delivery.py` composes the reviewed `ResendInvitationDeliveryProvider`
and the signed `verify_resend_delivery_event` webhook contract — it does not
reimplement or modify the credential-rotation system.

- **Fails closed.** `POST /api/events/{id}/invites/send` performs no send unless
  `INVITATION_FIRST_SEND_ENABLED=true` AND the provider is configured AND the
  provider preflight passes. Otherwise it returns a categorical `unavailable`
  status with zero counts. Blocked on `organizer_draft`.
- **The provider never sees a credential.** Each send carries an OPAQUE
  `target_id` (a random hex id), so the provider's sanitized logs cannot leak a
  bearer token. The outbox maps the opaque provider message id to the invitation
  server-side; the recipient's own fragment link is the only place their
  credential appears, in their own email.
- **Delivery confirmed only by signature.** The isolated
  `/api/provider/resend/invitation-first-send` webhook (its own signing secret,
  `INVITATION_FIRST_SEND_WEBHOOK_SECRET`) verifies each callback, discards every
  non-operational field, and stamps `delivered_at` / `delivery_verified_at` once
  (monotonic). Failure events never downgrade a delivered target; unknown
  provider references are ignored.

## Tier 3 — Server push notifications (disabled by default)

`push_sender.py` adds the missing send path for the device tokens already
collected at `/auth/push-token`, using FCM HTTP v1 over the vendored `httpx` and
a service-account JWT signed with the vendored `PyJWT` — **no new dependency**.

- **Fails closed.** Nothing is sent unless `PUSH_NOTIFICATIONS_ENABLED=true` AND
  a service account is configured.
- **Content-free by construction.** Notifications use only an allowlisted
  template table (fixed title/body pairs with no interpolation) — never a name,
  email, event title, or other customer content. Only aggregate categorical
  counts leave the module; tokens, bodies, and credentials are never logged.
- **Self-healing token list.** Tokens FCM reports permanently invalid are pruned
  from the user.
- **One gated trigger.** A member RSVP best-effort notifies the organizer's own
  devices (`rsvp_received`). It is a no-op when push is disabled and swallows any
  failure, so it can never affect the RSVP response. Additional triggers
  (public-link RSVP, reminders, reveal) are deferred behind the same gate.

## Finding-to-test matrix

| Risk | Control | Evidence |
|---|---|---|
| Delivery evidence never recorded | Signal endpoint + resolve stamp write the fields readiness reads | `test_release14_activation_signals` aggregate + stage tests |
| Signal on a private draft | Endpoint blocks `organizer_draft` before any write | draft-blocked unit test |
| Non-organizer records a signal | `ensure_minimum_role(organizer)` | member-denied unit test |
| Signal clobbers a concurrent RSVP | Routed through `compare_and_swap_event` | monotonic unit test + disposable contention campaign |
| Duplicate open/deliver stamps | First-write-wins array filters (`$exists: False`) | opened-once + delivered-once tests |
| Content leaks into aggregates | Counts only, capped at 10,000 | content-free repr assertions |
| First-send active without config | Enable flag + provider preflight both required | disabled/unconfigured endpoint tests |
| Credential in provider logs | Opaque `target_id`; credential only in the recipient's own link | opaque-target test |
| Unsigned/forged delivery callback | `svix` verification via the reviewed webhook contract | isolated webhook route + verified-event tests |
| Failure downgrades a delivered invite | Guarded outbox transition; no invite mutation on failure | failure-never-downgrades test |
| Push carries customer content | Allowlisted fixed templates; unknown template fails closed | content-free template + unknown-template tests |
| Push failure breaks the request | `maybe_notify` gated + exception-swallowed | no-op-when-disabled + swallows-errors tests |
| Dead device tokens accumulate | Invalid tokens pruned via `$pull` | prune-and-count test |

## Verification evidence

- Release 14 focused backend tests: **33 passed** (`test_release14_activation_signals`
  10, `test_release14_invitation_delivery` 13, `test_release14_push_sender` 10).
- Offline backend selection: **344 passed** on this branch vs **311 passed** on
  the untouched baseline — the same 52 environment-gated live-API failures and
  206 collection errors on both (they require `REACT_APP_BACKEND_URL` / a running
  server and were not pointed at production), so this branch adds **+33 passing
  tests and zero new failures or errors**.
- Frontend Jest: **43 passed** (7 suites), including the new activation-summary
  helper (`+2`).
- Optimized frontend production build: compiled successfully.
- `black 26.1.0` formatting and fatal `flake8` (`E9,F63,F7,F82`) on all changed
  and new backend files: passed. `py_compile` and `import server` (229 routes):
  passed.
- **Disposable-MongoDB campaign not run here.** `test_release14_activation_signals_disposable_db`
  (concurrent signal-vs-RSVP survival + `opened_at` first-write-wins) skips
  without a local disposable replica set, exactly as the Release 11/13 disposable
  campaigns document. It refuses any database whose name is not
  `kindred_disposable_*` and any production URL, and must not be pointed at a
  cloud/Atlas cluster. It remains an owner-environment gate.

## Activation configuration (required before Tiers 2/3 do anything)

Names only — no values. All are unset by default, which keeps the features inert.

- Tier 2 first-send: `INVITATION_FIRST_SEND_ENABLED`, `RESEND_API_KEY`,
  `INVITATION_FROM_ADDRESS`, `INVITATION_VERIFIED_DOMAIN`,
  `INVITATION_FIRST_SEND_WEBHOOK_SECRET`.
- Tier 3 push: `PUSH_NOTIFICATIONS_ENABLED`, and either
  `FCM_SERVICE_ACCOUNT_JSON` or `FCM_PROJECT_ID` + `FCM_CLIENT_EMAIL` +
  `FCM_PRIVATE_KEY`.

## Verdict

Tier 1 is ready for review and, after merge and deployment, makes the Release 13
pilot measurable without weakening its privacy contract. Tiers 2 and 3 are draft
capabilities: they stay inert until an owner configures the provider, verified
sender, webhook secret, and/or FCM service account, and — like every prior
delivery change in this program — they must pass an independent adversarial
security review before activation. Green automated checks do not substitute for
that review. This branch authorizes no real dinner, invitation, provider call,
message, push, Legacy Table delivery, subscription change, or store publication.
