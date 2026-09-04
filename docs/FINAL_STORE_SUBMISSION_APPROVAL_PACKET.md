# Kindred final store submission approval packet

**Prepared:** August 9, 2026 (America/Los_Angeles)  
**Decision:** **ENGINEERING GATES CLEARED; PRIVACY/STORE APPROVAL STILL REQUIRED**  
**Publication state:** Nothing was submitted, published, deployed, uploaded, rolled out, or placed into review.

This packet is the final pre-submission evidence record for the reunion-first store correction. It preserves the boundary that store submission requires a separate, explicit owner approval covering the exact metadata, privacy declarations, screenshots, build treatment, release notes, contact information, and publication behavior.

## Executive disposition

The reunion-first product, metadata proposal, deterministic 15-image campaign, public support/privacy pages, Android compilation, and unsigned iOS compilation are prepared. The canonical screenshots are structurally and visually valid and were not created or edited with generative AI.

The fifteen documented backend HTTP disagreements are resolved and the complete synthetic test collection is green. The release remains **not ready for store submission** because:

1. The repository and available store consoles cannot prove the production/legal privacy facts required for Google Data Safety or Apple App Privacy.
2. Google Play still has an unsubmitted Data Safety change, an unset AI-asset declaration on the store-listing draft, and no canonical screenshot upload.
3. App Store Connect requires a fresh Apple sign-in, so the Apple draft and current privacy answers could not be re-inspected or prepared in-console.
4. The native checks produced only a debug Android APK and an unsigned iOS app. They do not prove signed store-artifact provenance or physical-device behavior if a new binary is required.
5. No current, authorized evidence confirms the live RevenueCat/Stripe catalog, mobile diagnostics, analytics consent/settings, or processor contracts and retention.

## Completed verification

| Area | Result | Evidence and limitation |
|---|---|---|
| Store boundaries | Complete | No save, submit, review, publication, upload, rollout, deploy, pricing, contact, release-note, or production-configuration action was taken. |
| Public first-party pages | Pass | `https://www.heykindred.org`, `/privacy`, `/terms`, and `/support` returned HTTP 200 with successful TLS certificate verification. This does not prove every vendor path. |
| Complete backend collection | Pass | 755 tests collected with no collection error. Repository/loopback run: 732 passed, 8 intentionally skipped. All 15 disposable-database tests passed separately, for 747 passing tests and zero failures. |
| Disposable MongoDB tests | Pass | All 11 disposable-database files passed in separate processes with isolated database names: 15 passed. A temporary MongoDB 7 replica set was used. |
| Loopback HTTP integration | Pass | All fifteen previously failing contract assertions were reproduced, classified, corrected or updated, and passed on rerun. No production or provider traffic was used. |
| Android compilation | Pass, partial provenance | Capacitor sync and `assembleDebug` passed in a disposable copy: 340 Gradle tasks, 23 seconds. No upload and no signed AAB. |
| iOS compilation | Pass, partial provenance | Capacitor sync, CocoaPods install, and unsigned generic-device Xcode build passed in disposable locations. No archive, signing, upload, or device run. |
| Screenshot package | Pass | 15/15 files match the manifest, exact dimensions, SHA-256 hashes, RGB color, and no-alpha requirements; sensitive-marker scan and full-size visual clipping review passed. |
| Screenshot provenance | Pass | Deterministic local browser rendering from the production frontend with synthetic in-process API responses; external requests blocked; no generative-AI image or text model used. |
| Google Play read-only inspection | Complete | Signed-in console inspected without editing or saving. Managed Publishing is off; Data Safety remains pending; draft listing has an unset AI declaration; canonical screenshots are not uploaded. |
| Apple read-only inspection | Blocked | App Store Connect is at the Apple sign-in screen and requires fresh authentication. |

## Backend verification details

### Final totals

- Complete collection: **755 tests**, zero collection errors.
- Repository and loopback run: **732 passed, 8 skipped, 0 failed**.
- Disposable MongoDB run: **15 passed** across all 11 `*_disposable_db.py` files, each with its own database name.
- Aggregate: **747 passed, 8 skipped, 0 failed**.
- Frontend: **11 suites and 59 tests passed**; production build and six-route prerender passed.
- Store-trust/focused regression group: **18 passed**.

The eight intentional skips are environment/feature-availability branches already reported by the tests; none was a failure or a concealed production check. No test contacted a production database, customer record, invitation-delivery provider, payment provider, or store service.

### Resolution of the fifteen documented HTTP disagreements

