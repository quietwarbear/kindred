# Kindred — Product Vision & Build Blueprint

*Prepared 2026-06-13 from a full product evaluation (codebase + live site + 10-competitor
analysis). This is the engineering-facing companion to the strategy brief
(`Kindred_Product_Evaluation_and_Vision_Brief.docx`). It mirrors the
`VILLAGE_MIGRATION_PLAN.md` format from ile_ubuntu: a North Star, phased slices with
crisp scope, the hard-won context that should not be relearned, and the open loops so
nothing falls through. The next build session starts here.*

## North Star

Make **belonging** the primitive, not the feed. Every Kindred surface should answer one
of three questions for a real-world community: *Are we gathering? Are we remembered? Are
we cared for?* Courses, chat, events, and dues are things that happen **inside a living,
multi-generational, member-owned home** — effortless enough for an 80-year-old matriarch,
rich enough for a teenager. The wedge no competitor occupies: **the only place where this
summer's reunion, today's group chat, and grandma's oral history live in the same home.**

## Where Kindred is today (foundation already shipped)

React SPA (PWA + Capacitor iOS/Android) on FastAPI + MongoDB (11 modular route files),
JWT + Google/Apple OAuth, Stripe (web) + RevenueCat (mobile). Live entities: Communities →
Courtyards/Subyards → Gatherings (RSVP, agenda, volunteers, potluck, travel, roles),
Memory Vault (photos + voice + AI tags via litellm/Gemini), Legacy Threads (oral history,
7 categories), Kinship Map (network graph of relationship pairs), Timeline, Polls,
Contributions/Funds, Activity Feed, Announcements, Chat. Five tiers named for growing
trees: Seedling (free/10) → Sapling ($9.99/25) → Oak ($19.99/50) → Redwood ($39.99/100) →
Elder Grove (custom). Role tooling: organizer, treasurer, historian, communications lead,
elder, contributor. Design system: "The Digital Hearth" — Playfair Display + Manrope +
JetBrains Mono, terracotta/bone, warm-organic light / deep-legacy dark.

**Honest assessment in one line:** the *scaffolding* of a belonging platform is built and
broad; the *soul* (memory that compounds, kinship that means something, AI that acts like
a community steward, an onboarding warm enough for elders) is the work ahead.

## Phase 1 — Quick wins (30–60 days)

*High impact, limited engineering. Make the existing product feel finished, warm, and
trustworthy. These are queued as concrete tasks in `QUICK_WINS_BACKLOG.md`.*

1. **Fix the landing page glyphs.** Feature-card icons and the App Store button render as
   missing-glyph boxes (see `kindred_screenshot_1_landing.png`). First impression of a
   trust product; ship a lucide/SVG fix this week.
2. **Empty states that invite, not abandon.** Dashboard shows "Gatherings 0 / Next 3–5
   moments… No gatherings yet." Replace every zero-state with a warm first action
   ("Plant your first gathering", "Record the first story") — this is the onboarding cliff.
3. **Weekly community digest email.** Already in the backlog. The single highest-leverage
   retention lever for multi-gen groups who won't open an app daily. Reuse the ile_ubuntu
   digest patterns (youth/elder sections; village→community).
4. **Elder-friendly onboarding path.** A large-type, low-step "join by invite" flow; SMS/
   email invite that lands on a one-tap RSVP without forcing app install first.
5. **Make Legacy Threads prompt-driven.** Ship the static "elder prompt" rotation (port the
   deterministic-per-day pattern from ile_ubuntu's village home) so the archive fills
   itself: "Ask Grandma about…" cards that turn into voice notes.
6. **Mood/health surface v1 (read-only).** Community Mood Board is in the backlog; ship a
   simple participation + contribution snapshot on the dashboard (no new metrics infra).

## Phase 2 — Mid-term initiatives (3–12 months)

*Major UX and product depth. This is where Kindred stops being "a better group app" and
becomes a community operating system.*

1. **Living Memory System.** 🟡 v1 IN PROGRESS (2026-06-13). Search SHIPPED:
   `GET /api/memory/search?q=` (regex over memory title/description/ai_summary/tags +
   thread title/body/category/elder) with a search bar on `MemoryVaultPage`. Export was
   ALREADY shipped (`/api/timeline/export` → JSON/CSV of memories+threads+gatherings) — the
   member-owned promise is already real. NEXT: video + document media types, attach
   memories to people (kinship) and gatherings, and milestones.
2. **Kinship Map → Kinship Graph.** ✅ v1 SHIPPED 2026-06-13. Relationships now carry real
   member ids (`person_user_id`/`related_to_user_id`) alongside names — backward
   compatible, so legacy name-pair records still render. `/kinship/graph` is account-aware
   (member nodes keyed by `user_id`, navigable); new `GET /kinship/person/{user_id}`
   returns a person's relationships + gatherings + memories + stories (community-scoped,
   read-only). `KinshipMapPage` now picks real members in the add form (free-text
   fallback for non-members) and tapping a node opens that person's story panel.
   NEXT: relationship direction/inference (parent↔child auto-reciprocal), generation
   layout, profile photos on nodes, and wiring this graph into the Legacy Table sync.
