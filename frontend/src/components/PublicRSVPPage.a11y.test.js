import React from "react";
import { createRoot } from "react-dom/client";
// axe-core ships with eslint-config-react-app (via jsx-a11y), so it is always
// installed with the toolchain.
import axe from "axe-core";

jest.mock(
  "react-router-dom",
  () => ({ useParams: () => ({}), Link: ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a> }),
  { virtual: true }
);
jest.mock("@/lib/api", () => ({ API_URL: "https://api.example.invalid/api", BACKEND_URL: "https://api.example.invalid" }));
jest.mock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));

const { PublicRSVPPage } = require("./PublicRSVPPage");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const activity = (id, title, extra = {}) => ({
  id,
  title,
  start_at: "2026-12-01T10:00",
  end_at: "2026-12-01T11:00",
  timezone: "UTC",
  venue_name: "Hall",
  response_open: true,
  attendance_requested: true,
  my_response: "no-response",
  attendance: { coming: 2, maybe: 1 },
  ...extra,
});

const PAYLOAD = {
  invitee_name: "Ada Guest",
  rsvp_status: "pending",
  guests: 0,
  gathering: {
    id: "e1",
    title: "Harvest Gathering",
    start_at: "2026-12-01T10:00",
    end_at: "2026-12-02T18:00",
    timezone: "UTC",
    location: "Town Hall",
    activities: [
      activity("a1", "Opening", { response_choices: ["In person", "Remote"] }),
      activity("a2", "Meal", { response_open: false }),
      activity("a3", "Walk", { attendance_requested: false }),
    ],
  },
};

let container;
let root;

beforeEach(async () => {
  window.location.hash = "#guest-token";
  global.fetch = jest.fn(async (_url, options = {}) => ({
    ok: true,
    json: async () => (options.method === "POST" ? { ...PAYLOAD, rsvp_status: "some" } : PAYLOAD),
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<PublicRSVPPage />));
  await act(async () => {});
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

// jsdom has no layout, so axe's colour-contrast rule can't run here; colours
// were checked by hand (see the K12 notes in the PR).
const violations = async () => {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.html).join(" | ")}`);
};

const button = (text) => [...container.querySelectorAll("button")].find((node) => node.textContent.includes(text));
const press = async (node) => act(async () => node.click());

test("every step passes axe and focus follows the step", async () => {
  expect(await violations()).toEqual([]);
  expect(container.querySelector(".sr-only[aria-live='polite']").textContent).toBe("Step 1 of 3");

  await press(button("Attending some activities"));
  await press(button("Choose activities"));
  expect(document.activeElement.textContent).toContain("Tell us which activities");
  await press(container.querySelector("fieldset button"));
  expect(await violations()).toEqual([]);
  // Each activity's buttons are grouped under a legend naming the activity.
  const legends = [...container.querySelectorAll("legend")].map((node) => node.textContent);
  expect(legends).toEqual(expect.arrayContaining(["Response for Opening", "How will you join? (Opening)"]));

  await press(button("Review response"));
  expect(document.activeElement.textContent).toBe("Review your response");
  expect(container.querySelector("input[type='number']").closest("label").textContent).toContain("Additional people");
  expect(await violations()).toEqual([]);

  await press(button("Save my response"));
  expect(document.activeElement.textContent).toBe("Your event response is saved.");
  expect(await violations()).toEqual([]);

  await press(button("Revise my response"));
  expect(document.activeElement.textContent).toContain("Will you join the event?");
});

test("decorative step dots are hidden and the new-tab link says so", async () => {
  const dots = container.querySelectorAll("span.h-2.w-12");
  expect(dots).toHaveLength(3);
  dots.forEach((dot) => expect(dot.getAttribute("aria-hidden")).toBe("true"));
  const appLink = [...container.querySelectorAll("a[target='_blank']")][0];
  expect(appLink.textContent).toContain("(opens in a new tab)");
});

test("page load does not steal focus", () => {
  expect(document.activeElement).toBe(document.body);
});
