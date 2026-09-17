// Sentry error monitoring for the web build and the Capacitor native shells.
// Errors and light performance tracing only — NO Session Replay, because
// replay records the screen/DOM and Kindred carries private family content
// (photos, stories, invite details). No-op unless REACT_APP_SENTRY_DSN is set
// at build time, mirroring how the backend is gated on SENTRY_DSN.
import * as Sentry from "@sentry/capacitor";
import * as SentryReact from "@sentry/react";

export function initSentry() {
  const dsn = (process.env.REACT_APP_SENTRY_DSN || "").trim();
  if (!dsn) return;
  // A malformed DSN must never take down the app; monitoring is optional.
  try {
    Sentry.init(
      {
        dsn,
        environment: process.env.REACT_APP_SENTRY_ENVIRONMENT || "production",
        release: process.env.REACT_APP_SENTRY_RELEASE || undefined,
        tracesSampleRate: 0.1,
        sendDefaultPii: false,
        // Third-party noise filter: some in-app browsers and extensions inject
        // scripts into the page; when those crash (xbrowser/swbrowser bridge
        // globals and friends) the errors land in OUR project with no app
        // frames. Drop the known injected globals and every browser-extension
        // URL scheme. Real app errors are unaffected.
        ignoreErrors: [
          /\\b(xbrowser|swbrowser|zaloJSV2|__gCrWeb|__firefox__|_AutofillCallbackHandler|instantSearchSDKJSBridgeClearHighlight)\\b/,
        ],
        denyUrls: [
          /^chrome-extension:\\/\\//i,
          /^moz-extension:\\/\\//i,
          /^safari-(web-)?extension:\\/\\//i,
        ],
      },
      SentryReact.init,
    );
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn("[Kindred] Sentry init skipped:", err?.message || err);
  }
}
