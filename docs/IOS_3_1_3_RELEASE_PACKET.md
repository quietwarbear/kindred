# Kindred iOS 3.1.3 release packet

Prepared September 20, 2026. This packet records release preparation only. It does not claim that App Store Connect accepted build 68 or that Apple review was submitted.

## Release identity

- App: heyKindred
- Bundle identifier: `com.ubuntumarket.kindred`
- Marketing version: 3.1.3
- Build: 68
- Minimum iOS version: 16.6
- Release focus: family events and the Keep The Record holiday campaign
- Prior public version: 3.1.2 build 67, confirmed live in App Store Connect and Apple's public lookup API

## Proposed App Store metadata

- Subtitle: `Family Event Planner`
- Promotional text: `Plan a holiday gathering or family event, invite relatives privately, collect RSVPs, and keep the stories together.`
- Keywords: `family event,holiday gathering,reunion,RSVP,itinerary,memories,potluck,invitation`
- Release notes: `Plan a holiday gathering for Keep The Record, or start any family event. This update improves event setup, private draft previews, RSVPs, shared tables, volunteer coordination, and family story prompts.`
- Privacy Policy: `https://www.heykindred.org/privacy`
- Terms: `https://www.heykindred.org/terms`
- Support: `https://www.heykindred.org/support`
- Full description and category proposal: `frontend/STORE_LISTINGS.md`

## Verification completed

- 18 frontend test suites and 119 tests passed for the event-first change set.
- The production frontend build and public-page prerender passed locally.
- Capacitor sync completed for iOS and Android.
- RevenueCat's Capacitor bridge was updated from 11.3.2 to 13.6.0 because the older bridge's RevenueCat iOS SDK did not compile under Xcode 27.
- RevenueCat unit tests and Android debug assembly passed after the update.
- A disposable generic iOS archive completed successfully under Xcode 27 for 3.1.3 build 68, bundle `com.ubuntumarket.kindred`; Xcode's store validation build phase passed. An iPhone 17 simulator build also installed and launched successfully for the event-first change set.
- Xcode Cloud build 180 failed before compilation because `npm install` resolved `@sentry/capacitor` 4.4.0, whose npm tarball omits `SentryCapacitor.podspec`.
- The cloud install is now deterministic with `npm ci`, `@sentry/capacitor` is pinned to 4.3.0, and the script explicitly verifies that the podspec exists before Capacitor sync.
- The deterministic screenshot generator produced exactly 15 synthetic PNGs: five iPhone, five iPad, and five Google phone images. Manifest inventory, dimensions, and SHA-256 hashes match.
- The screenshots were rendered from the production frontend with synthetic in-process API responses. No generative-AI model was used.

## Store creative order

1. Start a family event
2. Build the event plan
3. Share one private RSVP
4. See what needs attention
5. Keep the stories

Canonical file paths and hashes are in `frontend/store-assets/manifest.json`.

## Pending before review submission

- Verify the 3.1.3/68 archive in Xcode Cloud and wait for App Store Connect processing; the local archive is development-signed and was not uploaded directly.
- Complete a physical-device smoke test if the available iPhone can be brought online.
- Create/select App Store version 3.1.3 and build 68.
- Apply and verify the event-first metadata and the five iPhone plus five iPad screenshots in App Store Connect.
- Reconcile App Privacy answers against the production data map. Do not infer identity linkage, tracking, retention, or processor/legal treatment.
- Verify subscription products, reviewer credentials, export compliance, content rights, and release mode in App Store Connect.
- Obtain explicit owner approval immediately before `Submit for Review`.

## Submission boundary

Uploading a build for processing does not authorize review submission. Do not click `Submit for Review` until the owner confirms after seeing the completed App Store Connect version page and any warnings.
