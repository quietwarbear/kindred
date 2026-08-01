# Release 15 — Reminder and follow-up loop

## Release boundary

- Baseline: `f249ef6` (origin/main, the merge of Release 14 / PR #33).
- Branch: `agent/release-15-reminder-followup`. Draft, unmerged, undeployed.
- Production data, customer records, live providers, invitations, messages,
  configuration, deployments, and store listings: not accessed or changed.
- Subscription recovery remains paused; checkout HTTP 410 unchanged. Legacy Table
  delivery remains governed by Stage 12B and is untouched.
- No live email or push was sent. Reminder delivery and every push trigger are
  disabled by default and inert until an owner enables and configures them.

## Why this release exists

Release 14 made activation measurable and built gated first-send + push. Two
gaps remained in the pilot's follow-up story: `send_gathering_reminders` only
labeled records (`reminder_delivery_status = "email-ready"`) and never actually
sent, and the push send path had only one trigger. Release 15 closes the loop —
still under the content-free privacy contract (only categorical codes, booleans,
opaque ids, and bounded counts leave a module).

## What ships

### Gated reminder delivery (disabled by default)

`send_reminders` (`invitation_delivery.py`) reuses the same reviewed Resend
provider, opaque-`target_id` envelope, signed-webhook contract, and revision-safe
CAS stamping as first-send. It:

- targets only invites that are **active, still unanswered, and not already
  reminded today** (a per-day bucket + a per-day idempotency key dedupe rapid
  re-triggers); responded/already-reminded invites are counted as `skipped`;
- stamps `reminder_sent_at` / `last_reminder_bucket` / `reminder_delivery_status`
  through `compare_and_swap_event`, so a concurrent RSVP cannot erase them;
- records a `kind: "reminder"` outbox row, and delivery is confirmed only by the
  signed provider callback, which now stamps `reminder_delivered_at` (never the
  first-send `delivered_at`);
- fails closed unless `INVITATION_REMINDERS_ENABLED=true` AND the provider is
  configured AND preflight passes.

The existing `POST /gatherings/{id}/send-reminders` endpoint keeps its prepare
behavior and now, when enabled, performs the gated send and returns content-free
`delivery` counts.

### Follow-up nudge (active)

`build_holiday_pilot_readiness` adds a bounded `invitations_awaiting_response`
count — invites demonstrably reached (shared/opened/delivered) but still pending
— and sets `next_action_code` to `send_reminders` when any exist. The organizer
panel renders a content-free "N reached but haven't answered" nudge.

### Push triggers (disabled by default)

`push_sender.notify_community` sends an allowlisted content-free template to a
community's members who registered a device, bounded (`recipient_cap`), gated,
best-effort, and excluding the actor. Wired at three content-free points, each a
no-op when push is disabled and each unable to raise into its request:

- new (non-hidden, non-draft) gathering created → `new_gathering` to the community;
- surprise gathering revealed → `gathering_revealed` to the community;
- a reminder sent → `gathering_reminder` to the reminded member's own devices;
- a public-link RSVP received → `rsvp_received` to the organizer (extends the
  Release 14 authenticated-RSVP trigger to the guest path).

## Continuity preserved

- First-send delivery, activation signals, and `opened_at` stamping are unchanged
  except that first-send outbox rows now carry `kind: "first_send"`.
- The delivery callback remains monotonic, idempotent, and revision-safe; a
  duplicate callback is a no-op and a lost race returns `conflict` → webhook 503.
- Subscription HTTP 410, RevenueCat, Stripe, Apple, Google, and Legacy Table are
  untouched.

## Verification evidence

- Release 15 focused backend tests: **12 passed** plus **1 disposable-DB proof**
  (reminder stamp survives a concurrent RSVP, run against a throwaway replica set).
- Disposable campaigns re-run on the replica set (each in its own process):
  Release 15 reminder concurrency, Release 14 both concurrency proofs, and
  Release 13 publish concurrency — all pass, no regression.
- Offline backend selection: **362 passed** vs **311 baseline** — same 52
  environment-gated live-API failures and 206 collection errors on both, so this
  branch adds passing tests with zero new failures or errors.
- Frontend Jest: **44 passed** (7 suites, +1 for the awaiting-response helper);
  production build compiles.
- `black 26.1.0` + fatal `flake8` clean on all changed/new backend files;
  `py_compile` and `import server` (229 routes) pass.

## Activation configuration (required before anything sends)

Names only. All unset by default, keeping every path inert.

- Reminder delivery: `INVITATION_REMINDERS_ENABLED`, plus the same provider
  config as first-send (`RESEND_API_KEY`, `INVITATION_FROM_ADDRESS`,
  `INVITATION_VERIFIED_DOMAIN`, `INVITATION_FIRST_SEND_WEBHOOK_SECRET`).
- Push triggers: `PUSH_NOTIFICATIONS_ENABLED` + an FCM service account
  (`FCM_SERVICE_ACCOUNT_JSON`, or `FCM_PROJECT_ID`/`FCM_CLIENT_EMAIL`/`FCM_PRIVATE_KEY`).

## Verdict

The follow-up nudge (Tier-1-style) is ready for review and makes the pilot's
"who hasn't answered" story actionable without weakening privacy. Reminder
delivery and the push triggers are draft capabilities: inert until an owner
configures them, and — like every prior delivery/push change — subject to an
independent adversarial review before activation. This branch authorizes no real
send, push, message, provider call, subscription change, or store publication.