| Classification | Resolution |
|---|---|
| Genuine authentication regression | Invalid bearer tokens could let a decoder `ValueError` escape as HTTP 500. Authentication now converts malformed/invalid tokens to the same generic HTTP 401 contract without exposing token or exception details; focused account-deletion regression coverage passes. |
| Genuine attachment contract regression | The frontend sends `name`, `data_url`, and `mime_type`, while the backend model only accepted legacy `file_name` and `file_data`. The canonical model now uses the frontend shape and safely accepts the legacy aliases. Two focused normalization tests were added; announcement and chat projections pass. |
| Genuine overview projection omission | The community overview implementation supplied the current user, but the response model stripped it. The typed response now includes the existing privacy-safe user projection. |
| Intentionally safer contracts with stale tests | Google sign-in uses `credential`, RSVP member responses expose only the caller's status/guest count, `/auth/me` uses a `user` envelope, polls and announcements use named envelopes, GET `/auth/bootstrap` is retired, invite copy says `Join online:`, and arbitrary Legacy Table configuration/bulk export routes remain retired. Tests were aligned only after checking implementation and frontend consumers. |
| Authorization/subscription gates | Seedling subyard limits and paid travel/shared-funds gates correctly return HTTP 403 with no write. Organizer-only named volunteer/potluck projections remain separate from member-safe aggregate projections; frontend consumers were updated to handle those safe shapes. |
| Missing provider configuration / expected fail-closed behavior | Contributions/add-on provider initialization returns HTTP 503 without verified credentials; RevenueCat offerings, restore, and webhook processing return HTTP 503 when unconfigured; web subscription checkout remains globally disabled with HTTP 410 `subscription_checkout_migrating`. Tests now assert these boundaries instead of expecting synthetic purchase success. |

Additional stale full-suite assumptions were reconciled: PWA files are validated from `frontend/public` rather than requested from the backend API, RevenueCat entitlement tests use the canonical `*_access` IDs, and the legacy inline-edit suite self-seeds a disposable identity while respecting the Seedling subyard cap.

Warnings observed but not treated as test failures: Starlette multipart pending deprecation, Python `crypt` deprecation through Passlib, FastAPI `on_event` deprecation, and a Passlib/bcrypt version-introspection warning.

## Native build and provenance record

### Android

- Application ID: `com.ubuntumarket.kindred`
- Source version name: **3.1.0**
- Source version code: **18**
- Minimum API: **24**
- Target/compile SDK: **36**
- Disposable debug APK size: **11,461,970 bytes**
- Disposable debug APK SHA-256: `b87b790bfcfb90e66f58a52170325f60744f43546e53c037698d4f6efbd5761a`
- Result: Capacitor sync and debug compilation passed.
- Limitation: debug APK only; no signed release AAB, Play signing verification, upload, internal test, or physical-device test.

### iOS

- Bundle ID: `com.ubuntumarket.kindred`
- Marketing version: **3.1.0**
- Build number: **65**
- Xcode: **26.6**
- Disposable unsigned app executable size: **72,688 bytes**
- Disposable unsigned app executable SHA-256: `566d2f72e3bf89bca7630f766c58598e0ea507eb61cba8bfcffa31d9c5f7bed8`
- Result: Capacitor sync, CocoaPods install, and unsigned generic-device compilation passed.
- Limitation: no signing, archive, App Store validation, upload, TestFlight, or physical-device test.
- Warnings: one unassigned AppIcon child, a CocoaPods embed phase configured to run every build, and no AppIntents metadata.

### Proposed store-build treatment

The console evidence indicates version 3.1.0 is already public. Therefore the reunion-first listing correction should be treated as **metadata/privacy/screenshot work with no binary upload** unless the console requires a new version container. If a new binary is required, do not reuse Android code 18 or iOS build 65: increment the applicable build identifier, create signed release artifacts, verify their provenance, and repeat native/device testing before approval.

## Canonical screenshot validation

The only proposed upload source is `frontend/store-assets` and its `manifest.json`.

| Platform | Count | Dimensions | Format | Result |
|---|---:|---:|---|---|
| Google phone | 5 | 1080 x 1920 | RGB PNG, no alpha | Pass |
| Apple iPhone 6.9-inch | 5 | 1320 x 2868 | RGB PNG, no alpha | Pass |
| Apple iPad 13-inch | 5 | 2064 x 2752 | RGB PNG, no alpha | Pass |

Order for all three platforms:

