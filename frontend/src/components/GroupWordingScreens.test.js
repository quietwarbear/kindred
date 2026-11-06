// K3: key screens rendered with a non-default group word. Each snapshot is the
// visible text only, so it stays readable in review and breaks only on copy.
import React from "react";
import { createRoot } from "react-dom/client";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  apiRequest: jest.fn(),
  errorDetail: (error, fallback) => error?.response?.data?.detail || fallback,
}));
jest.mock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));
jest.mock("@/components/ui/sonner", () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { GroupWordingProvider } = require("@/lib/groupWording");
const { HomePage } = require("./HomePage");
const { PlanUpgradeCard } = require("./PlanUpgradeCard");
const { GroupWordingSettings } = require("./GroupWordingSettings");

const CONGREGATION = { preset: "congregation", singular: "congregation", plural: "congregations" };
const CUSTOM = { preset: "custom", singular: "Village", plural: "Villages" };
const CONTEST_OPEN = Date.parse("2026-10-01T12:00:00-07:00");

let container;
let root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  apiRequest.mockReset();
});
afterEach(async () => {
  await React.act(async () => root.unmount());
  container.remove();
  jest.restoreAllMocks();
});

const render = async (label, element) => {
  await React.act(async () => root.render(<GroupWordingProvider label={label}>{element}</GroupWordingProvider>));
  return container;
};

const visibleText = (el) => {
  const attributes = [...el.querySelectorAll("[aria-label],[placeholder]")]
    .map((node) => node.getAttribute("aria-label") || node.getAttribute("placeholder"));
  return [el.textContent, ...attributes].join(" | ").replace(/\s+/g, " ").trim();
};

const expectNoDefaultWording = (text) => {
  expect(text).not.toMatch(/famil/i);
  expect(text).not.toMatch(/\{group/i);
};

const TODAY = {
  viewer_role: "member",
  lifecycle_state: "active",
  primary_action: { code: "complete_reunion_rsvp", destination_category: "gatherings" },
  secondary_actions: [
    { code: "respond_to_gathering_pulse", destination_category: "gathering_proposals" },
    { code: "check_family_access_status", destination_category: "family_access" },
  ],
  recent_changes: [
    { id: "1", category: "family_update", is_read: false },
    { id: "2", category: "gathering_pulse", is_read: true },
  ],
  milestone_codes: [],
};

describe("Today", () => {
  beforeEach(() => apiRequest.mockResolvedValue({ subscription: { provider: "stripe" }, tier: { id: "oak", name: "Oak", max_members: 50 }, usage: { member_count: 4 } }));

  test("member Today with a congregation label", async () => {
    const text = visibleText(await render(CONGREGATION, <HomePage todayData={TODAY} token="t" />));
    expect(text).toContain("Congregation Today");
    expect(text).toContain("Let the congregation know your own plans");
    expectNoDefaultWording(text);
    expect(text).toMatchSnapshot();
  });

  test("Today when it cannot load, with a custom label", async () => {
    const text = visibleText(await render(CUSTOM, <HomePage todayError={{ kind: "unavailable" }} token="t" />));
    expect(text).toContain("Open your village space");
    expect(text).toContain("Open village activity");
    expectNoDefaultWording(text);
    expect(text).toMatchSnapshot();
  });

  test("the default still reads family", async () => {
    const text = visibleText(await render(undefined, <HomePage todayData={TODAY} token="t" />));
    expect(text).toContain("Family Today");
    expect(text).toContain("Let the family know your own plans");
  });
});

describe("plan card", () => {
  test("a member of a free-plan space during Keep The Record", async () => {
    jest.spyOn(Date, "now").mockReturnValue(CONTEST_OPEN);
    apiRequest.mockImplementation(async (path) => (path.startsWith("/subscriptions")
      ? { subscription: null, tier: { id: "seedling", name: "Seedling", max_members: 10 }, usage: { member_count: 9, subyard_count: 0 } }
      : { available: false }));
    const text = visibleText(await render(CONGREGATION, <PlanUpgradeCard token="t" variant="today" isHost={false} />));
    expect(text).toContain("Your congregation isn’t entered yet");
    expect(text).toContain("for subscriber congregations");
    // Plan names never change with the wording.
    expect(text).toContain("Seedling");
    expectNoDefaultWording(text);
    expect(text).toMatchSnapshot();
  });
});

describe("organizer wording setting", () => {
  test("members never see it", async () => {
    const el = await render(undefined, <GroupWordingSettings token="t" user={{ role: "member" }} />);
    expect(el.innerHTML).toBe("");
  });

  test("an organizer saves a custom word, then the session is refreshed", async () => {
    const refresh = jest.fn();
    apiRequest.mockResolvedValue({ group_label: { preset: "custom", singular: "village", plural: "villages" } });
    const el = await render(undefined, <GroupWordingSettings onSessionRefresh={refresh} token="t" user={{ role: "organizer" }} />);
    expect(el.querySelector('[data-testid="group-wording-option-family"]').checked).toBe(true);
    expect(el.querySelector('[data-testid="group-wording-save"]').disabled).toBe(true);

    await React.act(async () => el.querySelector('[data-testid="group-wording-option-custom"]').click());
    const type = async (testId, value) => {
      const input = el.querySelector(`[data-testid="${testId}"]`);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      await React.act(async () => {
        setter.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };
    await type("group-wording-singular", "village");
    await type("group-wording-plural", "villages2");
    expect(el.textContent).toMatch(/letters only/);
    expect(el.querySelector('[data-testid="group-wording-save"]').disabled).toBe(true);

    await type("group-wording-plural", "villages");
    expect(el.querySelector('[data-testid="group-wording-preview"]').textContent).toContain("Village Today");
    await React.act(async () => el.querySelector('[data-testid="group-wording-save"]').click());
    expect(apiRequest).toHaveBeenCalledWith("/community/group-label", {
      method: "PUT",
      token: "t",
      data: { preset: "custom", singular: "village", plural: "villages" },
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  test("the current word is preselected", async () => {
    const el = await render({ preset: "team" }, <GroupWordingSettings token="t" user={{ role: "host" }} />);
    expect(el.querySelector('[data-testid="group-wording-option-team"]').checked).toBe(true);
    expect(el.querySelector('[data-testid="group-wording-preview"]').textContent).toContain("Team Today");
  });
});
