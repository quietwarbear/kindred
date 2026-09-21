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
    || /^\/sso\/?$/i.test(window.location.pathname)
    || /^\/family\/join\/?$/i.test(window.location.pathname)
    || /^\/(?:home|dashboard)\/?$/i.test(window.location.pathname)
    || /^\/proposals(?:\/|$)/i.test(window.location.pathname)
    || /^\/reunion\/(?:activate|command|hub|memories|recap)\//i.test(window.location.pathname)
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
  || (typeof window !== "undefined" && /^\/sso\/?$/i.test(window.location.pathname))
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
    && ["$autocapture", "$snapshot", "$pageview"].includes(event?.event)
  ) return null;
  if (!event?.properties) return event;
  return {
    ...event,
    properties: redactInvitationPaths(event.properties),
  };
};

// The GA4 browser client id, for the backend to attach to server-side
// conversions (sign_up, begin_checkout, purchase). Those fire from webhooks,
// long after the tab may be gone; handing the backend this id is what makes a
// purchase land in the same GA4 session — and so the same campaign — as the
// click that produced it. Without it the sale still counts, but it opens its
// own session and the ad that earned it gets no credit.
//
// Read straight from the `_ga` cookie rather than gtag('get'), which is async
// and races the first form submit. The backend trims the GA1.1. prefix.
// Returns "" when the tag never loaded (ad blocker, local dev) or on a
// suppressed route — the backend falls back to a synthetic id. Suppression is
// honoured here on purpose: a route we do not track is a route we do not
// hand an identifier for either.
export function gaClientId() {
  if (analyticsSuppressed()) return "";
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)_ga=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

// Meta Pixel. Absent id = the snippet never loads and every Meta call is a
// no-op, matching how the backend gates Sentry and push.
//
// This is the ONLY conversion signal Meta receives. GA4 and Meta are separate
// pipes: the server-side GA4 events (sign_up, begin_checkout, purchase) never
// reach Meta's optimiser, so without this a paid campaign has nothing to aim
// at and buys the cheapest clicks it can find.
const META_PIXEL_ID = process.env.REACT_APP_META_PIXEL_ID || "";

// Kindred's activation funnel -> Meta standard events. Deliberately shallow:
// Meta needs roughly 50 events a week to leave the learning phase, so the
// upper-funnel steps are here to give it volume to optimise on long before
// purchases exist.
//
// Purchase is absent on purpose. Subscriptions complete in the RevenueCat
// webhook, server-side, where the browser cannot see them — that needs the
// Conversions API, not this file.
const META_STANDARD_EVENTS = {
  reunion_start_clicked: "ViewContent",
  reunion_draft_created: "Lead",
  reunion_saved: "Schedule",
  community_activated: "CompleteRegistration",
};

// The Pixel transmits the page URL with every event, and invitation tokens
// live in /rsvp/<token> paths. So the Pixel is not merely silenced on
// sensitive routes — it is never loaded there, because even the script
// request would carry that URL to Meta as a Referer.
const metaPixelForbidden = () => analyticsSuppressed() || isSensitiveContentRoute();

function loadMetaPixel() {
  if (!META_PIXEL_ID || typeof window === "undefined") return;
  if (metaPixelForbidden()) return;
  if (typeof window.fbq === "function") return; // already loaded
  /* eslint-disable */
  !(function (f, b, e, v, n, t, s) {
    if (f.fbq) return;
    n = f.fbq = function () {
      n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
    };
    if (!f._fbq) f._fbq = n;
    n.push = n;
    n.loaded = !0;
    n.version = "2.0";
    n.queue = [];
    t = b.createElement(e);
    t.async = !0;
    t.src = v;
    s = b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t, s);
  })(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");
  /* eslint-enable */
  window.fbq("init", META_PIXEL_ID);
  window.fbq("track", "PageView");
}

// Event NAME only — never properties. Everything this app tracks may carry
// family content, and Meta gets none of it. The standard event name alone is
// what the optimiser needs.
function forwardToMeta(name) {
  const standard = META_STANDARD_EVENTS[name];
  if (!standard) return;
  if (metaPixelForbidden()) return;
  if (typeof window !== "undefined" && typeof window.fbq === "function") {
    window.fbq("track", standard);
  }
}

export function initAnalytics() {
  if (analyticsSuppressed()) return false;
  loadMetaPixel();
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
  "reunion_recap_viewed",
  "reunion_recap_published",
  "reunion_memory_continued",
  "next_gathering_started",
  "gathering_proposal_submitted",
  "gathering_pulse_viewed",
  "gathering_interest_recorded",
  "gathering_proposal_converted",
  "family_today_viewed",
  "family_today_primary_action_shown",
  "family_today_primary_action_selected",
  "reunion_draft_saved",
  "first_invitation_prepared",
  "first_invitation_shared",
  "first_rsvp_received",
  "organizer_return_after_first_rsvp",
  "memory_contribution_completed",
  "family_access_approved",
  "gathering_pulse_completed",
  "next_private_draft_started",
]);