1. Start a family reunion — Name the gathering, dates, and place.
2. Build a multiday itinerary — Keep every activity and update in one plan.
3. Share one private RSVP — Relatives can answer without creating an account.
4. See what needs attention — Track responses, gaps, and planning progress.
5. Keep the stories — Preserve photos, voices, and memories after the reunion.

All 15 current SHA-256 values match the manifest. Visual review at full size and scaled/store-like size found no clipped caption or application text. No visible email address, URL, credential, invitation token, reviewer/demo/staging/development label, watermark, or production record was found. The older untracked `docs/store-screenshots` files are not approved upload assets.

A fresh disposable scripted render also generated and passed visual/clipping validation for all 15 frames. Chromium capture output is not byte-reproducible across runs (a minority of fresh frames had pixel/hash differences), so the recorded SHA-256 values attest the fixed canonical upload files, not every future rerender. The source fixtures and rendering process remain deterministic in content and use no generative-AI model.

### Google AI-asset declaration

For this canonical screenshot campaign, the exact proposed choice is:

- **Select:** `Don't label assets`
- **Reason:** The assets were created by deterministic browser rendering and caption composition. No generative-AI model created or edited the screenshots.

This remains a proposal only. The Play draft currently has neither AI radio option selected, and nothing was saved.

## Production and privacy evidence audit

| Evidence area | Repository/read-only finding | Submission status |
|---|---|---|
| First-party web TLS | Public site, privacy, terms, and support pages passed HTTPS/TLS verification. | Partially verified only. |
| MongoDB | Code uses the configured MongoDB URL and stores account, reunion, content, purchase, push, and operational records. Live host, TLS enforcement, region, backups, and retention were not inspected. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Frontend/backend hosting | Repository indicates Vercel and Railway; public first-party web TLS passed. Live project binding, backend path, log/backup retention, IP handling, and regional processing remain unproven. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Resend/email | Code calls the HTTPS Resend API and handles delivery events. Active account, DPA, message/log retention, suppression data, and deletion were not proven. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Push | Code supports APNs and FCM and stores device tokens; server push is disabled by default in code. Shipped entitlements, active production configuration, platform diagnostics, and retention were not proven. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| RevenueCat/Stripe | Code links store/customer identifiers to Kindred user IDs and stores entitlement/subscription records. Live keys, products, automatic SDK collection, DPA, retention, and deletion were not inspected. Checkout remains paused. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Optional AI | Repository supports LiteLLM-routed AI, Gemini/OpenAI-style paths, and transcription when invoked. The production provider/model, no-training terms, TLS path, and retention are not provable from code. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Crash/performance diagnostics | No dedicated Sentry, Firebase Crashlytics, or equivalent app dependency was found in the inspected source. Store/platform, hosting, PostHog, and SDK diagnostics can still apply. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Google Analytics/GTM | GA and GTM load automatically outside localhost and protected invitation routes. Live container tags, consent mode, Google Signals/ads features, IP treatment, retention, regional processing, and cross-company use were not inspected. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| PostHog | EU ingestion host is coded; page views and autocapture are on; text and attributes are masked; sensitive content routes suppress pageview/autocapture/snapshots; signed-in activity is identified to backend user ID; no in-product opt-out was found. Live retention, IP capture, session replay/project settings, consent, deletion, and cross-company use remain unproven. | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Processor exclusions | Code establishes processor paths but not current contracts, use restrictions, or every Google service-provider-exclusion condition. | Treat transfers as shared conservatively; **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Retention/deletion | In-app deletion exists, but ownership transfer, shared-content, newer subscription/service records, logs, backups, analytics, payments, email, AI, and legal retention limit completeness. | Do not promise complete deletion within 30 days; **OWNER/LEGAL CONFIRMATION REQUIRED** |

## Exact proposed Google Play Data Safety answers

These are field proposals, not saved console answers. Current Play definitions and legal review control if the wording changes.

### Overview and security

- Does the app collect or share required user data types? **Yes**.
- Is all user data encrypted in transit? **Do not answer yet — OWNER/LEGAL CONFIRMATION REQUIRED.** Select Yes only after every production and provider path is proven TLS-protected.
- Does the app provide account creation? **Yes**.
- Account-creation methods: **email and password, Google OAuth, and Apple OAuth**.
- Can users request deletion? **Yes**.
- In-app path: **Settings -> Delete Account**.
- External deletion URL: `https://www.heykindred.org/support`.
- External contact: `support@heykindred.org`.
- Deletion qualification: owners with other members must transfer ownership; shared community content and some subscription/provider/log/backup/legal-retention records may persist.
- Independent security review: **Do not claim one without evidence.**
- Government app: **No**, subject to owner confirmation.
- Financial features: declare only the current store form selections supported by purchases/subscriptions; checkout remains disabled and pricing must not be changed in this pass.

