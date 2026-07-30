# Release 2: Store and Trust Correction

Prepared from `origin/main` commit `0962195b304339bd3300c6cd0d083c052308daf4` on 2026-07-30.

This is a repository-only release candidate. No Apple App Store or Google Play listing, privacy declaration, screenshot, price, reviewer credential, or build has been uploaded or published.

## Positioning correction

**Before:** repository store copy presented Kindred broadly as a permanent digital home for families, churches, neighborhoods, and intentional communities, emphasizing governance tiers and unsupported price copy. The public Google Play declaration also remained inconsistent with the application's documented data processing.

**After:** public, first-open, authentication, support, privacy, terms, and proposed store copy use one reunion-first promise:

> Plan the reunion. Bring everyone in. Keep the stories.

The narrative is limited to implemented behavior: private reunion planning, multiday itineraries, private organizer controls, no-account web RSVP, participation and contributions, response-gap visibility, and post-reunion stories. Existing family chats can continue; Kindred is the private reunion source of truth rather than a WhatsApp or Facebook replacement.

## Privacy reconciliation

`docs/STORE_PRIVACY_DECLARATION_MATRIX.md` maps each observed data category to:

- collection versus temporary processing;
- identity linkage;
- application functionality, analytics, communications, and account-management purposes;
- Apple and Google declaration categories;
- Apple, Google, RevenueCat, Resend, Vercel, Railway, MongoDB, push, payment, analytics, email, and optional AI processing;
- first-party deletion behavior and provider, backup, log, accounting, and legal-retention limitations.

The matrix explicitly rejects “No data collected” and a complete 30-day deletion promise. Console answers remain gated on current production configuration and legal confirmation.

## Store creative manifest

The real production frontend build is rendered against in-process synthetic disposable responses. External application and provider requests are blocked during capture.

| Store set | Dimensions | Frames |
|---|---:|---:|
| Apple iPhone 6.9-inch | 1320 x 2868 PNG | 6 |
| Apple iPad 13-inch | 2064 x 2752 PNG | 6 |
| Google phone | 1080 x 1920 PNG | 6 |

The campaign shows:

1. Start a family reunion.
2. Build a multiday itinerary.
3. Share one private invitation.
4. RSVP without an account.
5. See response gaps and planning progress.
6. Preserve stories and memories.

`frontend/store-assets/manifest.json` records exact files, dimensions, captions, alt text, and SHA-256 hashes. The generator validates dimensions, alpha channel, caption safe area, typography, horizontal crop, intended content, sensitive markers, and the external-request boundary.

## Synthetic-data statement

Every campaign person, family space, date, location, activity, invitation, response, planning total, and memory is synthetic and disposable. The generator does not query customer records, production invitations, provider payloads, email history, or credentials. Its synthetic RSVP credential remains inside the local harness and is absent from images, filenames, reports, and the manifest.

## Support identity

All public support, privacy, terms, and marketing URLs use `https://www.heykindred.org`. The repository's only verified support mailbox remains `support@ubuntu-village.org`. A canonical-domain mailbox could not be verified, so no new address or provider change was invented.

## Verification evidence

- Base: `origin/main` and local starting commit both verified as `0962195b304339bd3300c6cd0d083c052308daf4`.
- Frontend unit tests: `CI=true yarn test --watchAll=false` — 5 suites, 28 tests passed.
- Focused offline privacy/security regressions: 50 tests passed, including store-trust, commercial-readiness, reunion-activation, invitation-redelivery static boundaries, and every paid-plan HTTP 410 case.
- Production frontend: `GENERATE_SOURCEMAP=false yarn build` — compiled and prerendered the public routes successfully.
- Built-browser campaign: desktop and mobile reunion-first homepage, keyboard CTA, draft, invitation preview, organizer itinerary, operations summary, no-account activity RSVP, authentication boundary, pricing, privacy, terms, support, fragment/header transport, legacy transition, service-worker upgrade/purge, third-party isolation, and no anonymous backend mutations passed.
- Store campaign: 18 PNGs generated and validated at the exact dimensions above.
- Store-asset sensitive-marker scan: no URL, email, credential, reviewer, demo, staging, development, production-customer, or provider marker found in PNG payload strings, filenames, or the manifest.
- Public URLs: marketing, privacy, terms, and support returned HTTP 200.
- Android: production web assets synced in a disposable copy; `assembleDebug` completed with Java 21.
- iOS: production web assets and CocoaPods synced in a disposable copy; unsigned `iphoneos` Debug build completed with code signing disabled.
- Subscription regression: every web paid-plan/billing-cycle path retained HTTP 410 with `subscription_checkout_migrating`, and the static regression confirmed the handler cannot reach Stripe or subscription writes.
- Source checks: JavaScript syntax validation, changed-source secret scan, generated-artifact scan, and `git diff --check` passed.

## Known limitations and external gates

- The real-database incident campaign was not run because this machine has no configured disposable MongoDB process or matching isolated backend environment. No production database was substituted.
- Legacy RevenueCat/PWA and Capacitor API integration tests expect an external test API and shared test account. An unconfigured invocation cannot produce meaningful local results; the offline provider-initialization and native-build checks were used instead. No customer data was accessed and no successful external mutation occurred.
- `npm ci` is not reproducible from the committed npm lockfile because the existing lockfile is out of sync and the dependency graph contains a Capacitor peer-version conflict. The repository-declared Yarn workflow installed with the frozen Yarn lockfile and all requested frontend/build checks passed.
- Store-console tracking, diagnostics, retention, processor exemptions, legal disclosures, children/minor treatment, and branded support mailbox remain approval/production-confirmation gates.

## External console changes that remain unpublished

- Apple name, subtitle, promotional text, description, keywords, categories, release notes, URLs, reviewer instructions, screenshots/order, and App Privacy answers.
- Google name, short/full descriptions, category, release notes, support/contact URLs, screenshots/order, and Data Safety answers.
- Review credentials and review-contact details.
- Branded support mailbox.
- Any subscription, product, price, or purchase-console change.

## Safety boundary confirmation

This release does not change invitation credential transport, header-only `/api/public/rsvp`, legacy RSVP protections, hidden-event confidentiality, notification audience isolation, RSVP concurrency/idempotency, service-worker RSVP bypass/purge, privacy-safe redelivery, provider initialization, Apple/Google authentication, RevenueCat initialization, the subscription HTTP 410 kill switch, or the subscription recovery pause.

No production customer data, invitation, credential, provider payload, or email history was accessed. No invitation was rotated, no message was sent, no provider configuration was changed, no store listing was published, and no production code was deployed. Opening the draft PR can trigger the repository's existing isolated Vercel preview automation; that preview is not a production promotion.
