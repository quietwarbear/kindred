# Kindred Growth Audit & Consumer Build Roadmap

**Assessment date:** July 30, 2026

**Product:** heyKindred

**Repository release reviewed:** `quietwarbear/kindred` at `09721332ca4c0d3c1f22aeedec3a9cb4f46540e3`

**Public surfaces reviewed:** `www.heykindred.org`, Apple App Store metadata, Google Play listing, public repository, current production-safe endpoints

## Status update — August 9, 2026

**Every release in the roadmap below has shipped code** (PRs #20–#48 on `quietwarbear/kindred`, merged Jul 30 – Aug 9). Summary against the plan, with evidence:

| Roadmap item | Status | Evidence |
|---|---|---|
| **Release 1 — One coherent activation path** | ✅ Shipped | PR #20 (intent-based activation, no provider detours, no auto-created communities, no subscription routing, privacy-safe funnel events) + PR #44 single-intent front door (Plan / Join / Preserve) |
| **Release 2 — Store and trust correction** | ✅ Code side shipped; console partially verified | PR #21 (store/trust presentation), PR #39 branded **support@heykindred.org mailbox live**, PR #40 honest privacy copy, PR #10 (dead kindred.ubuntumarket.com → heykindred.org; **Play privacy-policy URL updated in console Aug 9**, ahead of the Aug 21 deadline). iOS 3.1.0 was submitted and approved. ⚠️ Still verify in consoles: Play **Data Safety declarations** vs PRIVACY_DATA_MAP.md, and the native portrait screenshot set (ASO plan drafted in PR #38's `docs/ASO_AND_STORE_LISTING.md`). |
| **Release 3 — Organizer command center** | ✅ Shipped | PR #22 |
| **Release 4 — Guest-to-family conversion** | ✅ Shipped | PR #23 (reunion attendee hub, RSVP stays no-account) + PR #26 (organizer-approved guest family access) |
| **Release 5 — Post-reunion continuity** | ✅ Shipped | PR #24 (private memory capsule), PR #27 (recap + next-gathering continuity), PR #28 (gathering proposals) |
| **Release 6 — Monetization experiments (gated)** | 🔶 In progress, gate respected | Activation funnel dashboard (PR #36) provides the measurement gate; billing restore staged fail-closed: catalog reconcile (#46 / Stage 1), web-catalog endpoint (Stage 2), RevenueCat Web SDK purchases (#48, fail-closed). Draft PR #13 (billing recovery) still open. Checkout remains paused per the roadmap's gate. |

**Beyond the roadmap** (same window): unified **Family Today** home (PR #29), Thanksgiving/holiday **pilot track** (readiness #32, consent & cohort management #37, reminder/follow-up loop #34, activation signals + gated delivery + push #33), **iOS push via APNs** (PR #45), invite create+send UX collapsed to one step with real confirmation (#41/#43) and delivery hardening (#42), **Legacy Table continuity** (cross-app recipe delivery, #30/#31 — an acquisition bridge between the two apps), launch runbook + ASO plan + owner-decisions memo (#38).

**Also relevant to Discover/Store stages** (shipped from the sister visibility workstream): prerendered public pages, robots.txt + sitemap.xml on heykindred.org, and Kindred's card on ubuntu-markets.org + the Village Journal.

**Remaining open items from this audit:** (1) Play Data Safety reconciliation — console task, the roadmap's P0; (2) replace store screenshots with the five-frame portrait story; (3) the 12–15 customer interviews before any billing resumption; (4) merge or close draft PR #13.

## Executive verdict

Kindred does not primarily have a feature shortage. It has an acquisition-to-activation coherence problem.

The website now presents a reasonably clear wedge—family-reunion planning that becomes a lasting family archive—but the app-store listings still present Kindred as a broad community operating system for families, churches, fraternities, and intentional communities. The product then gives different first-run experiences to Google, Apple, email, and invited users. Some users face a five-step setup; others are sent toward subscriptions before reaching value; social sign-in can create an empty community automatically.

That combination explains low traction more convincingly than a lack of capabilities:

1. People searching an app store are unlikely to discover or quickly understand Kindred.
2. The listing creative does not look like a polished mobile consumer product.
3. The store trust declarations conflict with the product's documented data flows.
4. The first-run journey does not consistently deliver the promise made on the website.
5. The product exposes its broad architecture before establishing one concrete habit.
6. Current analytics cannot reliably distinguish account creation, empty-community creation, meaningful activation, and retained use.

**Product-market-fit assessment:** not established. The reunion wedge is credible and substantially stronger than the previous broad positioning, but public traction and the current activation system do not yet demonstrate repeatable acquisition, activation, retention, referral, or willingness to pay.

**Recommended strategic focus:** make Kindred the best private, multigenerational reunion workspace first. Let the larger community platform emerge after a family has planned, attended, and preserved one meaningful gathering.

## What Kindred actually does

The implemented product is a private community platform with:

- reunion and gathering planning;
- no-account invitation RSVP;
- multiday itineraries and activity-level RSVP;
- roles, checklists, potluck, volunteers, travel, and reminders;
- community spaces, announcements, chats, polls, care, and activity;
- memories, voice notes, oral histories, timelines, and legacy threads;
- kinship relationships;
- contribution and budget records;
- Apple, Google, email, and invitation-based account paths;
- multi-community and cross-product handoff capabilities.

This is much broader than the job a new consumer arrives to complete. The strongest entry job is:

> “Help me organize our reunion without losing details in group chats, then preserve the stories and relationships that made it matter.”

The current public website communicates that job better than the stores or signed-in product.

## Ten-second positioning test

### Website

The current homepage passes a basic ten-second comprehension test:

> “Plan the reunion. Bring everyone in. Keep the stories.”

It names the audience, job, and emotional continuation. It also reduces risk by allowing a draft and preview before account creation.

### App stores

The store funnel fails the same test. The description opens with four audiences and expands into a large catalog of gatherings, archives, kinship, contributions, polls, courtyards, communications, privacy, multi-community support, and subscriptions. A consumer must infer which problem to solve first.

The result is category ambiguity:

- Apple category: Social Networking
- Google Play category: Events
- Website position: reunion-first family coordination and memory
- Product architecture: private community operating system

The consumer should not have to reconcile four product categories before installing.

## Severity-ranked findings

### P0 — Google Play data-safety declaration conflicts with documented product behavior

**Public evidence:** Google Play currently states “No data collected.”
**Repository evidence:** `docs/PRIVACY_DATA_MAP.md` documents account identity, profiles, community membership, events, RSVPs, media, voice notes, AI-provider flows, contribution records, subscription data, push tokens, email, Google analytics, PostHog analytics, support requests, SSO handoff, and hosting logs.

**Impact:**

- material consumer-trust risk;
- potential store-policy and disclosure risk;
- creates a contradiction between privacy marketing and actual operation;
- makes future paid acquisition unsafe to scale.

**Required action:** reconcile Google Play Data Safety and Apple App Privacy declarations against the current data map before growth campaigns or listing experiments. This is a console declaration task, not a feature-development task. Legal review may be appropriate; the engineering map explicitly does not constitute legal advice.

### P0 — First-time activation differs by authentication provider

**Evidence:**

- `frontend/src/App.js:47-53` requires onboarding only when `auth_provider === "google"`.
- `backend/routes/auth.py:161-234` sets `onboarding_completed: false` for newly created Google and Apple social users.
- `frontend/src/components/AuthPage.jsx:80-99` routes ordinary authentication toward `/subscription`.

**Failure condition:**

- A new Google user is intercepted and forced through `/welcome`.
- A new Apple user has the same incomplete onboarding state but bypasses `/welcome`.
- A normal Apple or email user can encounter subscription choice before completing a meaningful product action.

**Impact:** inconsistent first value, harder support, unusable funnel comparisons, and provider-dependent activation.

**Required action:** replace provider-specific onboarding with intent-specific activation. The relevant distinction is organizer, invited member, and RSVP guest—not Google versus Apple.

### P0 — New users are exposed to monetization before demonstrated value

**Evidence:** `frontend/src/components/AuthPage.jsx:80-99` navigates non-guest, non-reunion authentication to `/subscription`. Production web subscription checkout intentionally returns HTTP 410 with `subscription_checkout_migrating`.

**Impact:**

- a first-time consumer encounters pricing before completing a reunion, invitation, or RSVP loop;
- the destination contains a disabled purchase path;
- the experience suggests the product is asking for money before proving usefulness.

**Required action:** route new organizers to a single activation workspace and defer plan presentation until a meaningful threshold—such as a saved reunion plus first invitation or a capacity boundary.

### P0 — Store creative is not credible mobile acquisition creative

**Public evidence:** Google Play currently presents four wide desktop-style screenshots. The screenshots contain very small interface text, demo/reviewer identity, and an “Emergent” watermark. They do not show a consumer moving through a mobile reunion journey.

**Impact:**

- poor store-page comprehension on phones;
- weak perceived product maturity;
- no emotional before/after story;
- no evidence of the strongest differentiators: no-account RSVP, multiday itinerary, potluck, volunteer coordination, or memory capture.

**Required action:** replace the listing set with native portrait creative organized as a six-frame story:

1. Plan the reunion in minutes.
2. Share one private link—no app required to RSVP.
3. See who is coming and what still needs attention.
4. Coordinate the itinerary, potluck, volunteers, and travel.
5. Capture photos, voices, and family stories.
6. Keep the family space alive after everyone goes home.

### P1 — Social sign-in creates product state before intent is established

**Evidence:** `backend/routes/auth.py:180-233` creates a new community and host user when no pending email invitation matches, naming it from the user's first name.

**Impact:**

- accidental and empty communities;
- “community created” is not a meaningful activation metric;
- users who intended to explore or join later become hosts of an empty space;
- abandoned state complicates lifecycle messaging and data retention.

**Required action:** create the account first, then create a community only when the user confirms organizer intent or saves a complete reunion draft. Invitation intent should join the intended community without creating a fallback circle.

### P1 — Onboarding is architecture-first rather than outcome-first

**Evidence:** `frontend/src/components/OnboardingPage.jsx:11-34` defines five steps—Profile, Circle, Subyard, Gathering, Invites—with fields for profile, community identity, subyard, gathering, and invite emails. Most fields are optional in `backend/models.py:107-123`, but the interface still requires traversing every step.

**Impact:**

- users learn Kindred's internal nouns before experiencing value;
- “Subyard” is introduced before the need for a planning team is felt;
- optional fields create visible work without a clear payoff;
- invited members and organizers have different jobs but share the same conceptual structure.

**Required action:** reduce organizer activation to:

1. Name/date/location/timezone.
2. Preview the family invitation.
3. Save.
4. Share the first invitation.

Profile, team structure, modules, and permanent community identity should be progressive enhancements.

### P1 — The signed-in product exposes too much surface area too early

**Evidence:** `frontend/src/components/layout/AppShell.jsx:38-52` defines 15 primary navigation destinations before module filtering. `frontend/src/components/HomePage.jsx:41-219` combines metrics, gatherings, courtyards, quick actions, cross-product handoff, notifications, and role tooling.

**Impact:** a new user sees the breadth of a community operating system before understanding the next action. Empty-state volume can make a capable product feel inactive.

**Required action:** create a reunion-focused “Today” experience with one dominant action and progressively reveal the broader system:

- Organizer: finish setup, invite family, resolve missing responses, complete next planning task.
- Invitee: RSVP, answer requested details, view itinerary, contribute one item or story.
- Returning family member: see the next gathering update or memory prompt.

### P1 — Store messaging and website messaging describe different products

**Public evidence:**

- Website: reunion-first, multigenerational-family positioning.
- Store: broad private infrastructure for families, churches, fraternities, and intentional communities.
- Store screenshots: older broad platform and desktop interface.

**Impact:** campaign, store, install, and activation expectations do not form one narrative.

**Required action:** carry the reunion wedge through title/subtitle, first three screenshots, short description, onboarding, home screen, lifecycle messages, and measurement.

### P1 — Public support identity is fragmented

**Public evidence:** Google Play links its website to an Ubuntu Village domain and lists `collective@ubuntu-village.org`, while the product's canonical domain is `heykindred.org`. The repository's privacy map also flags the absence of a confirmed branded support mailbox.

**Impact:** reduced confidence during installation, support, privacy requests, and billing questions.

**Required action:** verify a functioning branded mailbox, then align website, stores, privacy, support, and provider identities. Do not publish an unverified mailbox.

### P1 — The growth funnel is only partially measurable

**Evidence:** `frontend/src/lib/analytics.js` defines a privacy-constrained reunion event vocabulary, but there is no explicit event model for:

- authentication method started/completed/failed;
- organizer versus invited-member intent;
- onboarding step exposure/completion/skip;
- time to saved reunion;
- time to first invitation;
- delivery-channel success;
- first RSVP received;
- organizer return after first RSVP;
- post-event memory contribution;
- retained active family at 7, 30, and 90 days.

Autocapture cannot substitute for a stable, privacy-reviewed funnel definition.

**Impact:** the team cannot determine whether acquisition, account creation, invitation delivery, guest response, organizer return, or post-event continuity is the dominant constraint.

**Required action:** add a small aggregate-only funnel schema with no names, emails, titles, credentials, event IDs, community IDs, message text, or provider payloads.

### P2 — The brand name is highly contested in app-store search

Public search results include unrelated Kindred products for home exchange, communities, relationships, mental health, fanfiction, personal networking, and other categories.

**Impact:** low branded discoverability and high category confusion.

**Required action:** consistently use “heyKindred” plus a descriptive subtitle. Own a narrow semantic phrase such as “Family Reunion Planner” rather than attempting to rank for “community platform.”

### P2 — Pricing may not match the episodic reunion job

The public plans are recurring, member-capacity subscriptions. A reunion organizer may perceive the job as seasonal or event-based even if the archive has long-term value.

**Limitation:** no validated willingness-to-pay research or cohort behavior was available, and subscription recovery remains intentionally paused.

**Required action:** do not change billing yet. Test the value model through interviews and non-purchasing concept tests:

- annual family home;
- per-reunion organizer pass;
- free coordination with paid archive/continuity;
- organization-sponsored access.

## Complete funnel diagnosis

| Stage | Current condition | Principal risk | Recommended measure |
|---|---|---|---|
| Discover | Crowded “Kindred” name; broad metadata | User never finds the right app | Store impressions by query and source |
| Store view | Desktop screenshots and broad feature catalog | User cannot see immediate value | Product-page conversion |
| Install/open | Website/store promise diverges | Expectation mismatch | First open to reunion-start rate |
| Account | Provider-dependent path | Incomparable and inconsistent experience | Auth completion by intent and provider |
| First value | Five-step setup or subscription route | User leaves before useful output | Median time to invitation preview |
| Activation | Empty community can exist without action | False-positive activation | Saved reunion + first invitation |
| Invite | Private-link workflow is strong | Delivery and share channel may fail | Invitations successfully shared/delivered |
| Guest response | No-account RSVP is strong | Guest may not understand next benefit | Invitation open to RSVP completion |
| Organizer return | Operational dashboard is broad | No single next task | Return after first RSVP |
| Event habit | Itinerary and coordination are differentiated | Use may stop after the event | Weekly active organizers during planning |
| Continuity | Memory and legacy are differentiated | Post-event value is not foregrounded | Families with a memory contribution after event |
| Referral | Invitations create distribution | Guest-to-organizer loop is weak | New organizer starts from guest flow |
| Revenue | Web checkout paused; PMF unproven | Monetizing before activation | Activated families reaching plan boundary |

## Competitive reality

Kindred is not competing against an empty market:

- WhatsApp already supports groups, Communities, events, reminders, files, media, and calls.
- Facebook Groups supports private groups, events, chats, files, polls, and admin tooling.
- Partiful markets free, fast invitation pages, no-paywall event creation, RSVP questions, text updates, and payments.
- New reunion-specific products are positioning around schedules, RSVP, payments, potluck, budgets, lodging, and family stories.

Kindred should not claim victory by having more modules. Its defensible consumer story is the combination of:

- no-account participation for relatives who will not install another app;
- structured, multiday reunion operations;
- privacy designed for known circles;
- family roles and relationships;
- continuity from planning into stories, voices, and a living archive.

The message is not “replace WhatsApp.” It is:

> Keep chatting wherever your family already chats. Use Kindred as the private source of truth for the reunion—and the place the memories remain.

## Recommended product architecture

### Acquisition wedge

Family reunion organizers, especially multigenerational and diaspora families coordinating across households and regions.

### Core activation event

An organizer saves a valid reunion and successfully shares or delivers at least one invitation.

### First reciprocal value

The organizer receives the first RSVP or planning contribution.

### Retention event

The family returns for itinerary coordination before the reunion and contributes at least one photo, voice note, or story during or after it.

### Expansion path

Only after the first reunion:

- invite the planning team;
- establish family roles and relationships;
- create focused subyards;
- activate broader community modules;
- plan the next gathering;
- maintain the archive year-round.

## Prioritized consumer build roadmap

### Release 1 — One coherent activation path

**Goal:** every new organizer reaches a saved reunion and invitation preview without provider-specific detours.

- Replace Google-only onboarding gating with intent-based activation.
- Stop routing first-time users to subscriptions.
- Do not auto-create an empty community from social sign-in.
- Preserve and resume the public reunion draft after any authentication method.
- Make organizer, invited member, and RSVP guest explicit states.
- Add “continue later” without creating false activation.
- Define activation as saved reunion plus first invitation, not account/community creation.
- Add privacy-safe funnel events.

### Release 2 — Store and trust correction

**Goal:** make the acquisition surface truthful, focused, and mobile-native.

- Correct store privacy declarations.
- Replace Google Play screenshots and add a complete Apple screenshot set.
- Align title/subtitle/short description around family reunion planning.
- Remove demo identity, reviewer labels, watermarks, and desktop framing.
- Align support website and verified support identity.
- Reconcile website, store, and in-product claims.

### Release 3 — Organizer command center

**Goal:** create a repeatable planning habit.

- One next-best action.
- Response gaps and approaching deadlines.
- Share/remind controls with safe delivery status.
- Planning team invitation.
- Itinerary, potluck, volunteer, travel, and budget progress.
- Clear separation between private organizer data and guest-visible information.

### Release 4 — Guest-to-family-member conversion

**Goal:** turn successful RSVP participation into an optional, understandable account benefit.

- RSVP remains no-account.
- After completion, show concrete benefits: itinerary updates, assigned contribution, family photos, and story prompts.
- Never block RSVP behind installation or account creation.
- Preserve the same invitation confidentiality boundary.

### Release 5 — Post-reunion continuity

**Goal:** prove Kindred is more than event software.

- Event-day story and photo prompts.
- Organizer-selected memory prompts.
- Post-event recap and archive invitation.
- “Plan the next gathering” from the completed reunion.
- Family-controlled continuity, export, and deletion.

### Release 6 — Monetization experiments

**Gate:** only after activation and early retention are measurable.

- Test value framing before resuming checkout.
- Keep the subscription safety pause until its separate recovery requirements are complete.
- Measure conversion at meaningful boundaries rather than exposing plans on first login.

## First implementation slice

The first code change should not be a visual redesign. It should be an **activation-path unification release** with these acceptance criteria:

1. Google, Apple, and email organizers resume the same reunion draft after authentication.
2. No authentication provider receives a special onboarding requirement.
3. No new user is sent to subscriptions before first value.
4. Social sign-in alone does not create an empty community.
5. Invited users join the intended community without falling into organizer setup.
6. RSVP guests can respond without an account.
7. A community is created only through confirmed organizer intent.
8. The core activation event is recorded only after a reunion is saved and an invitation is created.
9. Analytics remain aggregate-only and contain no personal or invitation data.
10. Existing RSVP confidentiality, concurrency, service-worker, provider, and subscription kill-switch safeguards remain unchanged.

## Research required before monetization

Conduct 12–15 interviews across:

- experienced family-reunion organizers;
- first-time organizers;
- relatives who avoid installing apps;
- planning-committee members;
- family historians or elders;
- organizers coordinating travel across regions.

Questions should establish:

- current tool stack and where information breaks;
- the hardest recurring coordination task;
- who controls the guest list;
- how reminders are sent;
- how contributions and payments are handled;
- what relatives refuse to install or share;
- what survives after the reunion;
- whether the family values an annual home or only an event workspace;
- who would pay and from which budget.

Do not lead with Kindred's module names. Ask participants to show their current process.

## Immediate decision

Proceed with the activation-path unification release before adding broader consumer features.

In parallel, correct the app-store privacy declarations and replace the listing creative. Those two workstreams address the largest present barriers:

- people do not understand or trust the product enough to install;
- people who do install do not receive one consistent route to first value.

## Sources and limitations

Public sources:

- [Kindred website](https://www.heykindred.org/)
- [Google Play listing](https://play.google.com/store/apps/details?id=com.ubuntumarket.kindred)
- [Apple App Store listing](https://apps.apple.com/us/app/heykindred/id6760608478)
- [Partiful product site](https://info.partiful.com/)
- [WhatsApp Communities and events](https://about.fb.com/news/2024/05/events-in-whatsapp-communities/)
- [Facebook Groups features](https://www.facebook.com/help/messenger-app/166599882185672)

Limitations:

- No real customer records, invitation records, analytics identities, provider payloads, or production database records were accessed.
- No live email, invitation rotation, subscription action, or customer communication was performed.
- Private store-console acquisition metrics, retention cohorts, search-term reports, and RevenueCat conversion data were not accessed.
- Public download/rating indicators are directional and can lag store-console data.
- Pricing recommendations remain hypotheses until customer research and activation data exist.