### Collection and sharing entries

Until every service-provider exclusion is proven, use the conservative **Shared = Yes** treatment below for processor transfers.

| Google category | Collected | Shared | Purposes | Required/optional |
|---|---:|---:|---|---|
| Personal info -> Name | Yes | Yes | App functionality; Account management; Developer communications | Required for account/community identity |
| Personal info -> Email address | Yes | Yes | App functionality; Account management; Developer communications; Fraud prevention/security | Required for account |
| Personal info -> Phone number | Yes | Conservative Yes pending processor review | App functionality | Optional |
| Photos and videos -> Photos | Yes | Yes | App functionality | Optional; AI transfer only when invoked |
| Audio files -> Voice or sound recordings | Yes | Yes | App functionality | Optional; transcription transfer only when invoked |
| App activity -> App interactions | Yes | Yes | Analytics; App functionality | Automatically collected where analytics initializes |
| App activity -> Other user-generated content | Yes | Yes | App functionality | Feature-dependent |
| App info and performance -> Diagnostics | Do not finalize | Do not finalize | Analytics; App functionality | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| App info and performance -> Other app performance data | Do not finalize | Do not finalize | Analytics; App functionality | **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Device or other IDs | Yes | Yes | App functionality; Analytics; Fraud prevention/security | Push optional; analytics/SDK dependent |
| Financial info -> Purchase history | Yes | Yes | App functionality; Fraud prevention/security; Account management | Required only for paid subscription |
| Messages -> Other in-app messages | Yes | Yes | App functionality | Optional feature |
| Files and docs | Yes | Yes | App functionality | Optional; AI transfer only for invoked supported workflows |

For each collected category, mark the data as linked to identity when it belongs to an account, community, purchase, push token, support interaction, or identified analytics path. Mark collection optional only where the user can use the app without that category or invokes a feature selectively. Do not use “ephemeral” for records stored by Kindred or retained by a provider.

## Exact proposed Apple App Privacy answers

Answer **Yes, data is collected**. The current public “Data Not Linked to You” presentation must not be copied forward for data tied to accounts, purchases, user content, support, device tokens, or identified analytics.

### Data linked to the user

| Apple category | Select | Purpose(s) |
|---|---:|---|
| Contact Info -> Name | Yes | App Functionality; Developer Communications |
| Contact Info -> Email Address | Yes | App Functionality; Developer Communications |
| Contact Info -> Phone Number | Yes | App Functionality |
| User Content -> Photos or Videos | Yes | App Functionality |
| User Content -> Audio Data | Yes | App Functionality |
| User Content -> Other User Content | Yes | App Functionality |
| Identifiers -> User ID | Yes | App Functionality; Analytics |
| Identifiers -> Device ID | Yes, pending Apple-definition confirmation | App Functionality |
| Purchases -> Purchase History | Yes | App Functionality; Account Management |
| Usage Data -> Product Interaction | Yes | Analytics; App Functionality |
| Diagnostics -> Crash Data | Do not finalize | App Functionality; Analytics; **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Diagnostics -> Performance Data | Do not finalize | Analytics; **OWNER/LEGAL CONFIRMATION REQUIRED** |
| Other Data | Yes | App Functionality |

### Tracking

- Name, email, private community content, and purchases: proposed **Not used for tracking** based on current code.
- Usage Data and identifiers processed by GA/GTM/PostHog: **do not finalize the tracking answer** until the live GTM container, GA property, PostHog project, and legal cross-company-use analysis are complete.
- If any relevant data is combined with third-party data for targeted advertising, ad measurement, data-broker sharing, or cross-company tracking under Apple's definition, mark the applicable categories as used for tracking and satisfy ATT/consent obligations.
- Do not select Payment Info solely because Apple/Stripe processes card details that Kindred does not receive; retain Purchase History.

## Exact proposed store metadata

### Google Play

- App name: **heyKindred: Reunion Planner**
- Short description: **Plan a private family reunion, collect RSVPs, and keep the stories together.**
- Category: **Events**
- Privacy policy: `https://www.heykindred.org/privacy`
- Support URL: `https://www.heykindred.org/support`
- Website: `https://www.heykindred.org`
- Terms: `https://www.heykindred.org/terms`
- Proposed support email: `support@heykindred.org`
- Current Play support email remains unchanged in this pass.
- Proposed release notes: **A clearer reunion-first start, private multiday planning, no-account guest RSVP, response-gap visibility, and aligned privacy and support information.**

