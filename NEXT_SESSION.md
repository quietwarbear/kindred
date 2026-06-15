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
- **Phase 2 — Community Health Dashboard:** `GET /api/community/health` +
  `HealthDashboardPage.jsx` ("Community Health" nav). Participation, contribution/
  volunteers, leadership, intergenerational proxy, living-record counts. **This completes
  every net-new Phase 2 feature; only #6 pricing remains, and that's a decision, not a build.**
- **Cross-product SSO + recipe sync (debugged + hardened):** Legacy Table gained
  `POST /api/auth/exchange` (shared-secret single identity); Kindred sends Recipe/Tradition
  threads to Legacy Table authored as the signed-in user — no passwords. First-class
  **Legacy Table status card** + recipe-form hint on `LegacyThreadsPage`. **Family mapping
  fix:** LT is family-scoped, so a family-less recipe was invisible; sync now auto-creates a
  LT family named after the Kindred community (`/api/families`) so recipes land in the
  Family Cookbook.
- **Phase 3 — Federation (bi-directional, all three):** `POST /api/auth/exchange` now exists
  in Legacy Table, Ile Ubuntu, AND Kindred (`kindred/backend/routes/auth.py` — find-or-create
  by email, mint Kindred session via `build_auth_response`; new federated user has no
  community → lands in onboarding). The fabric is symmetric: any product can sign a user
  into any other. Kindred's backend already has `UBUNTU_SSO_SECRET`. ⏳ Still set it on Ile
  Ubuntu's **backend** to finish that leg. NEXT: the user-facing "jump" links that USE the
  exchange (e.g., "Open in Legacy Table / Ile Ubuntu / Kindred" lands you signed in).
- **Phase 3 — Surprise Gathering mode + Reveal:** create a gathering hidden from the
  guest(s) of honor; it's suppressed on EVERY surface (events list, single-event fetch,
  dashboard, home, weekly digest per-recipient, steward briefing) and sends no create
  notification. One-tap **Reveal** (`POST /api/events/{id}/reveal`) un-hides + announces it.
  Surprise toggle + guest picker + reveal banner in `GatheringsPage`.

## STEP 1 — Status of SSO / recipe sync (mostly verified)

- ✅ `UBUNTU_SSO_SECRET` is on both backends; Legacy Threads card reads **Connected**.
- ✅ SSO exchange + recipe create confirmed live (a recipe row was created in LT).
- 🐛→✅ Found & fixed the "sent but invisible" bug: LT is **family-scoped**, the first
  synced recipe was family-less so it never showed. Fix deployed — sync now auto-creates a
  LT family named after the Kindred community.
- ⏳ **RE-VERIFY (do first):** send a **new** Recipe/Tradition thread (not the orphaned
  gumbo one) → it should auto-create the "Toure Honor" family and the recipe should appear
  in **Family Cookbook / My Recipes** in Legacy Table. Then the bridge is fully proven.
- Still set `DIGEST_CRON_KEY` on the Kindred backend (for the weekly digest) if not done.
- Cleanup: delete the one orphaned family-less test recipe in LT once verified.
- Reminder: frontend services expose env publicly — keep all secrets (SSO, Stripe `sk_`,
  `whsec_`, Google secret, JWT) on backend services only. SSO unifies by EMAIL — Kindred &
  LT accounts must share an email.

## STEP 2 — End-to-end smoke test on heykindred.org

1. **Ubuntu Guide** → briefing cards render.
2. **Kinship Map** → add a relationship between two members, tap one, person panel shows
   their gatherings/memories/stories.
3. **Memory Vault** → run a search, results return.
4. **Recipe sync (the headline):** see STEP 1 — send a new recipe, confirm it appears in
   the auto-created Family Cookbook in Legacy Table.
5. **Community Health** → open it, confirm the metric cards render.
6. **Digest:** point a weekly trigger (cron-job.org / Railway cron) at
   `POST /api/digest/cron` with header `X-Digest-Cron-Key: <key>`. Test once with
   `POST /api/digest/send` (organizer) before enabling.

## STEP 3 — Close the loops on what we built (logged as "NEXT" in the vision plan)

- Recipe sync depth: send recipe **photos** (base64) + **structured ingredients** so
  Legacy Table recipes aren't sparse (currently ingredients=[], cook-time/servings=0).
- AI Guide v1.1: organizer **"send this welcome"** action; richer "quiet member" signal
  from RSVP/activity; weave a steward teaser onto the home feed.
- Kinship polish: generation layout + member **avatars** on nodes; reciprocal/auto-inferred
  relationships (parent↔child).

## STEP 4 — Phase 2 DONE; Phase 3 STARTED

Phase 2 complete (Living Memory, Kinship Graph, Ubuntu AI Guide, Community Health Dashboard,
Legacy Table recipe sync over SSO). Item #6 (pricing) is a business decision, not a build.

Phase 3 already underway this session:
- ✅ **Federation v1** — `/api/auth/exchange` now in all three products (Kindred, Legacy
  Table, Ile Ubuntu). ⏳ Set `UBUNTU_SSO_SECRET` on Ile Ubuntu's backend to finish.
- ✅ **Care infrastructure (first slice)** — Surprise Gathering mode + Reveal.

Remaining Phase 3 rocks (see KINDRED_VISION_PLAN.md Phase 3):
- **Community Operating System** — per-type configurable templates (extends default subyards).
- **Gathering Intelligence Layer** — AI plans events end-to-end + generates histories
  (extends the Ubuntu AI Guide).
- **Living oral-history at scale** — guided interviews + transcription/translation
  (extends Living Memory + Legacy Threads).
- **Care infrastructure (more)** — meal trains, check-in routing, milestones.
- **Federation (more)** — a user-facing "open in Ile Ubuntu / Legacy Table" cross-product
  jump that uses the exchange; multi-community identity.

Surprise Gathering follow-ups: post-hoc "add a guest of honor" to an existing gathering
(currently set at create only); Reveal exists. Federation follow-up: a Kindred→sibling
"jump" link that calls the exchange so the user lands signed-in.

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
