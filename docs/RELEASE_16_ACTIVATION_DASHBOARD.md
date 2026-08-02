# Release 16 — Organizer activation dashboard

## Release boundary

- Stacked on Release 15 (`agent/release-15-reminder-followup`), since it surfaces
  R15's `invitations_awaiting_response` signal and reminder next-action. **Merge
  after R15 (PR #34).**
- Mostly frontend. The only backend change is two additional **content-free,
  bounded** readiness counts (`invitations_reached`, `invitations_seen`) that make
  the funnel monotonic; no new endpoint, no data model change.
- Draft, unmerged, undeployed. No production data, provider, or configuration
  touched.

## Why this release exists

Releases 14 and 15 produced the activation signals (prepared / shared / opened /
delivered / responded / awaiting) and a next-best-action code, but the organizer
only saw them as a flat row of numbers. Release 16 turns them into an
at-a-glance **funnel** so an organizer can see, in one look, where people are
dropping off and what to do next.

## What ships

- **`lib/activationFunnel.js`** — `buildActivationFunnel(counts, nextActionCode)`,
  a pure function that structures the readiness aggregate counts into an ordered
  funnel (Prepared → Shared → Opened → Responded) with a bar percentage for each
  stage (a ratio of bounded counts, clamped so no bar exceeds 100%), plus the
  `awaiting` count and a friendly `nextAction` label. `NEXT_ACTION_LABELS` maps
  each categorical backend next-action code to organizer-facing wording, with a
  safe fallback.
- **`components/gatherings/ActivationFunnel.jsx`** — a presentational funnel: one
  bar per stage with its count and percentage, an "reached but not answered"
  highlight when `awaiting > 0`, a "next best step" chip, and a graceful empty
  state before any invitations exist. It renders **only bounded integer counts
  and static labels** — never a name, contact, or link.
- Wired into `HolidayPilotReadiness`, replacing the previous flat activation grid
  and the awaiting nudge with the richer funnel (no information lost — shared,
  opened, responded, and awaiting are all still shown).

## Privacy

The funnel reads exactly two things from the readiness signal:
`aggregate_counts` (bounded integers, capped at 10,000 by the backend) and
`next_action_code` (a categorical string). No per-person field, invite record,
email, name, or link is ever read or rendered. The content-free contract holds by
construction.

## Independent adversarial review (completed)

A focused reviewer probed the content-free guarantee and the funnel math.
Content-free, graceful degradation, and label mapping were **clean**. It found —
and this release fixes — two real issues:

1. **MEDIUM — non-monotonic funnel.** Because `_was_shared` needs a manual
   share/copy while `_was_opened` needs only `opened_at`, an emailed-and-opened
   (never-manually-shared) invite made "Opened" exceed "Shared" — nonsense for a
   funnel. **Fix:** the stages are now **nested-by-construction** on the server
   (Prepared ≥ Reached ≥ Opened ≥ Responded) via the new `invitations_reached` /
   `invitations_seen` counts, with a test asserting the stages never invert.
2. **LOW/MEDIUM — the `delivered` count vanished from the UI.** The old grid
   showed it; the first funnel computed but never rendered it. **Fix:** a "Of
   those reached: N delivered by email, M shared by you" line restores it.

Also addressed: added `role="progressbar"` + ARIA values to the bars (a11y nit).

## Verification

- Backend: **33 passed** across the readiness suites, including 2 new Release 16
  tests (funnel-count monotonicity and content-free counts). `black` + fatal
  `flake8` clean.
- Frontend Jest: **48 passed** (8 suites), including the `activationFunnel` tests
  (monotonic ordering + percentages, empty state, defensive clamping, unknown
  action-code fallback) and the updated summary tests.
- Production build compiles.

## Verdict

Ready for review. It makes the existing activation signals actionable for
organizers without adding any new data surface, and stays strictly within the
content-free privacy contract. Merge after Release 15.
