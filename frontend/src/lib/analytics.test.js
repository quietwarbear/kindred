jest.mock("posthog-js", () => ({
  __esModule: true,
  default: {
    capture: jest.fn(),
    identify: jest.fn(),
    init: jest.fn(),
    register: jest.fn(),
    reset: jest.fn(),
  },
}));

import posthog from "posthog-js";
import {
  initAnalytics,
  identifyUser,
  isSensitiveInvitationRoute,
  redactInvitationPaths,
  REUNION_EVENTS,
  resetAnalytics,
  sanitizeAnalyticsEvent,
  trackEvent,
  trackReunionEvent,
} from "./analytics";

beforeEach(() => {
  Object.values(posthog).forEach((mock) => mock.mockClear());
  window.history.replaceState({}, "", "/");
});

test("declares every deliberate reunion funnel event", () => {
  expect(REUNION_EVENTS).toEqual([
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
  ]);
});

test("drops sensitive and unapproved analytics properties", () => {
  trackReunionEvent("rsvp_completed", {
    source: "public_rsvp",
    status: "going",
    email: "private@example.com",
    token: "private-token",
    gathering_name: "Private Family Reunion",
  });
  expect(posthog.capture).toHaveBeenCalledWith("rsvp_completed", {
    source: "public_rsvp",
    status: "going",
  });
});

test("allows itinerary counts and categories but drops itinerary content", () => {
  trackReunionEvent("activity_rsvp_updated", {
    activity_count: 4,
    day_number: 2,
    venue_assigned: true,
    response_category: "coming",
    actor_type: "invitee",
    activity_title: "Private dinner",
    venue_address: "Private address",
    attendee_name: "Private Person",
    invitation_token: "private-token",
    notes: "Private accessibility note",
  });
  expect(posthog.capture).toHaveBeenCalledWith("activity_rsvp_updated", {
    activity_count: 4,
    day_number: 2,
    venue_assigned: true,
    response_category: "coming",
    actor_type: "invitee",
  });
});

test("allows privacy-safe activation evidence counts", () => {
  trackReunionEvent("community_activated", {
    invite_count: 4,
    verified_invite_count: 3,
    accepted_count: 2,
    copied_invite_tokens: ["private-token"],
  });
  expect(posthog.capture).toHaveBeenCalledWith("community_activated", {
    invite_count: 4,
    verified_invite_count: 3,
    accepted_count: 2,
  });
});

test("ignores unknown event names", () => {
  trackReunionEvent("family_name_recorded", { source: "test" });
  expect(posthog.capture).not.toHaveBeenCalled();
});

test("masks autocaptured text and element attributes", () => {
  initAnalytics();
  expect(posthog.init).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({
      mask_all_text: true,
      mask_all_element_attributes: true,
      before_send: sanitizeAnalyticsEvent,
    })
  );
});

test("redacts invitation tokens from analytics URL properties", () => {
  const event = sanitizeAnalyticsEvent({
    event: "invite_opened",
    properties: {
      $current_url: "https://heykindred.org/rsvp/private-token?source=email",
      $pathname: "/rsvp/private-token",
      nested: {
        referrer: "https://heykindred.org/rsvp/another-private-token#reply",
      },
    },
  });
  expect(event.properties).toEqual({
    $current_url: "https://heykindred.org/rsvp/[redacted]?source=email",
    $pathname: "/rsvp/[redacted]",
    nested: {
      referrer: "https://heykindred.org/rsvp/[redacted]#reply",
    },
  });
  expect(JSON.stringify(event)).not.toContain("private-token");
  expect(redactInvitationPaths("https://heykindred.org/pricing")).toBe(
    "https://heykindred.org/pricing"
  );
  expect(redactInvitationPaths("https://heykindred.org/rsvp#fragment-token")).toBe(
    "https://heykindred.org/rsvp#[redacted]"
  );
});

test("fails closed for every analytics entry point on secure RSVP routes", () => {
  window.history.replaceState({}, "", "/rsvp/synthetic-invitation");
  expect(isSensitiveInvitationRoute()).toBe(true);
  expect(initAnalytics()).toBe(false);
  trackEvent("frontend_error", { message: "synthetic" });
  trackReunionEvent("invite_opened", { source: "public_rsvp" });
  trackReunionEvent("rsvp_completed", { status: "going" });
  identifyUser({ id: "synthetic-user", auth_provider: "test" });
  resetAnalytics();

  expect(posthog.init).not.toHaveBeenCalled();
  expect(posthog.register).not.toHaveBeenCalled();
  expect(posthog.capture).not.toHaveBeenCalled();
  expect(posthog.identify).not.toHaveBeenCalled();
  expect(posthog.reset).not.toHaveBeenCalled();
});

test("secure RSVP analytics guard covers nested paths but not similar public pages", () => {
  window.history.replaceState({}, "", "/rsvp/synthetic-invitation/confirm");
  expect(isSensitiveInvitationRoute()).toBe(true);
  window.history.replaceState({}, "", "/rsvp-help");
  expect(isSensitiveInvitationRoute()).toBe(false);
  window.history.replaceState({}, "", "/rsvp#fragment-token");
  expect(isSensitiveInvitationRoute()).toBe(true);
});

test("explicit local QA mode suppresses every PostHog entry point", () => {
  const previous = process.env.REACT_APP_DISABLE_ANALYTICS;
  process.env.REACT_APP_DISABLE_ANALYTICS = "true";
  window.history.replaceState({}, "", "/gatherings");

  expect(initAnalytics()).toBe(false);
  identifyUser({ id: "synthetic-user" });
  resetAnalytics();
  trackEvent("synthetic_event", { source: "browser-qa" });
  trackReunionEvent("itinerary_viewed", { source: "browser-qa" });

  expect(posthog.init).not.toHaveBeenCalled();
  expect(posthog.register).not.toHaveBeenCalled();
  expect(posthog.capture).not.toHaveBeenCalled();
  expect(posthog.identify).not.toHaveBeenCalled();
  expect(posthog.reset).not.toHaveBeenCalled();

  if (previous === undefined) {
    delete process.env.REACT_APP_DISABLE_ANALYTICS;
  } else {
    process.env.REACT_APP_DISABLE_ANALYTICS = previous;
  }
});
