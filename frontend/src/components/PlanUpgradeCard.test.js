import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ apiRequest: jest.fn() }));
// Jest cannot resolve react-router-dom v7's package exports here; the card only needs Link.
jest.mock(
  "react-router-dom",
  () => ({ Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a> }),
  { virtual: true },
);

const { apiRequest } = require("@/lib/api");
const { PlanUpgradeCard } = require("./PlanUpgradeCard");
const act = React.act || require("react-dom/test-utils").act;

const CONTEST_OPEN = Date.parse("2026-10-01T12:00:00-07:00");
const CONTEST_CLOSED = Date.parse("2026-12-10T12:00:00-08:00");

const plan = ({ id = "seedling", name = "Seedling", max = 10, members = 4, provider } = {}) => ({
  subscription: provider ? { provider } : null,
  tier: { id, name, max_members: max },
  usage: { member_count: members, subyard_count: 0 },
});

let container;
let root;

const render = async ({ now, payload, ...props }) => {
  jest.spyOn(Date, "now").mockReturnValue(now);
  apiRequest.mockResolvedValue(payload);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<PlanUpgradeCard token="t" {...props} />);
  });
  return container;
};

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.restoreAllMocks();
});

describe("Today card during Keep The Record", () => {
  it("asks a free-plan host to upgrade to enter, linking to the subscription page", async () => {
    const el = await render({ now: CONTEST_OPEN, payload: plan(), variant: "today", isHost: true });
    expect(el.textContent).toContain("Upgrade to enter Keep The Record");
    expect(el.textContent).toContain("Seedling plan · 4 of 10 members");
    expect(el.querySelector('a[href="/subscription"]')).not.toBeNull();
  });

  it("adds the limit sentence when a free-plan host is also nearly full", async () => {
    const el = await render({ now: CONTEST_OPEN, payload: plan({ members: 9 }), variant: "today", isHost: true });
    expect(el.textContent).toContain("Upgrade to enter Keep The Record");
    expect(el.textContent).toContain("Only 1 spot is left.");
  });

  it("tells a member of a free-plan family that only the host can change the plan", async () => {
    const el = await render({ now: CONTEST_OPEN, payload: plan(), variant: "today", isHost: false });
    expect(el.textContent).toContain("Your family isn’t entered yet");
    expect(el.textContent).toContain("Only your host can change the plan");
  });

  it("never offers a member a link to the plan page — only the host may buy", async () => {
    // The member CAN chip in toward the host's Reunion Pass (that card renders
    // itself, and is covered by its own tests), but must never be handed a
    // route to the subscription page: only the host can change the plan, and
    // sending a member there produces a request they cannot complete.
    const el = await render({ now: CONTEST_OPEN, payload: plan(), variant: "today", isHost: false });
    expect(el.querySelector('a[href="/subscription"]')).toBeNull();
  });

  it("shows nothing to a paid family, host or not", async () => {
    const paid = plan({ id: "sapling", name: "Sapling", max: 25 });
    expect((await render({ now: CONTEST_OPEN, payload: paid, variant: "today", isHost: true })).innerHTML).toBe("");
    await act(async () => root.unmount());
    container.remove();
    expect((await render({ now: CONTEST_OPEN, payload: paid, variant: "today", isHost: false })).innerHTML).toBe("");
  });
});

describe("Today card after the contest", () => {
  it("shows nothing to a free-plan host with room, or to members", async () => {
    expect((await render({ now: CONTEST_CLOSED, payload: plan(), variant: "today", isHost: true })).innerHTML).toBe("");
    await act(async () => root.unmount());
    container.remove();
    expect((await render({ now: CONTEST_CLOSED, payload: plan(), variant: "today", isHost: false })).innerHTML).toBe("");
  });

  it("falls back to the almost-full prompt for hosts", async () => {
    const el = await render({ now: CONTEST_CLOSED, payload: plan({ members: 8 }), variant: "today", isHost: true });
    expect(el.textContent).toContain("Your family is almost full");
    expect(el.querySelector('a[href="/subscription"]')).not.toBeNull();
  });
});

describe("Settings plan card", () => {
  it("offers Upgrade plan on Seedling and Manage plan under the admin override", async () => {
    const free = await render({ now: CONTEST_OPEN, payload: plan({ members: 10 }), variant: "settings" });
    expect(free.textContent).toContain("Seedling");
    expect(free.textContent).toContain("10 of 10 members · family is full");
    expect(free.textContent).toContain("Upgrade plan");
    await act(async () => root.unmount());
    container.remove();
    const admin = await render({
      now: CONTEST_OPEN,
      payload: plan({ id: "redwood", name: "Redwood", max: 100, members: 3, provider: "admin_override" }),
      variant: "settings",
    });
    expect(admin.textContent).toContain("Manage plan");
  });
});
