# Kindred reunion-first release readiness packet

**Prepared:** August 9, 2026  
**Publication state:** Repository and evidence work only. No deployment, store review, release, or publication action is authorized by this packet.

## Executive status

Kindred's reunion-first product foundation is substantially implemented. The original growth audit recommended a narrow acquisition wedge (plan a family reunion), one coherent Plan / Join / Preserve front door, no-account RSVP, an organizer command center, a guest-to-family path, post-reunion continuity, trustworthy store presentation, and monetization only after activation evidence. Releases 1 through 5 are represented in the application and synthetic browser verification. Release 6 remains deliberately gated and checkout remains paused.

The repository's engineering verification gates are cleared and it is ready for owner/legal privacy decisions and store-draft preparation, but it is **not ready for submission**. Store submission remains blocked by production processor verification, final privacy declarations, provider pricing checks, any required signed artifact/device verification, and explicit final approval.

## Recommendation-to-delivery matrix

| Growth-audit recommendation | Current status | Repository evidence | Remaining gate |
|---|---|---|---|
| Reunion-first positioning | Complete in product and draft copy | Plan / Join / Preserve entry points, reunion-first store copy, public reunion routes | Apply already-approved drafts in both consoles only after privacy gates clear |
| One coherent activation path | Complete | Intent-first reunion draft and activation flow; no provider-specific product detour | Measure production conversion after release |
| No-account private RSVP | Complete | Fragment-based private RSVP route and synthetic guest verification | Confirm live delivery-provider configuration without exposing invitation credentials |
| Multiday reunion planning | Complete | Reunion itinerary, activities, attendance, locations, and organizer controls | Authorized native-device smoke test |
| Organizer command center | Complete | RSVP totals, unanswered invitations, attendance-by-day, roles, potluck, and planning status | Production admin/provider configuration where applicable |
| Guest-to-family conversion | Complete and approval-gated | Attendee hub and organizer-approved guest access | Measure acceptance and downstream organizer creation |
| Post-reunion continuity | Complete | Memory prompt, recap, next-gathering continuity, and proposals | Measure memory contribution and repeat-gathering behavior |
| Trustworthy support identity | Complete in repository | `support@heykindred.org` is the canonical public support address | Console contact publication still requires separate approval |
| Credible mobile store creative | Complete in canonical evidence set | Five Google phone, five iPhone 6.9-inch, and five iPad 13-inch synthetic screenshots plus manifest | Upload only after privacy gates and final approval |
| Monetization after demonstrated value | Gate respected | Catalog and RevenueCat paths fail closed; checkout remains paused | Verify Stripe/RevenueCat products and activation evidence before restoring billing |
| Funnel measurement | Implemented; production behavior unconfirmed | Privacy-safe activation events and synthetic commercial-readiness verification | Inspect live GTM, GA, and PostHog consent, identity, retention, and regional behavior |
| Research before monetization | Not complete | Interview and experiment guidance remains documented | Conduct organizer interviews and validate willingness to pay |

## Safe engineering correction completed in this pass

The backend already allows Apple and Google accounts to use authenticated account deletion without a password. The Settings screen only recognized Google as passwordless, which made deletion unavailable to Apple-authenticated users. The frontend now uses a single tested provider rule for both Apple and Google. Password accounts still require the existing password confirmation.

This does not broaden deletion authority or change the backend deletion cascade. Ubuntu SSO and any other provider remain subject to the current backend policy until their security model is explicitly reviewed.

The subsequent engineering-gate pass also corrected three narrow backend defects: malformed bearer tokens now return a generic HTTP 401 instead of escaping as HTTP 500; attachment payloads use the frontend's `name`/`data_url` contract while accepting legacy aliases; and the community overview response model preserves its existing privacy-safe user projection. Member RSVP, volunteer, and potluck projections remain privacy-limited, Seedling and paid-feature gates remain enforced, and checkout remains disabled.

## Canonical screenshot package

The canonical campaign is `frontend/store-assets`, generated from the real production frontend build with disposable in-process API responses and synthetic Rivers-family records.

Ordered story:

1. Start a family reunion.
2. Build a multiday itinerary.
3. Share one private RSVP; relatives can answer without an account.
4. See what needs attention.
5. Keep the stories.

Validated exports:

- Google phone: five RGB PNG files, 1080 x 1920, no alpha.
- Apple iPhone 6.9-inch: five RGB PNG files, 1320 x 2868, no alpha.
- Apple iPad 13-inch: five RGB PNG files, 2064 x 2752, no alpha.
- `frontend/store-assets/manifest.json` records all 15 dimensions and SHA-256 hashes.
- The hashes attest the fixed canonical upload files. Fresh Chromium captures pass the same structural and clipping checks but are not promised to be byte-identical across browser runs.
- The Play and iPhone sets were visually inspected for readable captions and cut-off text after regeneration.
- The generator blocks external requests and rejects visible email, URL, reviewer, demo, staging, development, token, credential, and other non-store markers.
- The images are deterministic browser captures and caption composition. No generative-AI image or text model was used to create or edit them.

The older untracked Bell-family exports under `docs/store-screenshots` are not the canonical upload set and were not modified.

## Privacy and data-safety disposition

The repository supports these conclusions:

