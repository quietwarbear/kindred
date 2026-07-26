import posthog from "posthog-js";

// Shared Ubuntu Markets PostHog project (EU). phc_ tokens are public
// client-side tokens. Every event carries product: "kindred" so the one
// project can be segmented per app (Legacy Table, Ile Ubuntu, Kindred,
// marketing site).
const POSTHOG_KEY = "phc_m3uewVirngKNvpwdZ6DYkwMaWXjCscBf5iPwCSpJGm68";
const POSTHOG_HOST = "https://eu.i.posthog.com";

export const isSensitiveInvitationRoute = () => (
  typeof window !== "undefined"
  && /^\/rsvp\/[^/]+(?:\/|$)/i.test(window.location.pathname)
);

const analyticsSuppressed = () => (
  process.env.REACT_APP_DISABLE_ANALYTICS === "true"
  || (
    typeof window !== "undefined"
    && (
      window.location.hostname === "127.0.0.1"
      || (
        window.location.hostname === "localhost"
        && Boolean(window.location.port)
      )
    )
  )
  || isSensitiveInvitationRoute()
);

export const redactInvitationPaths = (value) => {
  if (typeof value === "string") {
    return value.replace(/(\/rsvp\/)[^/?#\s]+/gi, "$1[redacted]");
  }
  if (Array.isArray(value)) return value.map(redactInvitationPaths);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, redactInvitationPaths(item)])
    );
  }
  return value;
};

export const sanitizeAnalyticsEvent = (event) => {
  if (!event?.properties) return event;
  return {
    ...event,
    properties: redactInvitationPaths(event.properties),
  };
};

export function initAnalytics() {
  if (analyticsSuppressed()) return false;
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    capture_pageview: true,
    autocapture: true,
    mask_all_text: true,
    mask_all_element_attributes: true,
    before_send: sanitizeAnalyticsEvent,
  });
  posthog.register({ product: "kindred" });
  return true;
}

// Tie events to the backend user id (never email as the identifier).
export function identifyUser(user) {
  if (!user?.id || analyticsSuppressed()) return;
  posthog.identify(String(user.id), {
    auth_provider: user.auth_provider || null,
  });
}

// Clear identity on logout so the next login isn't merged.
export function resetAnalytics() {
  if (analyticsSuppressed()) return;
  posthog.reset();
}

export function trackEvent(name, properties = {}) {
  if (analyticsSuppressed()) return;
  posthog.capture(name, properties);
}

export const REUNION_EVENTS = Object.freeze([
  "reunion_start_clicked",
  "reunion_draft_created",
  "reunion_preview_viewed",
  "invite_created",
  "invite_link_copied",
  "invite_opened",
  "rsvp_completed",
  "guest_account_started",
  "community_activated",
  "memory_prompt_completed",
  "reunion_multiday_enabled",
  "itinerary_activity_created",
  "itinerary_activity_published",
  "activity_rsvp_updated",
  "itinerary_viewed",
  "activity_roster_viewed",
]);

const SAFE_REUNION_PROPERTY_KEYS = new Set([
  "source",
  "status",
  "invite_count",
  "verified_invite_count",
  "accepted_count",
  "days_since_created",
  "reunion_days",
  "activity_count",
  "venue_assigned",
  "activity_position",
  "day_number",
  "response_category",
  "actor_type",
]);

// Acquisition events must never contain family content, names, emails,
// invitation tokens, provider identifiers, or community identifiers.
export function trackReunionEvent(name, properties = {}) {
  if (analyticsSuppressed() || !REUNION_EVENTS.includes(name)) return;
  const safeProperties = Object.fromEntries(
    Object.entries(properties).filter(
      ([key, value]) =>
        SAFE_REUNION_PROPERTY_KEYS.has(key)
        && (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    )
  );
  posthog.capture(name, safeProperties);
}
