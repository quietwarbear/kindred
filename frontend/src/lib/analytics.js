import posthog from "posthog-js";

// Shared Ubuntu Markets PostHog project (EU). phc_ tokens are public
// client-side tokens. Every event carries product: "kindred" so the one
// project can be segmented per app (Legacy Table, Ile Ubuntu, Kindred,
// marketing site).
const POSTHOG_KEY = "phc_m3uewVirngKNvpwdZ6DYkwMaWXjCscBf5iPwCSpJGm68";
const POSTHOG_HOST = "https://eu.i.posthog.com";

export const isSensitiveInvitationRoute = () => (
  typeof window !== "undefined"
  && (
    /^\/rsvp\/[^/]+(?:\/|$)/i.test(window.location.pathname)
    || (
      /^\/rsvp\/?$/i.test(window.location.pathname)
      && Boolean(window.location.hash)
    )
  )
);

export const isSensitiveContentRoute = () => (
  typeof window !== "undefined"
  && (
    /^\/family\/activate\/?$/i.test(window.location.pathname)
    || /^\/family\/join\/?$/i.test(window.location.pathname)
    || /^\/reunion\/(?:activate|command|hub|memories)\//i.test(window.location.pathname)
  )
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
    return value
      .replace(/(\/rsvp\/)[^/?#\s]+/gi, "$1[redacted]")
      .replace(/(\/rsvp)#([^?\s]+)/gi, "$1#[redacted]");
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
  if (
    isSensitiveContentRoute()
    && ["$autocapture", "$snapshot"].includes(event?.event)
  ) return null;
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
  "organizer_intent_confirmed",
  "reunion_saved",
  "reunion_preview_viewed",
  "invite_created",
  "invite_link_copied",
  "invite_opened",
  "rsvp_completed",
  "guest_account_started",
  "community_activated",
  "memory_prompt_completed",
  "memory_prompt_started",
  "reunion_multiday_enabled",
  "itinerary_activity_created",
  "itinerary_activity_published",
  "activity_rsvp_updated",
  "itinerary_viewed",
  "activity_roster_viewed",
  "command_center_viewed",
  "next_action_viewed",
  "next_action_completed",
  "invitation_share_initiated",
  "reminder_preflight_passed",
  "reminder_preflight_failed",
  "planning_team_setup_started",
  "planning_team_setup_completed",
  "organizer_returned_after_first_rsvp",
  "reunion_hub_viewed",
  "attendee_next_action_viewed",
  "contribution_claimed",
  "contribution_released",
  "reunion_capsule_viewed",
  "memory_contribution_started",
  "memory_contribution_saved",
  "memory_contribution_withdrawn",
  "reunion_capsule_next_action_viewed",
  "family_space_activation_viewed",
  "family_space_activation_deferred",
  "family_space_activated",
  "family_space_activation_conflict",
  "guest_family_access_started",
  "guest_family_access_submitted",
  "guest_family_access_status_viewed",
  "guest_family_access_cancelled",
  "guest_family_access_decided",
]);

const FAMILY_ACTIVATION_EVENTS = new Set([
  "family_space_activation_viewed",
  "family_space_activation_deferred",
  "family_space_activated",
  "family_space_activation_conflict",
]);

const FAMILY_ACCESS_EVENTS = new Set([
  "guest_family_access_started",
  "guest_family_access_submitted",
  "guest_family_access_status_viewed",
  "guest_family_access_cancelled",
  "guest_family_access_decided",
]);

const FAMILY_ACCESS_CATEGORIES = Object.freeze({
  source: new Set(["public_rsvp", "family_access_boundary", "organizer_command_center"]),
  request_state: new Set(["none", "pending", "approved", "declined", "cancelled", "expired", "conflict"]),
  decision: new Set(["approved", "declined"]),
});

const safeFamilyAccessProperties = (properties) => Object.fromEntries(
  Object.entries(properties).filter(
    ([key, value]) => typeof value === "string" && FAMILY_ACCESS_CATEGORIES[key]?.has(value)
  )
);

const FAMILY_ACTIVATION_CATEGORIES = Object.freeze({
  source: new Set(["family_activation", "organizer_command_center"]),
  readiness_category: new Set(["ready", "not_ready", "active", "legacy_unchanged", "unknown"]),
  result: new Set(["success", "conflict", "deferred", "failure"]),
  elapsed_day_bucket: new Set(["0_1", "2_7", "8_30", "31_plus", "unknown"]),
});

const FAMILY_ACTIVATION_COUNT_KEYS = new Set([
  "verified_invite_count",
  "accepted_count",
  "non_host_participation_count",
  "reunion_count",
]);

const safeFamilyActivationProperties = (properties) => Object.fromEntries(
  Object.entries(properties).filter(([key, value]) => {
    if (FAMILY_ACTIVATION_CATEGORIES[key]) {
      return typeof value === "string" && FAMILY_ACTIVATION_CATEGORIES[key].has(value);
    }
    return FAMILY_ACTIVATION_COUNT_KEYS.has(key)
      && Number.isInteger(value)
      && value >= 0
      && value <= 1000;
  })
);

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
  "action_code",
  "result",
  "planning_team_state",
  "reminder_code",
  "return_reason",
]);

// Acquisition events must never contain family content, names, emails,
// invitation tokens, provider identifiers, or community identifiers.
export function trackReunionEvent(name, properties = {}) {
  if (analyticsSuppressed() || !REUNION_EVENTS.includes(name)) return;
  if (FAMILY_ACTIVATION_EVENTS.has(name)) {
    posthog.capture(name, safeFamilyActivationProperties(properties));
    return;
  }
  if (FAMILY_ACCESS_EVENTS.has(name)) {
    posthog.capture(name, safeFamilyAccessProperties(properties));
    return;
  }
  const safeProperties = Object.fromEntries(
    Object.entries(properties).filter(
      ([key, value]) =>
        SAFE_REUNION_PROPERTY_KEYS.has(key)
        && (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    )
  );
  posthog.capture(name, safeProperties);
}
