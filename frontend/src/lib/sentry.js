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

function getUserAgent(event) {
  const headers = event?.request?.headers;
  if (Array.isArray(headers)) {
    return String(
      headers.find(([name]) => String(name).toLowerCase() === "user-agent")?.[1] ||
        "",
    );
  }

  const entry = Object.entries(headers || {}).find(
    ([name]) => name.toLowerCase() === "user-agent",
  );
  return String(entry?.[1] || "");
}

function isFacebookBrowser(event) {
  return (
    String(event?.contexts?.browser?.name || "").toLowerCase() === "facebook" ||
    /\bFB_IAB\//i.test(getUserAgent(event))
  );
}

function getExceptionFrames(exception) {
  return exception?.stacktrace?.frames || [];
}

function isAnonymousOrDocumentFrame(frame) {
  const filename = String(frame?.filename || "");
  return (
    filename === "app:///<anonymous>" ||
    /^https:\/\/(?:www\.)?heykindred\.org\/?$/i.test(filename)
  );
}

function isPaidMetaLandingRequest(event) {
  return /(?:[?&]fbclid=|[?&]utm_source=fb(?:&|$))/i.test(
    String(event?.request?.url || ""),
  );
}

const META_JAVA_BRIDGE_FAILURE =
  /error invoking postMessage: (?:Java bridge method invocation error|Java exception was raised during method invocation)/i;

function isMetaJavaBridgeFailure(event) {
  if (!isFacebookBrowser(event)) return false;

  return (event?.exception?.values || []).some((exception) => {
    const frames = getExceptionFrames(exception);
    const value = String(exception?.value || "");
    return (
      META_JAVA_BRIDGE_FAILURE.test(value) &&
      frames.length > 0 &&
      frames.every(
        (frame) => String(frame?.filename || "") === "app:///<anonymous>",
      )
    );
  });
}

function isMetaInjectedRuntimeFailure(event) {
  if (!isFacebookBrowser(event)) return false;

  return (event?.exception?.values || []).some((exception) => {
    const value = String(exception?.value || "");
    const frames = getExceptionFrames(exception);
    if (!frames.length || !frames.every(isAnonymousOrDocumentFrame)) {
      return false;
    }

    if (/TTRCCallbacks\.onDomContentLoaded is not a function/i.test(value)) {
      return frames.every(
        (frame) => String(frame?.filename || "") === "app:///<anonymous>",
      );
    }

    if (/window\.webkit\.messageHandlers/i.test(value)) {
      return (
        isPaidMetaLandingRequest(event) &&
        frames.every((frame) =>
          /^https:\/\/(?:www\.)?heykindred\.org\/?$/i.test(
            String(frame?.filename || ""),
          ),
        )
      );
    }

    if (/^Unexpected end of input$/i.test(value)) {
      return (
        isPaidMetaLandingRequest(event) &&
        frames.every(
          (frame) =>
            /^https:\/\/(?:www\.)?heykindred\.org\/?$/i.test(
              String(frame?.filename || ""),
            ) && Number(frame?.lineno || 0) >= 36,
        )
      );
    }

    return false;
  });
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
  if (
    hasInjectedMetaFrame(event) ||
    isMetaJavaBridgeFailure(event) ||
    isMetaInjectedRuntimeFailure(event) ||
    isHonorBrowserAdTimeout(event)
  ) {
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
