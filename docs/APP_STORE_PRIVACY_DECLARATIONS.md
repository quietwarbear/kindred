# Kindred Apple App Privacy and Google Play Data Safety worksheet

Last code review: 2026-07-30

The exact cross-store category, linkage, purpose, processor, collection-versus-temporary-processing, retention, and deletion reconciliation is maintained in `docs/STORE_PRIVACY_DECLARATION_MATRIX.md`. This worksheet is the console-oriented companion; if the two differ, stop and reconcile them against `docs/PRIVACY_DATA_MAP.md` and the current code before submission.

Use this worksheet to update the store consoles. No console changes were made. The answers below reflect production code paths; the owner must confirm production configuration, provider contracts, and actual feature availability before submitting. Store taxonomy and legal interpretations can change, so review the current console definitions and obtain legal review.

## Apple App Privacy

Answer **Yes, data is collected**.

### Data linked to the user

| Apple category | Select | Purpose(s) to select | Code-backed examples |
|---|---|---|---|
| Contact Info → Name | Yes | App Functionality; Developer Communications | Account/profile, invitations, email |
| Contact Info → Email Address | Yes | App Functionality; Developer Communications | Account, support, Resend, Stripe customer, cross-product SSO |
| Contact Info → Phone Number | Yes | App Functionality | Optional profile field |
| User Content → Photos or Videos | Yes | App Functionality | Profile images and memory images |
| User Content → Audio Data | Yes | App Functionality | Voice notes and Whisper transcription |
| User Content → Other User Content | Yes | App Functionality | Chats, announcements, events, polls, memories, threads, attachments, care and planning content |
| Identifiers → User ID | Yes | App Functionality; Analytics | Backend user/community IDs; PostHog identify; RevenueCat app user ID |
| Identifiers → Device ID | Yes | App Functionality | Push notification token. Confirm with counsel whether the token fits Apple's Device ID definition in the active SDK path |
| Purchases → Purchase History | Yes | App Functionality | Plan, product, transaction/customer identifiers, status and dates from Stripe/RevenueCat/stores |
| Usage Data → Product Interaction | Yes | Analytics; App Functionality | GA/GTM and PostHog page views/autocapture/interactions |
| Diagnostics → Crash Data | Production confirmation required | App Functionality; Analytics | No dedicated crash SDK was found, but Apple/Google/platform or PostHog diagnostics may apply depending on enabled console/SDK settings |
| Diagnostics → Performance Data | Production confirmation required | Analytics | Confirm PostHog/hosting/mobile platform configuration |
| Other Data | Yes | App Functionality | Roles, community membership, notification preferences, kinship and community coordination records |

### Tracking

- **Name, email, community content, purchases:** select **Not used for tracking** based on current code.
- **Usage Data / identifiers collected by Google Analytics, GTM, and PostHog:** production/legal confirmation required. If any data is combined with third-party data for targeted advertising, ad measurement, data-broker sharing, or cross-company tracking under Apple's definition, mark the relevant categories as **used for tracking** and ensure ATT/consent compliance.
- The code states no ads and no sale of personal information, but GTM can load additional tags. Inspect the live GTM container before answering “No” to tracking.

### Apple form notes

- Payment card numbers are handled by Stripe/Apple and are not received by Kindred; do not select “Payment Info” solely for StoreKit/App Store processing unless the current Apple instructions require it for the app's own collection.
- AI processing does not remove the need to disclose the underlying User Content categories.
- If voice transcription, translation, analytics, push, cross-product SSO, or an AI provider is disabled in the shipped binary/production environment, preserve evidence before narrowing any answer.

## Google Play Data Safety

### Overview answers

- **Does the app collect or share any of the required user data types?** Yes.
- **Is all user data encrypted in transit?** Select Yes only after confirming every production endpoint and vendor path uses HTTPS/TLS. The intended first-party and vendor URLs are HTTPS.
- **Do you provide a way for users to request deletion?** Yes: in-app Settings account deletion and `support@heykindred.org`. Disclose the ownership-transfer limitation and community-content retention behavior accurately.
- **Is data collection required?** Account identity and core community content are required for corresponding features. Profile phone/image, push, analytics where consent law applies, AI actions, voice notes, translations, Google/Apple sign-in, cross-product SSO, and purchases are optional or feature-dependent.

### Data types to declare

| Google Play category | Collected | Shared | Purpose(s) | Required / optional |
|---|---:|---:|---|---|
| Personal info → Name | Yes | Yes, to service providers when needed | App functionality; Account management; Developer communications | Required for account/community identity |
| Personal info → Email address | Yes | Yes (Google/Apple auth as chosen, Stripe, Resend, sibling SSO when initiated) | App functionality; Account management; Developer communications; Fraud/security | Required for account |
| Personal info → Phone number | Yes | No observed routine external sharing | App functionality | Optional |
| Photos and videos → Photos | Yes | Yes when AI tagging is invoked; hosting/database processors | App functionality | Optional |
| Audio files → Voice or sound recordings | Yes | Yes when transcription is invoked; hosting/database processors | App functionality | Optional |
| App activity → App interactions | Yes | Yes (Google Analytics/GTM, PostHog) | Analytics; App functionality | Automatically collected in current web code; confirm mobile WebView behavior |
| App activity → Other user-generated content | Yes | Yes to processors and AI provider when corresponding features run | App functionality | Feature-dependent |
| App info and performance → Diagnostics / Other app performance data | Production confirmation required | Production confirmation required | Analytics; App functionality | Inspect live SDK/provider settings |
| Device or other IDs | Yes | Yes (push infrastructure, RevenueCat, analytics as applicable) | App functionality; Analytics; Fraud/security | Push is optional; analytics currently automatic in web bundle |
| Financial info → Purchase history | Yes | Yes (Stripe, RevenueCat, Apple, Google) | App functionality; Fraud/security; Account management | Required only for paid subscription |
| Messages → Other in-app messages | Yes | Hosting/database processors | App functionality | Optional feature |
| Files and docs | Yes | Hosting/database processors; AI provider if a supported workflow transmits them | App functionality | Optional |

“Shared” above includes transfers to service providers for Play's disclosure workflow only if the current Play definition does not exempt the processor transfer. Apply the current service-provider exemption carefully rather than copying this column mechanically.

### Security practices and deletion URL

- Public privacy policy: `https://www.heykindred.org/privacy`
- Public support: `https://www.heykindred.org/support`
- Public website: `https://www.heykindred.org`
- In-app deletion: Settings → Delete Account
- External deletion request/contact: `support@heykindred.org`
- Account deletion behavior: immediate first-party deletion for the records enumerated in `backend/routes/auth.py`; owners with other members must transfer ownership; some community, subscription, vendor, log, backup, and legal-retention records require confirmation and may persist.

## Before submitting either store form

1. Inspect the live GTM container and PostHog project settings.
2. Confirm the production AI model/provider and vendor data-use terms.
3. Confirm whether analytics runs in the native WebView and whether ATT, consent, or opt-out controls are required.
4. Confirm push infrastructure, crash/diagnostic collection, and store SDK automatic collection.
5. Confirm deletion coverage, backup retention, and statutory billing retention.
6. Have privacy counsel approve the linked policy and the “tracking,” “shared,” children, retention, and deletion answers.
