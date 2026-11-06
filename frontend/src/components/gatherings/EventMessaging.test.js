import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({
  apiRequest: jest.fn(),
  errorDetail: (_e, fallback) => fallback,
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { EventMessaging } = require("./EventMessaging");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const event = { id: "event-1", publication_state: "published" };
const MESSAGING = {
  event_id: "event-1",
  settings: {
    sender_name: "",
    reply_to_user_id: "org-1",
    reminders_enabled: true,
    default_reminder_offsets_minutes: [1440, 60],
    activity_reminder_offsets_minutes: { "act-2": [] },
  },
  reply_to: { id: "org-1", name: "Organizer One", email: "one@example.invalid" },
  reply_to_options: [
    { id: "org-1", name: "Organizer One", email: "one@example.invalid" },
    { id: "org-2", name: "Organizer Two", email: "two@example.invalid" },
  ],
  default_sender_name: "Organizer One",
  activities: [
    { id: "act-1", title: "Opening Workshop", offsets_minutes: [1440, 60], uses_default: true },
    { id: "act-2", title: "Closing Circle", offsets_minutes: [], uses_default: false },
  ],
  days: [{ day: "2031-06-01", activity_count: 2 }],
  upcoming_reminders: [
    { activity_id: "act-1", activity_title: "Opening Workshop", offset_minutes: 1440, send_at: "2031-05-31T09:00:00Z" },
  ],
  delivery: { email: "ready", push: "off", scheduler: "configured" },
};

let container;
let root;
const mount = async (element) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(element));
  return container;
};
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

const q = (el, id) => el.querySelector(`[data-testid="${id}"]`);
const setValue = async (node, value) => {
  const proto = node.tagName === "SELECT" ? HTMLSelectElement.prototype : node.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(node, value);
  await act(async () => node.dispatchEvent(new Event(node.tagName === "SELECT" ? "change" : "input", { bubbles: true })));
};

const routeApi = (handlers = {}) => {
  apiRequest.mockImplementation(async (path, options = {}) => {
    const key = `${options.method || "GET"} ${path}`;
    if (handlers[key]) return handlers[key](options);
    if (key === "GET /events/event-1/messaging") return MESSAGING;
    if (key === "GET /events/event-1/announcements") return { announcements: [] };
    if (key === "POST /events/event-1/announcements/audience") return { recipients: 2, with_email: 2, with_account: 1 };
    return {};
  });
};

describe("EventMessaging panel", () => {
  it("sends an announcement to one activity's attendees by email and push", async () => {
    let sent = null;
    routeApi({ "POST /announcements": ({ data }) => { sent = data; return { id: "a-1" }; } });
    const el = await mount(<EventMessaging event={event} token="t" />);
    expect(q(el, "event-messaging-readiness").textContent).toContain("Push notifications are off");

    await setValue(q(el, "announcement-title"), "Room change");
    await setValue(q(el, "announcement-body"), "We moved to the main hall.");
    await setValue(q(el, "announcement-audience"), "activity");
    expect(q(el, "announcement-send").disabled).toBe(true); // no activity chosen yet
    await setValue(q(el, "announcement-activity"), "act-1");
    expect(q(el, "announcement-audience-summary").textContent).toBe("2 people · all with email · 1 in the app");
    const previewCall = apiRequest.mock.calls.find(([p, o]) => p.endsWith("/audience") && o.data.audience === "activity");
    expect(previewCall[1].data).toEqual({ audience: "activity", day: "", activity_id: "act-1" });

    await act(async () => q(el, "announcement-send").click());
    expect(sent).toEqual({
      title: "Room change",
      body: "We moved to the main hall.",
      scope: "courtyard",
      event_id: "event-1",
      audience: "activity",
      day: "",
      activity_id: "act-1",
      channels: ["email", "push"],
    });
  });

  it("can send in the app only", async () => {
    let sent = null;
    routeApi({ "POST /announcements": ({ data }) => { sent = data; return {}; } });
    const el = await mount(<EventMessaging event={event} token="t" />);
    await setValue(q(el, "announcement-title"), "Hello");
    await act(async () => q(el, "announcement-email").click());
    await act(async () => q(el, "announcement-push").click());
    await act(async () => q(el, "announcement-send").click());
    expect(sent.channels).toEqual([]);
    expect(sent.audience).toBe("everyone");
  });

  it("saves sender, reply-to and reminder offsets with per-activity overrides", async () => {
    let saved = null;
    routeApi({ "PUT /events/event-1/messaging": ({ data }) => { saved = data; return MESSAGING; } });
    const el = await mount(<EventMessaging event={event} token="t" />);
    expect(el.textContent).toContain("Next reminders");

    await setValue(q(el, "messaging-sender-name"), "The Planning Team");
    await setValue(q(el, "messaging-reply-to"), "org-2");
    await act(async () => q(el, "messaging-default-offsets-60").click()); // drop 1 hour
    await act(async () => q(el, "messaging-default-offsets-180").click()); // add 3 hours
    await setValue(q(el, "messaging-activity-mode-act-1"), "custom");
    await act(async () => q(el, "messaging-activity-offsets-act-1-15").click());
    await act(async () => q(el, "messaging-save").click());

    expect(saved).toEqual({
      sender_name: "The Planning Team",
      reply_to_user_id: "org-2",
      reminders_enabled: true,
      default_reminder_offsets_minutes: [1440, 180],
      activity_reminder_offsets_minutes: { "act-1": [1440, 180, 15], "act-2": [] },
    });
  });

  it("does nothing for a private draft", async () => {
    routeApi();
    const el = await mount(<EventMessaging event={{ ...event, publication_state: "organizer_draft" }} token="t" />);
    expect(q(el, "event-messaging-draft-guard")).not.toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("lists sent announcements with content-free delivery counts", async () => {
    routeApi({
      "GET /events/event-1/announcements": () => ({
        announcements: [
          { id: "a1", title: "Parking", audience_label: "Everyone invited", delivery_summary: { recipients: 2, email: { accepted: 2 }, push: {} } },
        ],
      }),
    });
    const el = await mount(<EventMessaging event={event} token="t" />);
    expect(q(el, "event-messaging-sent").textContent).toContain("Everyone invited · 2 emailed");
  });
});