const GATHERING_PROPOSAL_EVENTS = new Set([
  "gathering_proposal_submitted",
  "gathering_pulse_viewed",
  "gathering_interest_recorded",
  "gathering_proposal_converted",
  "gathering_pulse_completed",
]);

const GATHERING_PROPOSAL_CATEGORIES = Object.freeze({
  viewer_role: new Set(["member", "organizer"]),
  proposal_state: new Set(["submitted", "published", "declined", "withdrawn", "converted", "expired", "conflict"]),
  response_category: new Set(["interested", "maybe", "not_available"]),
  next_action_category: new Set(["review_proposal", "respond_to_pulse", "continue_planning", "family_home"]),
});

const safeGatheringProposalProperties = (properties) => Object.fromEntries(
  Object.entries(properties).filter(
    ([key, value]) => typeof value === "string" && GATHERING_PROPOSAL_CATEGORIES[key]?.has(value)
  )
);

const REUNION_RECAP_EVENTS = new Set([
  "reunion_recap_viewed",
  "reunion_recap_published",
  "reunion_memory_continued",
  "next_gathering_started",
]);

const REUNION_RECAP_CATEGORIES = Object.freeze({
  viewer_role: new Set(["member", "organizer"]),
  recap_state: new Set(["not_ready", "ready", "published", "unpublished", "legacy_conflict"]),
  next_action_category: new Set(["memory_capsule", "continue_planning", "family_home"]),
});

const safeReunionRecapProperties = (properties) => Object.fromEntries(
  Object.entries(properties).filter(
    ([key, value]) => typeof value === "string" && REUNION_RECAP_CATEGORIES[key]?.has(value)
  )
);

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
  "family_access_approved",
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

const FAMILY_TODAY_EVENTS = new Set([
  "family_today_viewed",
  "family_today_primary_action_shown",
  "family_today_primary_action_selected",
  "reunion_draft_saved",
  "first_invitation_prepared",
  "first_invitation_shared",
  "first_rsvp_received",
  "organizer_return_after_first_rsvp",
  "memory_contribution_completed",
  "next_private_draft_started",
]);

const FAMILY_TODAY_CATEGORIES = Object.freeze({
  source: new Set(["family_today", "reunion_start", "reunion_activation", "organizer_command_center", "attendee_hub", "memory_capsule", "gathering_invites", "gathering_proposals", "reunion_recap"]),
  viewer_role: new Set(["member", "new_member", "organizer", "host"]),
  lifecycle_state: new Set(["active", "provisional"]),
  action_code: new Set([
    "activate_family_space", "finish_reunion_draft", "prepare_first_invitation",
    "finish_holiday_meal_setup", "prepare_holiday_invitation", "review_holiday_response_gaps",
    "fill_holiday_contribution_gaps", "preserve_holiday_recipe", "review_holiday_recap",
    "complete_holiday_rsvp", "review_holiday_schedule", "claim_holiday_contribution",
    "add_holiday_recipe", "view_holiday_recap",
    "review_family_access_requests", "resolve_rsvp_attention", "complete_command_task",
    "review_recap", "review_gathering_proposal", "continue_converted_draft",
    "open_command_center", "confirm_family_access", "complete_reunion_rsvp",
    "complete_activity_responses", "review_updated_itinerary", "manage_contribution",
    "respond_to_gathering_pulse", "continue_memory_contribution", "view_published_recap",
    "check_family_access_status", "open_family_home",
  ]),
  coarse_elapsed_time: new Set(["same_day", "within_week", "within_month", "later", "unknown"]),
});

const safeFamilyTodayProperties = (properties) => Object.fromEntries(
  Object.entries(properties).filter(
    ([key, value]) => typeof value === "string" && FAMILY_TODAY_CATEGORIES[key]?.has(value)
  )
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
  forwardToMeta(name);
  if (FAMILY_ACTIVATION_EVENTS.has(name)) {
    posthog.capture(name, safeFamilyActivationProperties(properties));
    return;
  }
  if (FAMILY_TODAY_EVENTS.has(name)) {
    posthog.capture(name, safeFamilyTodayProperties(properties));
    return;
  }
  if (FAMILY_ACCESS_EVENTS.has(name)) {
    posthog.capture(name, safeFamilyAccessProperties(properties));
    return;
  }
  if (REUNION_RECAP_EVENTS.has(name)) {
    posthog.capture(name, safeReunionRecapProperties(properties));
    return;
  }
  if (GATHERING_PROPOSAL_EVENTS.has(name)) {
    posthog.capture(name, safeGatheringProposalProperties(properties));
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
