// Sentry error monitoring for the web build and the Capacitor native shells.
// Errors and light performance tracing only — NO Session Replay, because
// replay records the screen/DOM and Kindred carries private family content
// (photos, stories, invite details). No-op unless REACT_APP_SENTRY_DSN is set
// at build time, mirroring how the backend is gated on SENTRY_DSN.
import * as Sentry from "@sentry/capacitor";
import * as SentryReact from "@sentry/react";

function hasInjectedMetaFrame(event) {
  return (event?.exception?.values || []).some((exception) =>
    (exception?.stacktrace?.frames || []).some((frame) =>
      String(frame?.filename || "").includes("iabjs://"),
    ),
  );
}

function isHonorBrowserAdTimeout(event) {
  const serialized = event?.extra?.__serialized__;
  return (
    String(serialized?.code) === "30013" &&
    /ad loading process exceeded the timeout period/i.test(
      String(serialized?.message || ""),
    )
  );
}

// Sentry applies ignoreErrors to exception messages, but some mobile browsers
// inject code whose identifying evidence lives only in the stack filename or
// serialized rejection payload. Keep this filter deliberately narrow so real
// Kindred application failures still reach Sentry.
export function filterInjectedBrowserNoise(event) {
  if (hasInjectedMetaFrame(event) || isHonorBrowserAdTimeout(event)) {
    return null;
  }
  return event;
}

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
        // Third-party noise filter: in-app browsers (Meta's Android IAB,
        // various Android "x/sw browser" webviews) and extensions inject
        // scripts into the page; when those crash the errors land in OUR
        // project with no app frames. Drop the known injected-script
        // signatures and every browser-extension URL scheme. Real app
        // errors are unaffected.
        ignoreErrors: [
          /\b(xbrowser|swbrowser|zaloJSV2|__gCrWeb|__firefox__|_AutofillCallbackHandler|instantSearchSDKJSBridgeClearHighlight)\b/,
          // Meta's Android in-app browser: its injected iabjs:// performance
          // logger throws once the page is left and its Java bridge is gone.
          /Java object is gone/,
          // Service-worker UPDATE check dying on flaky mobile networks
          // (common inside the Facebook webview). Deliberately narrow: a
          // real sw.js outage says "bad HTTP response code" and still alerts.
          /Failed to update a ServiceWorker[^]*unknown error occurred when fetching/,
        ],
        denyUrls: [
          /^chrome-extension:\/\//i,
          /^moz-extension:\/\//i,
          /^safari-(web-)?extension:\/\//i,
        ],
        beforeSend: filterInjectedBrowserNoise,
      },
      SentryReact.init,
    );
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn("[Kindred] Sentry init skipped:", err?.message || err);
  }
}
