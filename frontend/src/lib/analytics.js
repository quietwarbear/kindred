import posthog from "posthog-js";

// Shared Ubuntu Markets PostHog project (EU). phc_ tokens are public
// client-side tokens. Every event carries product: "kindred" so the one
// project can be segmented per app (Legacy Table, Ile Ubuntu, Kindred,
// marketing site).
const POSTHOG_KEY = "phc_m3uewVirngKNvpwdZ6DYkwMaWXjCscBf5iPwCSpJGm68";
const POSTHOG_HOST = "https://eu.i.posthog.com";

export function initAnalytics() {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    capture_pageview: true,
    autocapture: true,
  });
  posthog.register({ product: "kindred" });
}

// Tie events to the backend user id (never email as the identifier).
export function identifyUser(user) {
  if (!user?.id) return;
  posthog.identify(String(user.id), {
    auth_provider: user.auth_provider || null,
  });
}

// Clear identity on logout so the next login isn't merged.
export function resetAnalytics() {
  posthog.reset();
}

export function trackEvent(name, properties = {}) {
  posthog.capture(name, properties);
}
