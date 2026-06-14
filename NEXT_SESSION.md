# Kindred — Next Session Handoff

*Written 2026-06-14 at the end of a long build session. Open this first; it picks up
exactly where we left off. Companion docs: `KINDRED_VISION_PLAN.md` (the phased
blueprint), `QUICK_WINS_BACKLOG.md` (the 30–60 day list, now mostly done).*

## What shipped this session (all pushed to origin/main unless noted)

- **Product evaluation brief** (`Kindred_Product_Evaluation_and_Vision_Brief.docx`) +
  the repo blueprint + quick-wins backlog. *(Docs still UNTRACKED — see hygiene.)*
- **Quick wins:** QW-1 glyphs (already fine), QW-2 dashboard empty-state CTA (HomePage),
  QW-3 weekly digest (idempotent `/api/digest/cron` + one-click unsubscribe),
  QW-4 elder no-install RSVP (`/rsvp/:token` + "Copy RSVP link"), QW-5 Legacy Threads
  prompts, QW-6 pulse (already there).
- **Phase 2 — Ubuntu AI Guide v1:** `ai_steward.py` + `GET /api/steward/briefing` +
  `StewardPage.jsx` ("Ubuntu Guide" nav).
- **Phase 2 — Kinship Graph v1:** account-linked relationships + `GET /api/kinship/person/{id}`
  + tappable nodes / person panel in `KinshipMapPage`.
- **Phase 2 — Living Memory:** `GET /api/memory/search` + Memory Vault search box
  (export already existed at `/api/timeline/export`).
- **Cross-product SSO + recipe sync:** Legacy Table gained `POST /api/auth/exchange`
  (shared-secret single identity); Kindred sends Recipe/Tradition threads to Legacy Table
  authored as the signed-in user — no passwords. First-class **Legacy Table status card**
  + recipe-form hint on `LegacyThreadsPage`.

## STEP 1 — Verify the SSO secret reaches the BACKEND (do this first)

As of session end the Legacy Threads card reads **"Not connected"**, which means the
Kindred backend isn't seeing `UBUNTU_SSO_SECRET` at runtime even though it was set.
- Confirm `UBUNTU_SSO_SECRET` is on the **`backend`** service (the
  `kindred-production-badd…` one), NOT the umbrella/frontend/analytics service.
- Confirm the **same** value is on Legacy Table's **backend** service.
- Redeploy/restart the Kindred backend so it picks up the var.
- Reload Legacy Threads → the card should flip to **Connected**.
- Also set `DIGEST_CRON_KEY` on the Kindred backend (for the weekly digest).
- Reminder: frontend services expose env publicly — keep all secrets (SSO, Stripe `sk_`,
  `whsec_`, Google secret, JWT) on backend services only.

## STEP 2 — End-to-end smoke test on heykindred.org

1. **Ubuntu Guide** → briefing cards render.
2. **Kinship Map** → add a relationship between two members, tap one, person panel shows
   their gatherings/memories/stories.
3. **Memory Vault** → run a search, results return.
4. **Recipe sync (the headline):** create a Recipe/Tradition thread → **Send to Legacy
   Table** → card count ticks up, "Sent to Legacy Table" shows, recipe appears in Legacy
   Table under your account.
5. **Digest:** point a weekly trigger (cron-job.org / Railway cron) at
   `POST /api/digest/cron` with header `X-Digest-Cron-Key: <key>`. Test once with
   `POST /api/digest/send` (organizer) before enabling.

## STEP 3 — Close the loops on what we built (logged as "NEXT" in the vision plan)

- Recipe sync depth: send recipe **photos** (base64) + **structured ingredients** so
  Legacy Table recipes aren't sparse (currently ingredients=[], cook-time/servings=0).
- AI Guide v1.1: organizer **"send this welcome"** action; richer "quiet member" signal
  from RSVP/activity; weave a steward teaser onto the home feed.
- Kinship polish: generation layout + member **avatars** on nodes; reciprocal/auto-inferred
  relationships (parent↔child).

## STEP 4 — Pick the next big rock

- **Extend SSO to Ile Ubuntu** — add the same `/api/auth/exchange` so one identity spans
  all three Ubuntu Markets products.
- **Community Health Dashboard** — the last Phase 2 feature (belonging/participation/
  intergenerational/leadership metrics from existing data).

## Hygiene / open loops (don't lose)

- **Commit the planning docs** — `KINDRED_VISION_PLAN.md`, `QUICK_WINS_BACKLOG.md`,
  `NEXT_SESSION.md`, and the `.docx` brief are UNTRACKED. Add them if you want them in git.
- **Dead code:** `frontend/src/components/DashboardPage.jsx` is unused (the live dashboard
  is `HomePage.jsx`). My QW-2 CTA edits there are inert — revert or delete the file.
- **Digest unsubscribe** is a GET (some mail clients prefetch → accidental opt-out).
  Harden to a confirm-click / `List-Unsubscribe-Post` before any broad send. Add a
  per-user opt-out UI too.
- **Verify the Railway `stripe_key` shared variable** isn't fanned out to the FRONTEND
  service if it's the secret key (`sk_`) — that would publish it. Publishable `pk_` only.
- **Legacy Table**, ideally, should add a real API key / service account so the SSO
  secret isn't the only trust path.
- Multi-channel repo: always `git fetch origin/main` before committing.

## Build/verify conventions used this session

- Backend: `python3 -m py_compile <files>` after edits.
- Frontend: `npx esbuild <file.jsx> --bundle --external:react --external:react-dom
  --external:react-router-dom --external:@/* --format=esm` to parse-check (use
  `--loader:.js=jsx` for `App.js`). NOTE: parse ≠ runtime; still needs a `yarn start`
  eyeball. (Lesson learned: a file can parse fine but be an unmounted/dead component —
  confirm the route/component is actually wired before assuming it ships.)
- Couldn't commit from the build environment (stale `.git/index.lock`); commits/pushes
  were run by Doc locally.
