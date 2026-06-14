# Kindred — Quick Wins Backlog (30–60 days)

*Queued 2026-06-13 from the product evaluation; **updated same day after a code audit
+ first execution pass.** The original list leaned on an April landing/dashboard
screenshot — the live code turned out to be further along than the screenshot implied, so
several items were already done. Status reflects reality as of this session. Fetch
`origin/main` before committing (multi-channel repo).*

## Status at a glance

| # | Quick win | Status | Notes |
|---|-----------|--------|-------|
| QW-1 | Landing-page glyphs | ✅ Already shipped | lucide SVG icons + Apple's official badge already in `LandingPage.jsx`; the two "missing-icons" PRs landed after the screenshot. Nothing to fix. |
| QW-2 | Warm empty states | ✅ Done this session | Copy was already warm; added clickable CTAs to the dashboard empty states. |
| QW-3 | Weekly community digest | ✅ Done this session | Builder + endpoints + idempotent weekly cron hook + one-click unsubscribe. Needs `DIGEST_CRON_KEY` set + a weekly trigger wired + a verification send. |
| QW-4 | Elder no-install RSVP | ✅ Done this session | Public tokenized RSVP endpoint + elder-friendly page + organizer "Copy RSVP link" button. Reachable end-to-end. |
| QW-5 | Prompt-driven Legacy Threads | ✅ Done this session | Daily-rotating elder-prompt strip that pre-fills the new-thread form. |
| QW-6 | Participation snapshot | ✅ Already shipped | `DashboardPage` already renders a 5-stat community-pulse row. Optional: add "active this month" / memory-mood later. |

---