3. **Ubuntu AI Guide v1.** ✅ SHIPPED 2026-06-13. `ai_steward.py` (litellm warm-language
   layer + heuristic fallback) + `GET /api/steward/briefing` (`routes/steward.py`) +
   `StewardPage.jsx` at `/steward` ("Ubuntu Guide" nav item). Deterministic signals
   (newest member, quiet members = non-contributors older than 14 days, oldest memory/
   story to resurface, recent gatherings) are computed from real data; the LLM only
   phrases them, so the steward never invents people or events. Read-only — it suggests,
   never acts. Reuses `OPENAI_API_KEY`/`GEMINI_MODEL`; degrades gracefully with no key.
   NEXT: an organizer "send welcome" action, a richer quiet signal from RSVP/activity,
   and weaving the steward card into the home feed.
4. **Community Health Dashboard.** Real metrics that matter more than likes: participation
   breadth, intergenerational interaction, contribution/volunteer engagement, leadership
   development, belonging signals. Share `_compute_dashboard()`-style internals across
   community + courtyard scopes (reuse ile_ubuntu's pattern).
5. **Finish the Legacy Table integration.** 🟡 RECIPE SYNC SHIPPED via Ubuntu Markets SSO
   (2026-06-13). The first real cross-product link: a Recipe/Tradition Legacy Thread can be
   sent to Legacy Table ("where family recipes live forever"), authored by the signed-in
   Kindred user automatically — **no passwords stored or exchanged.**
   **How:** a shared single-identity exchange. Legacy Table gained `POST /api/auth/exchange`
   (server.py) that, given `{email, secret}` matching the shared `UBUNTU_SSO_SECRET`,
   find-or-creates the same-email user and returns a normal LT JWT (mirrors its Google
   flow). Kindred's `legacy_table_sync.py` calls it with the current user's email + secret,
   then POSTs `/api/recipes`. `POST /api/legacy-table/sync-recipe/{thread_id}` maps the
   thread (title→title, body→instructions, elder+community→story) and records the LT recipe
   id on the thread. `LegacyThreadsPage` shows a "your Kindred identity carries over" banner
   + per-recipe "Send to Legacy Table" button (no login form).
   **OPS:** set the SAME `UBUNTU_SSO_SECRET` (long random) in BOTH Railway projects (Kindred
   backend + Legacy Table backend). The secret is server-side only; it can mint an LT
   session for any email, so guard it and have LT trust only products you own.
   **NEXT:** recipe photos (base64), structured ingredients, extend SSO to Ile Ubuntu, and
   sync stories/gatherings the same way.
6. **Pricing & packaging revisit.** Validate the tree tiers against willingness-to-pay for
   non-commercial groups (the white space Mighty/Circle abandon). Consider a
   reunion/seasonal one-time plan and a church-org tier.

## Phase 3 — Long-term vision (1–3 years)

*Transformational. Position Kindred as the leading home for belonging, family continuity,
and cultural preservation.*

1. **Kindred as a Community Operating System.** A configurable home where families,
   churches, fraternities, cultural orgs, and intentional communities each get a tuned
   template (the default-subyard idea, taken all the way) — gathering, memory, kinship,
   care, and contribution as composable modules.
2. **Gathering Intelligence Layer.** AI that plans events end-to-end (volunteers, potluck,
   travel, agenda), generates family/community histories from the accumulated archive,
   and recommends the right engagement to the right person at the right time.
3. **Living oral-history at scale.** Guided multi-generational interview flows, automatic
   transcription/translation (en/es/yo and beyond), and AI-assembled "family chronicles"
   that turn scattered voice notes into a narrated legacy.
4. **Care infrastructure.** Move from coordination to *collective care*: meal trains,
   check-in routing to the right elder/mentor, bereavement and milestone support — the
   "are we cared for?" question, fully answered.
5. **Federation across communities.** Let a fraternity chapter, a family, and a church a
   member belongs to coexist without bleeding data — multi-community identity with
   member-owned boundaries (build on the existing multi-courtyard switcher).

## Hard-won context (carry forward; do not relearn)

*Ported from the ile_ubuntu blueprint where it applies to this shared stack/ops, plus
Kindred-specific findings from this evaluation.*

- **Multi-channel git habit:** fetch `origin/main` before committing — multiple Claude
  channels push to these repos. (Kindred working tree currently has uncommitted
  `version.properties` churn; start from a known state.)
- **Stripe discipline (shared account):** every Stripe call passes `api_key=` per call;
  never set the global. SDK GETs are broken on Railway — use direct `requests` for GETs.
  stripe-python v15 `Webhook.construct_event` returns an Event that is NOT dict-like
  (`.get` → AttributeError): verify signature, then `json.loads` the raw body. Strip
  `' ,\n\t\r'` from every env-read Stripe value (paste artifacts → 401). Each app on the
  shared Stripe account needs its OWN webhook destination + `whsec_` with
  "Events from: Your account" — Kindred will need its own when it goes fully live.
- **RevenueCat (mobile):** subscriptions are dual-rail (Stripe web + RevenueCat native);
  the launch-freeze fix (defer RC init, 8s timeout, skip empty session check) is load-
  bearing — don't undo it. Keep the iOS "Restore Purchases" button (Apple 3.1.1).
- **AI layer:** `ai_tagging.py` uses litellm (Gemini via Emergent LLM key) with a
  heuristic keyword fallback — keep the fallback so tagging degrades gracefully offline.
  AI is currently *only* memory tagging; the steward/intelligence work is greenfield.
- **Frontend lockfiles:** don't add npm deps casually (the ile_ubuntu QR-via-image-API
  rule); keep the bundle lean for native builds.
