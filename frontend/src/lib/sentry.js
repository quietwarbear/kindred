// Sentry error monitoring for the web build and the Capacitor native shells.
// Errors and light performance tracing only — NO Session Replay, because
// replay records the screen/DOM and Kindred carries private family content
// (photos, stories, invite details). No-op unless REACT_APP_SENTRY_DSN is set
// at build time, mirroring how the backend is gated on SENTRY_DSN.
import * as Sentry from "@sentry/capacitor";
import * as SentryReact from "@sentry/react";

export function initSentry() {
  const dsn = process.env.REACT_APP_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init(
    {
      dsn,
      environment: process.env.REACT_APP_SENTRY_ENVIRONMENT || "production",
      release: process.env.REACT_APP_SENTRY_RELEASE || undefined,
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
    },
    SentryReact.init,
  );
}