## QW-1 — Fix landing-page missing glyphs  ✅ ALREADY SHIPPED
**Audit result:** `frontend/src/components/LandingPage.jsx` imports real lucide-react icons
(`CalendarDays`, `Camera`, `MessageCircleHeart`, `Coins`) rendered as SVG, and uses
Apple's official `download-on-the-app-store.svg` badge linking to the live App Store
listing. The April screenshot predates the `feature/missing-icons` PRs (#5, #6). No code
change required. *Recommend a live-site spot check to close it out.*

## QW-2 — Warm empty states  ✅ DONE THIS SESSION
**What shipped:** the dashboard empty states already had warm copy but were dead text.
Added a primary CTA link to each — `Plan your first gathering` → `/events`,
`Add the first memory` → `/memories`, `Start a legacy thread` → `/threads` — with the
existing arrow affordance and `data-testid`s (`dashboard-*-empty-cta`).
**Touch points:** `frontend/src/components/DashboardPage.jsx`.
**Done when:** ✅ each empty state offers a one-tap next action. *Verify visually with
`yarn start`.*

## QW-3 — Weekly community digest  ✅ BUILT THIS SESSION
**What shipped:** reused the existing Resend pipeline (`email_service.py`) — added
`build_digest_body()` and `send_community_digest()` (styled with the existing Kindred email
template), plus a new `backend/routes/digest.py` registered in `server.py`:
- `POST /api/digest/preview` (any member) — digest data + rendered HTML, no send.
- `POST /api/digest/send` (organizer+) — send to all members of the caller's community.
- `POST /api/digest/run-all` (platform admin) — send to every community; the scheduler hook.

The digest summarizes the week: member count + new-this-week, upcoming gatherings, newly
added memories/threads, and contributions to date.
**Completed this session:**
- **Idempotent weekly cron hook:** `POST /api/digest/cron` (auth via `X-Digest-Cron-Key`
  header). A per-community `last_digest_sent_at` guard (`DIGEST_MIN_INTERVAL_DAYS = 6`)
  makes any trigger frequency safe — no double-sends. `/run-all` (admin) and `/send`
  (organizer, force) remain.
- **One-click unsubscribe:** per-user `digest_opt_out` + opaque `digest_unsubscribe_token`;
  the digest footer links to `GET /api/public/digest/unsubscribe/{token}` (with a
  re-subscribe link). Opted-out members are skipped on every send.
**To finish wiring (ops, ~2 min):**
1. Set `DIGEST_CRON_KEY` in Railway (any long random string). Until set, `/digest/cron`
   returns 403 — inert and safe.
2. Optionally set `PUBLIC_BACKEND_URL` (unsubscribe-link base; defaults to the Railway URL).
3. Point a weekly trigger (cron-job.org / GitHub Actions / Railway cron) at
   `POST /api/digest/cron` with header `X-Digest-Cron-Key: <key>`.
4. **Verify first:** `POST /api/digest/preview` to eyeball HTML, then `POST /api/digest/send`
   (organizer) to a test community before enabling the cron. Requires `RESEND_API_KEY`.
**Touch points:** `backend/email_service.py`, `backend/routes/digest.py`,
`backend/routes/public.py`, `backend/server.py`.

## QW-4 — Elder-friendly invite + RSVP (no-install path)  🟡 BUILT THIS SESSION (link not yet surfaced)
**Finding that reshaped it:** there was NO public RSVP path — every event route, incl.
`POST /events/{id}/rsvp`, requires `get_current_user` and ties the RSVP to the logged-in
user. So this needed a new unauthenticated endpoint, not a tweak.
**What shipped:**
- `backend/routes/public.py` (registered in `server.py`) — two **no-auth** endpoints keyed
  by the invite's own uuid4 `id` as an unguessable token:
  - `GET /api/public/rsvp/{token}` — minimal gathering + invitee info (title, when, where,
    community name, this invite's name + status). Nothing else exposed.
  - `POST /api/public/rsvp/{token}` — sets the RSVP for that one invite (going/maybe/
    not-going), creates an rsvp_record + flips the invite's rsvp_status. No account.
- `frontend/src/components/PublicRSVPPage.jsx` at route `/rsvp/:token` — elder-friendly:
  large type, few words, three big tap targets, change-anytime, no sign-in. Secondary
  "Get the app" link only.
**Security (reviewed):** no-auth by design; token is uuid4 (122-bit) shown only to the
authed organizer who sends it (Evite-style). GET leaks no member lists/contacts/other
invites; POST mutates only that one invite; status validated via enum; guests clamped ≥0;
no account/permission/payment side effects. Low-risk DoS (idempotent per token).
**Link surfacing — DONE:** `components/gatherings/GatheringInvites.jsx` now shows a
per-invite "Copy RSVP link" button (`{window.location.origin}/rsvp/{invite.id}`) so
organizers can hand the link out. QW-4 is now reachable end-to-end.
**Optional follow-up:** fold the link into the invite `share_message` and the
`event_invites` email body so it travels automatically.
**Nice-to-have:** add a Mongo index on `event_invites.id` if invite volume grows.
**Touch points:** `backend/routes/public.py`, `backend/server.py`,
`frontend/src/components/PublicRSVPPage.jsx`, `frontend/src/App.js`.

## QW-5 — Prompt-driven Legacy Threads ("Ask an elder about…")  ✅ DONE THIS SESSION
**What shipped:** added `ELDER_PROMPTS` (category-aware) and a deterministic daily rotation
(`promptsForToday`) to `LegacyThreadsPage.jsx`. When the form is closed, a three-card
prompt strip ("A prompt to get you started") shows the day's prompts; clicking one opens the
new-thread form pre-filled with the prompt as the title and the right category. Existing
`VoiceRecorder` handles the spoken answer.
**Touch points:** `frontend/src/components/LegacyThreadsPage.jsx`.
**Done when:** ✅ the archive offers a starting point instead of a blank page. *Verify with
`yarn start`.* Future: generate prompts via the Ubuntu Intelligence layer (Phase 2).

## QW-6 — Participation snapshot (Health v1)  ✅ ALREADY SHIPPED
**Audit result:** `DashboardPage` already renders a "Community pulse" row of five stats
(Members, Events, Memories, Threads, Raised) from `/community/overview`. The seed of the
Community Health Dashboard already exists. *Optional enhancement later: add "active members
this month" and a recent-memory mood read from the existing `ai_tagging` sentiment field.*

---

### Session verification notes
- Backend (`server.py`, `email_service.py`, `routes/digest.py`) pass `py_compile`; the
  digest's ISO-timestamp comparison matches `now_iso()` (both timezone-aware ISO strings).
- Edited frontend files (`LegacyThreadsPage.jsx`, `DashboardPage.jsx`) pass an esbuild JSX
  parse. Visual confirmation still needs a local `yarn start` — not runnable in this session.
- Not committed from here (a stale `.git/index.lock` blocks writes in this environment);
  commit locally after the visual check. Remember to fetch `origin/main` first.

### Not in this batch (tracked in KINDRED_VISION_PLAN.md → Phase 2)
Living Memory System, Kinship Graph rebuild, Ubuntu AI Guide, full Community Health
Dashboard, Legacy Table live sync, pricing revisit.
