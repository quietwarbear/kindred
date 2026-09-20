# Kindred iOS 3.1.2 release packet

Prepared September 20, 2026. This packet records release preparation only. It does not claim that App Store Connect accepted a build or that Apple review was submitted.

## Release identity

- App: heyKindred
- Bundle identifier: `com.ubuntumarket.kindred`
- Marketing version: 3.1.2
- Build: 67
- Minimum iOS version: 16.6
- Release focus: family events and the Keep The Record holiday campaign

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

- 18 frontend test suites and 119 tests passed.
- The production frontend build and public-page prerender passed.
- Capacitor sync completed for iOS and Android.
- RevenueCat's Capacitor bridge was updated from 11.3.2 to 13.6.0 because the older bridge's RevenueCat iOS SDK did not compile under Xcode 27.
- RevenueCat unit tests passed after the update.
- Android debug assembly passed after the update.
- A generic iOS archive completed successfully under Xcode 27 and passed Xcode's store validation build phase.
- The archive reports version 3.1.2, build 67, bundle `com.ubuntumarket.kindred`, and team `H543QXDYUW`.
- An iPhone 17 simulator build installed and launched successfully with the current Keep The Record landing screen.
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

- Complete a physical-device smoke test. The available iPhone was offline during this verification.
- Authenticate the Apple developer account in Xcode or App Store Connect; the locally cached Xcode account is missing its current Xcode token.
- Export or upload using an Apple Distribution credential and select build 67 in App Store Connect.
- Apply and verify the event-first metadata and the five iPhone plus five iPad screenshots in App Store Connect.
- Reconcile App Privacy answers against the production data map. Do not infer identity linkage, tracking, retention, or processor/legal treatment.
- Verify subscription products, reviewer credentials, export compliance, content rights, and release mode in App Store Connect.
- Obtain explicit owner approval immediately before `Submit for Review`.

## Submission boundary

Uploading a build for processing does not authorize review submission. Do not click `Submit for Review` until the owner confirms after seeing the completed App Store Connect version page and any warnings.