1. **Kindred collects data.** A public or console answer of “No data collected” conflicts with account, reunion, RSVP, content, purchase, device, analytics, and communication paths.
2. **Identity linkage must be reconciled.** Account data, user content, purchases, push tokens, support communications, and identified PostHog activity are linked to a user in the engineering map. Apple's current “Data Not Linked to You” presentation requires review.
3. **OAuth is an account-creation method.** Google and Apple sign-in are supported and should be included in the Google account-creation declaration.
4. **Screenshot AI provenance is resolved.** The canonical campaign did not use generative AI.

The repository cannot prove these production/legal facts, so they remain submission blockers:

- Whether every live MongoDB, analytics, email, push, RevenueCat, hosting, and optional AI-provider path is encrypted in transit.
- Whether every processor transfer satisfies Google's service-provider exclusion. Until contracts and use restrictions are confirmed, do not assume “No data shared.”
- Whether crash, performance, or other diagnostics are collected by the production Android/iOS builds and hosting/mobile consoles.
- Live GTM/GA/PostHog consent, autocapture, identity, IP handling, retention, cross-company use, and regional-transfer behavior.
- Provider retention and deletion for backups, logs, payments, email, push, analytics, AI processing, and legally retained records.
- Legal treatment of minors, lawful basis, consent/opt-out, sale/share, retention, and deletion language.

Do not promise complete deletion within 30 days. The current endpoint has ownership-transfer rules and does not prove deletion of every shared record, newer subscription/service record, provider log, or backup.

## Verification evidence

Passed in this workspace:

- Frontend unit tests: 11 suites, 59 tests.
- Production frontend build and prerender: `/`, `/reunion/start`, `/pricing`, `/privacy`, `/terms`, and `/support`.
- Ten synthetic browser journeys: commercial readiness, family-space activation, Family Today, gathering proposals, guest family access, organizer command center, attendee hub, memory capsule, reunion recap, and Thanksgiving pilot readiness.
- Store asset generation and structural validation: 15 images.
- Python backend syntax compilation.
- Git whitespace/error check.

Completed in the subsequent engineering-gate pass:

- Pytest was installed only in a temporary virtual environment. The complete backend collection contained 755 tests with no collection errors. The repository/loopback run passed 732 with 8 intentional skips and zero failures; all 15 disposable MongoDB tests passed separately. Aggregate result: 747 passed, 8 skipped, 0 failed.
- All 15 previously documented HTTP disagreements were reproduced and classified. Three narrow implementation defects were fixed; intentional privacy projections, response envelopes, subscription gates, retired routes, and provider-disabled behavior were preserved and their stale tests updated.
- Frontend verification passed again: 11 suites, 59 tests, production build, and prerender of `/`, `/reunion/start`, `/pricing`, `/privacy`, `/terms`, and `/support`.
- The canonical 15-image manifest passed hash, dimension, PNG, and no-alpha checks. A fresh disposable scripted render generated and visually validated all 15 frames without generative AI or external provider traffic.
- Android Capacitor sync and debug compilation passed in a disposable copy. iOS Capacitor sync, CocoaPods installation, and an unsigned generic-device build also passed in disposable locations.
- All 15 canonical screenshots passed hash, dimension, RGB/no-alpha, sensitive-marker, and visual-clipping validation.

Still not completed:

- Signed Android AAB or iOS archive provenance and authorized physical-device smoke tests if a new binary is required.
- Live production/provider-console verification and owner/legal privacy confirmation.

## Store and release boundary

Before either store can be submitted:

- [ ] Confirm all production encryption-in-transit paths.
- [ ] Confirm processor contracts and Google's shared-data treatment.
- [ ] Inspect production Android/iOS diagnostics collection.
- [x] Record canonical screenshot provenance as non-generative AI.
- [ ] Add Google and Apple OAuth to the Google account-creation methods.
- [ ] Reconcile Google Data Safety with the engineering matrix.
- [ ] Reconcile Apple identity linkage, tracking, Device ID, diagnostics, and communications declarations.
- [ ] Verify live GTM/GA/PostHog configuration and legal consent requirements.
- [ ] Verify Stripe and RevenueCat product configuration.
- [ ] Run authorized native builds and device smoke tests.
- [ ] Sign into App Store Connect and prepare, but do not submit, the Apple draft.
- [ ] Add the canonical screenshots to both store drafts.
- [ ] Obtain one explicit final approval covering the exact metadata, privacy answers, screenshots, build, release notes, and publication behavior.

Managed Publishing is off in Google Play. Do not place changes into review until publication timing is explicitly accepted. Do not change live release notes or contact information through a direct publish action as part of draft preparation.

## Audience expansion after the release gate

Once the store release is privacy-complete and approved, the next growth work should stay reunion-first:

1. Measure store impression-to-install, first-open-to-reunion-start, saved reunion plus first invitation, invitation-open-to-RSVP, organizer return after first RSVP, post-event memory contribution, and guest-to-new-organizer conversion.
2. Run small store-listing experiments on the first screenshot and short description; do not broaden the promise into a generic community platform.
3. Publish reunion-planning pages and practical reunion templates that lead directly to `/reunion/start`.
4. Conduct organizer interviews before enabling billing; test episodic reunion pricing and only restore checkout after activation and retention evidence clears the documented gate.
5. Use invitation and recap moments as the primary referral loop while keeping every family space private by default.

## Final decision

**Ready for continued repository review and store-draft preparation: yes.**  
**Ready for store submission or publication: no.**

The next authorized action is to resolve the owner/legal questionnaire, verify live provider facts through authorized read-only evidence, and prepare both store drafts with the canonical five-frame assets. If the stores require a new binary, signed artifact provenance and device testing must be completed first. Submission remains a separate final approval.
