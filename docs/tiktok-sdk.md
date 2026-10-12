# TikTok App Events SDK (native apps)

Ad attribution for TikTok App Promotion campaigns (Keep The Record).
Native iOS and Android only; the web build is untouched.

## What is wired

| Event | When | Where |
|---|---|---|
| Install, app launch | automatic | native SDK |
| `Registration` | `community_activated` (the same moment Meta counts) | `src/lib/analytics.js` |
| `Subscribe` | a native store purchase grants an entitlement | `src/lib/revenuecat.js` |

TikTok receives event names only, plus product id, price and currency on
`Subscribe`. No user identity and no family content is sent.

JS wrapper: `frontend/src/lib/tiktokEvents.js`. Native halves:
`frontend/ios/App/App/AppDelegate.swift` (`TikTokEventsPlugin`) and
`frontend/android/app/src/main/java/com/ubuntumarket/kindred/TikTokEventsPlugin.java`.

## IDs and secrets

The TikTok App IDs are committed in `tiktokEvents.js`. The App Secrets are not.
Without a secret the SDK is never started and nothing is sent.

Set these in the environment of the machine that runs `npm run build`
(Xcode Cloud: a secret environment variable on the workflow):

```
REACT_APP_TIKTOK_APP_SECRET_IOS=<secret>
REACT_APP_TIKTOK_APP_SECRET_ANDROID=<secret>
```

## After pulling this change

```bash
cd frontend && npm ci --legacy-peer-deps && npm run build && npx cap sync
cd ios/App && pod install
```

## Store paperwork this triggers

- **iOS:** the app now shows Apple's tracking prompt shortly after launch (only
  in builds that carry the secret). App Store Connect > App Privacy must
  declare data used for tracking (identifiers, purchases, usage data).
- **Android:** the SDK adds the `com.google.android.gms.permission.AD_ID`
  permission. Play Console > App content > Advertising ID must be answered
  "Yes", and the Data safety form updated to match.

## Verifying

TikTok Events Manager > the app > **Test event**. Run a build with the secret,
activate a community and buy a tier in sandbox, and confirm `Registration` and
`Subscribe` arrive. Native Android and iOS Debug builds enable TikTok's SDK
Test Event mode even though Capacitor embeds a production React bundle; release
builds do not.

## October 11, 2026 rebuild handoff

Local, not yet shipped: the iOS plugin now creates its TikTok configuration and
initializes the SDK on `DispatchQueue.main`. Capacitor invokes plugin methods
on a background bridge queue; the SDK schedules upload/session timers on the
calling thread's run loop. ATT requests are also dispatched to the main queue.
Debug/test mode, the ATT delay, and missing-secret safeguards are unchanged.

Local verification: all 22 frontend test suites / 157 tests pass, including
source guards for main-queue initialization and ATT. The unsigned Release iOS
simulator build in a disposable copy exited successfully and produced an app
binary for arm64 and x86_64. Third-party SDK/compiler diagnostics remain; this
is compilation evidence, not signed-device or production-delivery verification.

This addresses the observed timer-threading defect; it is not proof that TikTok
has accepted an event. Before submitting the next builds:

- Privately verify each compiled artifact's platform-specific TikTok App ID and
  secret against its corresponding Events Manager source. Report matches only;
  never print credentials or compiled-bundle snippets.
- Sync the rebuilt frontend so the mobile billing separation and Today recovery
  changes are included, not the previous embedded JavaScript bundle.
- Confirm initialization and a timed upload on a device. Debug events should
  appear in Test event; production verification requires a non-test event.
- Confirm an event API acceptance response or an event in Events Manager before
  declaring delivery fixed. Initialization/remote-switch logs alone do not prove it.
- Keep store submission and publication separate from build verification.
