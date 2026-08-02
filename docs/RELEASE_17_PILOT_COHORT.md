# Release 17 — Pilot consent & cohort management

## Release boundary

- Baseline: `origin/main`. Independent of R15/R16; branches off `main`.
- Draft, unmerged, undeployed. No production data, provider, or configuration
  touched. Recording consent here **enables no delivery, provider call, or send**
  — it is pure bookkeeping.

## Why this release exists

The Release 13 runbook and production launch checklist repeatedly require that a
pilot organizer has *explicitly agreed* to take part before any real event is
created — but that was a manual checkbox in a document. Release 17 turns it into
a recorded, platform-admin-gated state machine on the community, so the cohort
and each community's consent are auditable and can't be inferred.

## What ships

- **`pilot_cohort.py`** — a pure, content-free state machine. Statuses:
  `not_enrolled → enrolled → consented → active → completed`, plus `withdrawn`
  (and re-enroll). `apply_pilot_action` fails closed on any invalid or unknown
  action; `normalize_status` maps any garbage/None to `not_enrolled` (never to a
  permissive state). `pilot_cohort_summary` aggregates counts + the enrolled
  cohort + the not-enrolled communities available to enroll.
- **`routes/pilot.py`** — two **platform-admin-gated** endpoints
  (`GET /api/pilot/cohort`, `POST /api/pilot/cohort/{id}/action`). Recording
  consent requires an explicit `consent_confirmed=true` (enforced server-side, a
  422 otherwise); invalid transitions return 409; the persisted record captures
  the opaque admin id + a consent timestamp.
- **`PilotCohortPage`** (platform-admin only) — enroll a community, then step it
  through the lifecycle with buttons driven by the server's `allowed_actions`.
  Recording consent shows a confirmation making clear it must reflect a real
  out-of-band conversation. Gated by an `adminOnly` nav item, an
  `is_platform_admin` route guard, and a client-side denial fallback — all
  defense-in-depth behind the real backend gate.

## Content-free & side effects

Only categorical status, opaque actor/community ids, an optional short cohort
label, and timestamps are stored. The admin cohort view includes community
id/name (the authorized platform admin legitimately needs them) and never any
member, email, or event content; nothing is logged. Enrolling / consenting /
activating triggers no invitation delivery, push, email, or subscription change.

## Independent adversarial review (completed)

The reviewer confirmed the state machine sound, consent enforced server-side, and
the endpoints side-effect-free — and refuted the authorization claim, which this
release fixes:

1. **HIGH — the admin gate was effectively deny-all.** `_require_admin` keyed off
   `current_user["is_platform_admin"]`, but `get_current_user` returns the raw
   user document and never populates that field (it's derived only at login in
   `build_auth_response` from `PLATFORM_ADMIN_EMAIL`). So every request — including
   the real admin's — got 403; the feature was unreachable, and the passing tests
   masked it by injecting the flag. **Fix:** a shared `is_platform_admin_user`
   helper re-derives admin authority server-side from `PLATFORM_ADMIN_EMAIL`
   against the user's email (never a stored/payload flag, so a forged flag can't
   escalate); both `_require_admin` and `build_auth_response` use it, and a test
   asserts a forged `is_platform_admin` with the wrong email is still denied. The
   **same latent pattern in `digest.py`'s `run-all`** endpoint is fixed with the
   same helper.
2. **LOW — stale consent flag.** `consented_at` wasn't cleared on withdraw/
   re-enroll, so `consented` read true after re-enrollment. **Fix:** enrolling
   clears prior consent/withdrawal fields; a test asserts a re-enrolled community
   reports `consented: false`.
3. **LOW — lost-update race.** The whole-`pilot` write had no concurrency guard.
   **Fix:** the update is now guarded on the status we read (optimistic
   concurrency) and returns 409 `concurrent_pilot_conflict` if it changed under us.

Confirmed clean: state-machine soundness (terminal states immutable, garbage
normalizes to least-privileged `not_enrolled`), server-side consent enforcement,
no logging, internal actor ids stripped from responses, and no send/provider/
feature-enable side effects.

## Verification

- Backend: **15 Release 17 tests** (state machine, invalid/unknown transitions,
  `allowed_actions`, content-free summary, admin gating incl. forged-flag denial
  + real-admin authorized, consent-confirmation required, invalid-transition 409,
  persisted categorical record, 404, re-enroll clears consent, status-guarded
  concurrency conflict).
- Offline backend selection: **365 passed** vs the same environmental baseline —
  zero new failures/errors. `black` + fatal `flake8` clean; `server` imports.
- Frontend Jest: **47 passed** (8 suites, +4 `pilotCohort` label tests);
  production build compiles.
- Independent adversarial review: authorization, state-machine soundness,
  consent integrity, content-free, and side-effect freedom (see review record).

## Verdict

Ready for review. It makes the pilot's consent requirement a real, gated,
auditable record instead of a runbook checkbox, without adding any customer-data
surface or enabling any send.
