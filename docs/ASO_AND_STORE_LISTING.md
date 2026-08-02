# Kindred — ASO & store-listing recommendations

From the growth audit: the app is essentially undiscoverable — titled
"heyKindred" (nobody searches that), in the brutal Social Networking category,
with ~1 rating, and "Kindred" collides with a VC-backed home-swap app plus a
dozen others. Discoverability is the emergency, not positioning. These are the
concrete listing changes to make in App Store Connect and Google Play Console.
All are owner actions (store-console edits + a new build for screenshots).

## The core move: concede the head term, win the long tail

"Kindred" alone is unwinnable (Kindred – Home Swapping owns it, plus Kindred
parenting/fanfiction/credit-union/etc., plus near-name "Kyndred"). Stop competing
for it; rank for what your people actually type.

## iOS (App Store Connect)

- **App name / title (30 chars):** carry the brand *and* the job. Options to
  test: `Kindred: Family & Reunions` · `heyKindred: Private Community`. Lead with
  the recognizable word "Kindred," qualify it so it's not lost in the collision.
- **Subtitle (30 chars) — currently empty, highest-value field:** e.g.
  `Private family & church app` or `Reunions, memories, together`.
- **Keywords (100 chars, comma-separated, no spaces):** target real intent, not
  prose. Draft:
  `family reunion,private community,church app,group events,shared photos,alumni,fraternity,sorority,family tree,rsvp`
- **Category:** keep Social Networking as primary only if forced; consider
  **Lifestyle** as primary (less red-ocean) with Social Networking secondary.
- **Promotional text (170 chars, updatable without a build):** seasonal hook —
  e.g. "Planning a reunion or a holiday gathering? Keep everyone — and every
  photo and story — in one private place."

## Google Play (Play Console)

- **Title (30 chars):** mirror iOS — `Kindred: Family & Reunions`.
- **Short description (80 chars):** `The private, ad-free app to keep your family
  or church together.`
- **Long description:** front-load the real queries (family reunion, private
  group, church community, shared photos, oral history) naturally in the first
  two lines; Play indexes the full description.

## Screenshots & preview (both stores) — needs a new build/capture

The name and icon can't carry discovery, so the first-scroll screenshots must
tell the story. Recommended captioned narrative (3–5 shots):

1. **Gather** — a gathering with RSVPs. Caption: "Plan it. Bring everyone in."
2. **Remember** — the Memory Vault with a voice note. Caption: "Every photo and
   story, kept."
3. **Belong** — Legacy Threads / an elder prompt. Caption: "Preserve the stories
   only they can tell."
4. **Private** — the invite-only framing. Caption: "No ads. No algorithm. Just
   your people."
5. (optional) the activation/organizer view. Caption: "See who's coming at a glance."

Use real (consented, synthetic-if-needed) content, not lorem. Elder-legible type.

## Social proof (the conversion multiplier)

1 rating kills both ranking and trust. In-app, prompt for a review at the
**activation moment** (a successful first gathering / first RSVP), and seed
1 → 30+ ratings from the team's own network before any paid push.

## Beachhead

Pick **one** segment to dominate the listing and marketing around first —
**family reunions** (most emotional, most seasonal-urgent, most naturally viral).
Expand to churches / Greek orgs / alumni after the loop is working.

## Verify Google Play indexing

The audit could not surface the Play listing for its own package
(`com.ubuntumarket.kindred`). Open it logged-out and confirm it's live, indexed,
and has store keywords set — a listing that isn't indexed can't rank at all.

## Watch

- **Kindred – Home Swapping** (livekindred.com) owns the head term — don't fight it.
- **Kyndred** (kyndred.net) — near-identical name *and* positioning (private
  family reunion/album app). Closest true competitor; monitor.