- **Event/meta privacy:** events are faculty/steward-readable — never put sensitive
  payloads (scores, private notes, health) in event meta.
- **i18n:** add nav keys to all locales or the raw key name leaks into the UI (ile_ubuntu
  ships en/es/yo; Kindred should follow before any nav growth).
- **Capacitor:** native bridge has web fallbacks (camera, push, haptics) — test both paths;
  `test_capacitor_native.py` is the guardrail.

## Open loops (not this slice, but do not lose)

- **Legacy Table sync is a stub.** `legacy-table/status` returns "awaiting API docs or
  credentials." Real cross-product sync is blocked on the sibling product's API. When it
  goes live, the natural FIRST candidates to sync are the `recipe-tradition` and
  `family-lore` Legacy Thread categories (and their voice notes) — durable, heritage-grade
  content that belongs in the Legacy Table archive, not just Kindred's feed.
- **Kinship Map is name-string based, not account-linked.** Graph nodes key on display
  name (`node_map[name]`), so duplicates and ambiguity are possible. Phase 2 item #2
  addresses this; flag any new kinship feature as building on shaky ground until then.
- **Landing-page asset bug** (missing glyphs) is live in production — Phase 1 item #1.
- **Backlog inheritance:** Community Mood Board and weekly digest emails are listed as
  "Remaining Backlog" in `memory/PRD.md`; folded into Phase 1 here.
- **README is a placeholder** ("# Here are your Instructions"). Write a real one when
  touching the repo (engineering:documentation skill).
- **Stripe live-readiness for Kindred** has not been cut over the way ile_ubuntu's
  marketplace was; treat the per-app destination/secret work as pending before charging
  real cards at scale.

## The question this is all answering

> *If the world's strongest communities had a digital home built specifically for
> belonging, memory, kinship, and collective flourishing — what would Kindred become?*

The full answer lives in the strategy brief. The short version: **Kindred becomes the
village's memory and its nervous system at once** — the place a community goes to gather
this week and the place its grandchildren go to remember it in fifty years. *I am because
we are*, made software.
