# heyKindred proposed store metadata

Last reviewed against the built application and `docs/PRIVACY_DATA_MAP.md`: 2026-07-30

These are repository-managed proposals. Nothing in this file has been published to App Store Connect or Google Play Console. Store-console privacy answers must follow `docs/STORE_PRIVACY_DECLARATION_MATRIX.md` and receive the production/legal confirmations listed there.

## Shared positioning

**Primary promise:** Plan the reunion. Bring everyone in. Keep the stories.

**Position:** heyKindred is a private family-reunion planner and source of truth. Existing family chats can continue; Kindred keeps the itinerary, private invitation, RSVP responses, planning work, and memories together.

**Do not claim:** that Kindred replaces WhatsApp or Facebook; that all data is deleted within 30 days; that Kindred collects no data; adoption figures; security certifications; end-to-end encryption; guaranteed delivery; unsupported prices; or provider behavior not confirmed in production.

## Apple App Store

### Product name

heyKindred

### Subtitle

Family Reunion Planner

### Promotional text

Plan a multiday family reunion, invite relatives privately, collect no-account RSVPs, coordinate the details, and keep the stories together.

### Description

Plan the reunion. Bring everyone in. Keep the stories.

heyKindred gives your family one private place to coordinate a reunion without asking every relative to abandon the chats they already use.

START THE REUNION

Name the gathering, choose the dates and location, and begin with a focused planning workspace.

BUILD A MULTIDAY ITINERARY

Keep activities, times, venues, RSVP choices, potluck needs, volunteer roles, and travel details in one plan.

INVITE FAMILY PRIVATELY

Create a private invitation for the intended relative. Guests can respond on the web without creating an account.

SEE WHAT NEEDS ATTENTION

Organizers can review response gaps and planning progress while member and guest views remain limited to the information they need.

KEEP THE STORIES

Preserve family photos, voice notes, oral histories, and memories after the reunion.

Kindred is invitation-only, has no public member profiles, and is not built around an advertising feed. Kindred processes account, community, content, device, purchase, communication, diagnostic, and usage information as described in its Privacy Policy.

Privacy Policy: https://www.heykindred.org/privacy
Terms of Service: https://www.heykindred.org/terms

### Keywords

family reunion,reunion planner,RSVP,itinerary,family memories,potluck,volunteers,invitation

### Category recommendation

- Primary: Lifestyle
- Secondary: Social Networking
- Rationale: the acquisition job is personal family-reunion planning; social participation supports that job but is not the primary store promise.

### URLs

- Support: https://www.heykindred.org/support
- Privacy policy: https://www.heykindred.org/privacy
- Marketing: https://www.heykindred.org
- Terms: https://www.heykindred.org/terms

### Release notes

Kindred now opens with one reunion-first path: start a private reunion plan, build a multiday itinerary, share a private invitation, collect no-account RSVPs, see planning gaps, and preserve family stories. This release also aligns public privacy and support information with the application’s documented behavior.

## Google Play

### App name

heyKindred: Reunion Planner

### Short description

Plan a private family reunion, collect RSVPs, and keep the stories together.

### Full description

Plan the reunion. Bring everyone in. Keep the stories.

heyKindred is a private family-reunion planner for organizers, invited relatives, and multigenerational families.

Your family can keep using its existing group chats. Kindred serves as the private reunion source of truth for:

- Multiday activities, times, and locations
- Private invitations
- No-account guest RSVP
- Response gaps and planning progress
- Potluck items, volunteer roles, and travel details
- Family photos, voice notes, oral histories, and memories

Organizers control the reunion plan and invitations. Guests receive the gathering information needed to respond from a private web link. Family membership is not published as a public profile.

Kindred is not positioned as a replacement for WhatsApp, Facebook, text messages, or phone calls. It keeps the details that are difficult to manage inside a conversation in one private workspace.

Kindred processes account, profile, community, event, RSVP, content, device, purchase, communication, diagnostic, and usage information. Review the Privacy Policy for the current categories, service providers, retention limitations, and deletion controls.

Privacy Policy: https://www.heykindred.org/privacy
Terms of Service: https://www.heykindred.org/terms

### Category recommendation

- Category: Events
- Rationale: the primary acquisition and first-value job is planning and coordinating a family reunion.

### Contact and URLs

- Current verified repository support email: support@ubuntu-village.org
- Support URL: https://www.heykindred.org/support
- Privacy policy: https://www.heykindred.org/privacy
- Marketing URL: https://www.heykindred.org
- Terms: https://www.heykindred.org/terms

The support email is a verified existing fallback but is not on the canonical `heykindred.org` domain. Do not invent or publish a replacement mailbox until the owner verifies that it exists and receives mail.

### Release notes

A clearer reunion-first start, private multiday planning, no-account guest RSVP, response-gap visibility, and aligned privacy and support information.

## Screenshot captions and order

Use the same six-frame narrative on Apple and Google:

1. **Start a family reunion** — Name the gathering, dates, and place.
2. **Build a multiday itinerary** — Keep every activity and update in one plan.
3. **Share one private invitation** — Invite family without posting details publicly.
4. **RSVP without an account** — Relatives can answer from a private web link.
5. **See what still needs attention** — Track responses, gaps, and planning progress.
6. **Keep the stories** — Preserve photos, voices, and memories after the reunion.

The reproducible source campaign, exact dimensions, alt text, and synthetic-data statement are in `frontend/store-assets/README.md`.

## Reviewer instructions

1. Use only the dedicated synthetic review account entered securely in the applicable store console. Do not place review credentials in this repository or in listing text.
2. To review organizer behavior, start a reunion draft, save it with the synthetic account, and create a private invitation for a synthetic disposable invitee.
3. To review no-account RSVP, open that newly created synthetic invitation in a signed-out browser and submit a response. No account is required for this step.
4. Do not use production family names, events, invitations, email addresses, or customer records.
5. Web subscription checkout intentionally remains unavailable and returns HTTP 410 with `subscription_checkout_migrating`. Do not treat that paused path as a working purchase flow.

## External console changes intentionally unpublished

- Apple product name, subtitle, description, keywords, categories, release notes, reviewer instructions, URLs, screenshot order, screenshots, and App Privacy answers.
- Google app name, short/full descriptions, category, release notes, contact/support URLs, screenshot order, screenshots, and Data Safety answers.
- Any branded support-mailbox replacement.
- Any price, product, subscription, or purchase-console change.