Proposed full description:

> Plan the reunion. Bring everyone in. Keep the stories.
>
> heyKindred is a private family-reunion planner for organizers, invited relatives, and multigenerational families.
>
> Your family can keep using its existing group chats. Kindred serves as the private reunion source of truth for:
>
> - Multiday activities, times, and locations
> - Private invitations
> - No-account guest RSVP
> - Response gaps and planning progress
> - Potluck items, volunteer roles, and travel details
> - Family photos, voice notes, oral histories, and memories
>
> Organizers control the reunion plan and invitations. Guests receive the gathering information needed to respond from a private web link. Family membership is not published as a public profile.
>
> Kindred is not positioned as a replacement for WhatsApp, Facebook, text messages, or phone calls. It keeps the details that are difficult to manage inside a conversation in one private workspace.
>
> Kindred processes account, profile, community, event, RSVP, content, device, purchase, communication, diagnostic, and usage information. Review the Privacy Policy for the current categories, service providers, retention limitations, and deletion controls.
>
> Privacy Policy: https://www.heykindred.org/privacy  
> Terms of Service: https://www.heykindred.org/terms

### Apple App Store

- Product name: **heyKindred**
- Subtitle: **Family Reunion Planner**
- Promotional text: **Plan a multiday family reunion, invite relatives privately, collect no-account RSVPs, coordinate the details, and keep the stories together.**
- Keywords: **family reunion,reunion planner,RSVP,itinerary,family memories,potluck,volunteers,invitation**
- Primary category: **Lifestyle**
- Secondary category: **Social Networking**
- Support URL: `https://www.heykindred.org/support`
- Privacy policy: `https://www.heykindred.org/privacy`
- Marketing URL: `https://www.heykindred.org`
- Terms: `https://www.heykindred.org/terms`
- Proposed release notes: **Kindred now opens with one reunion-first path: start a private reunion plan, build a multiday itinerary, share a private invitation, collect no-account RSVPs, see planning gaps, and preserve family stories. This release also aligns public privacy and support information with the application's documented behavior.**

Proposed description:

> Plan the reunion. Bring everyone in. Keep the stories.
>
> heyKindred gives your family one private place to coordinate a reunion without asking every relative to abandon the chats they already use.
>
> START THE REUNION
>
> Name the gathering, choose the dates and location, and begin with a focused planning workspace.
>
> BUILD A MULTIDAY ITINERARY
>
> Keep activities, times, venues, RSVP choices, potluck needs, volunteer roles, and travel details in one plan.
>
> INVITE FAMILY PRIVATELY
>
> Create a private invitation for the intended relative. Guests can respond on the web without creating an account.
>
> SEE WHAT NEEDS ATTENTION
>
> Organizers can review response gaps and planning progress while member and guest views remain limited to the information they need.
>
> KEEP THE STORIES
>
> Preserve family photos, voice notes, oral histories, and memories after the reunion.
>
> Kindred is invitation-only, has no public member profiles, and is not built around an advertising feed. Kindred processes account, community, content, device, purchase, communication, diagnostic, and usage information as described in its Privacy Policy.
>
> Privacy Policy: https://www.heykindred.org/privacy  
> Terms of Service: https://www.heykindred.org/terms

## Read-only console change plan

### Google Play

Current read-only observations:

- Managed Publishing is **off**.
- Publishing overview says last published **August 2, 2026**.
- Dashboard displays the latest production release as released **August 3, 2026**; this is likely a console date/time-zone presentation difference and should be reconciled before the final record.
- Data Safety shows **Complete Data safety questionnaire** under changes not yet submitted for review.
- The reunion-first app name and short/full descriptions are present as unsaved draft content on the default listing.
- The AI-asset declaration is unset.
- The current listing draft does not contain the canonical five Google phone screenshots.
- No listing, privacy, or publication control was saved or submitted.

Field-by-field future action after blockers clear:

1. Complete owner/legal evidence and approve the exact Data Safety table above.
2. Select the non-generative screenshot declaration: `Don't label assets`.
3. Verify the reunion-first app name, short description, and full description against this packet.
4. Replace/reorder phone creative with the five canonical Google files only.
5. Keep category **Events**.
6. Do not alter the current contact email, website, pricing, or live release notes through a direct publish action without separate explicit approval.
7. Re-check every staged change in Publishing overview.
8. Because Managed Publishing is off, approval may make eligible changes publish automatically. Decide publication timing before any review submission.
9. Present one final approval screen; do not press Submit for review until explicitly authorized.

### App Store Connect

Current read-only observation: a fresh Apple sign-in is required, so no Apple app/version/privacy field was inspected or changed in this pass.

Future action after sign-in and blockers clear:

1. Verify whether metadata and screenshots can be changed on the current 3.1.0 version or require a new version container.
2. Enter the exact name, subtitle, promotional text, description, keywords, categories, URLs, and release notes above.
3. Upload only the five canonical iPhone and five canonical iPad screenshots in manifest order.
4. Reconcile App Privacy to the linked-data table above; do not preserve “Data Not Linked to You” for linked paths.
5. Resolve tracking, Device ID, Crash Data, and Performance Data from live settings and legal analysis.
6. Add only a newly signed/incremented build if App Store Connect requires one; otherwise make no binary upload.
7. Prepare reviewer instructions using only securely entered synthetic review credentials.
8. Present one final approval screen; do not submit for review until explicitly authorized.

## Publication behavior and unresolved risks

- Google Managed Publishing is off. A review approval can therefore publish eligible changes without a second managed-publication hold.
- Apple publication behavior could not be reverified while signed out.
- Google Data Safety remains a pending, unsubmitted console change.
- Canonical screenshots have not been uploaded to either store.
- The Play listing AI declaration is not selected.
- Current production analytics, diagnostics, processor contracts, deletion/retention, and cross-company use remain unproven.
- Store metadata correction without a new binary may be possible, but the console-specific version container requirements must be confirmed.
- Debug/unsigned native builds do not establish release-artifact provenance.
- The complete synthetic backend collection is green; no unresolved engineering test failure remains in this packet.

## Final approval checklist

### Engineering

- [x] Resolve or intentionally update all 15 failing HTTP integration assertions; complete synthetic result is 747 passed, 8 intentional skips, and 0 failures.
- [ ] Confirm whether a new binary is required. If yes, increment build identifiers, create signed store artifacts, record hashes/provenance, and run authorized device tests.
- [ ] If a new binary is required, perform Android and iOS physical-device smoke tests for sign-in, reunion creation, private invitation/RSVP, deletion, push permission behavior, and restore purchases without enabling checkout.
- [ ] Verify RevenueCat/Stripe products and fail-closed pricing behavior without enabling subscription checkout.

### Owner/legal/privacy

- [ ] Confirm encryption in transit for MongoDB, hosting, analytics, email, push, RevenueCat, store, and optional AI paths.
- [ ] Confirm processor contracts, restricted use, and Google service-provider exclusions; otherwise retain conservative shared-data answers.
- [ ] Confirm Android/iOS crash, performance, and diagnostic collection.
- [ ] Confirm GTM, GA, and PostHog consent, identity, IP, autocapture, replay, retention, regional processing, and cross-company use.
- [ ] Confirm provider retention/deletion, backup/log retention, billing retention, and deletion wording.
- [ ] Approve children/minor treatment, lawful basis, consent/opt-out, sale/share, tracking, and retention language.
- [ ] Approve the exact Google Data Safety answers and Apple App Privacy answers in this packet.

### Store preparation

- [ ] Sign into App Store Connect and inspect the current fields read-only before editing.
- [ ] Select Google's non-generative AI declaration for the canonical screenshots.
- [ ] Add Google and Apple OAuth as Play account-creation methods.
- [ ] Upload the canonical five Google phone, five iPhone, and five iPad screenshots only after all prior gates clear.
- [ ] Verify the exact metadata, categories, URLs, release notes, support contact, and build treatment.
- [ ] Explicitly accept publication timing with Google Managed Publishing off.
- [ ] Obtain one explicit final owner approval.

## Final outcome

**ENGINEERING GATES CLEARED — PRIVACY/STORE APPROVAL STILL REQUIRED — NOTHING SUBMITTED**

Remaining non-engineering gates: unproven production encryption, diagnostics, analytics, processor-contract, shared-data, retention/deletion, minors/consent, and tracking facts; Apple console sign-in; Google Data Safety completion; unset Play AI-asset declaration; screenshots not uploaded; live pricing-provider verification; signed artifact/device verification if a new binary is required; console-version/publication reconciliation; and explicit final owner approval.
