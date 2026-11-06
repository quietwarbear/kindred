import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({
  apiRequest: jest.fn(),
  errorDetail: (_e, fallback) => fallback,
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { toast } = require("@/components/ui/sonner");
const { DuplicateReview, mergeSummary } = require("./DuplicateReview");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const person = (id, name, extra = {}) => ({
  invite_id: id,
  name,
  email: `${id}@example.invalid`,
  has_account: false,
  rsvp_status: "pending",
  activity_answers: 0,
  ...extra,
});
const PAIR = {
  pair_key: "pair-1",
  reason: "same_name",
  people: [person("inv-old", "Ada Guest"), person("inv-new", "ada guest", { activity_answers: 2 })],
  suggested_keep_invite_id: "inv-old",
};
const event = { id: "event-1" };

let container;
let root;
const mount = async (element) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(element));
  return container;
};
const click = async (node) => act(async () => node.click());
const button = (text) => [...container.querySelectorAll("button")].find((b) => b.textContent.includes(text));

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

test("renders nothing when there are no possible duplicates", async () => {
  apiRequest.mockResolvedValue({ pairs: [] });
  await mount(<DuplicateReview event={event} token="t" />);
  expect(container.querySelector("[data-testid='duplicate-review']")).toBeNull();
});

test("shows each pair with the suggested record selected", async () => {
  apiRequest.mockResolvedValue({ pairs: [PAIR] });
  await mount(<DuplicateReview event={event} token="t" />);
  expect(container.textContent).toContain("Possible duplicates (1)");
  expect(container.textContent).toContain("Same name, different email");
  const radios = container.querySelectorAll("input[type='radio']");
  expect(radios).toHaveLength(2);
  expect(radios[0].checked).toBe(true);
  expect(container.querySelector("legend")).not.toBeNull();
  expect(button("Merge into").textContent).toContain("Ada Guest");
});

test("merges into the chosen record after confirmation and refreshes the event", async () => {
  const onUpdate = jest.fn();
  apiRequest.mockImplementation(async (path, options = {}) => {
    if (path.endsWith("/duplicates/merge")) {
      return { pairs: [], merge: { moved_event_answers: 0, moved_activity_answers: 2, account_linked: false } };
    }
    if (path.endsWith("/duplicates")) return { pairs: [PAIR] };
    return { id: "event-1", refreshed: true };
  });
  jest.spyOn(window, "confirm").mockReturnValue(true);
  await mount(<DuplicateReview event={event} onUpdate={onUpdate} token="t" />);
  await act(async () => container.querySelectorAll("input[type='radio']")[1].click());
  await click(button("Merge into"));
  const mergeCall = apiRequest.mock.calls.find(([path]) => path.endsWith("/duplicates/merge"));
  expect(mergeCall[1]).toMatchObject({
    method: "POST",
    data: { keep_invite_id: "inv-new", merge_invite_id: "inv-old" },
  });
  expect(toast.success).toHaveBeenCalledWith("Merged: 2 answers moved.");
  expect(onUpdate).toHaveBeenCalledWith({ id: "event-1", refreshed: true });
  expect(container.querySelector("[data-testid='duplicate-review']")).toBeNull();
});

test("does nothing when the organizer cancels the confirmation", async () => {
  apiRequest.mockResolvedValue({ pairs: [PAIR] });
  jest.spyOn(window, "confirm").mockReturnValue(false);
  await mount(<DuplicateReview event={event} token="t" />);
  await click(button("Merge into"));
  expect(apiRequest.mock.calls.some(([path]) => path.endsWith("/merge"))).toBe(false);
});

test("not the same person dismisses the pair", async () => {
  apiRequest.mockImplementation(async (path) => (path.endsWith("/dismiss") ? { pairs: [] } : { pairs: [PAIR] }));
  await mount(<DuplicateReview event={event} token="t" />);
  await click(button("Not the same person"));
  expect(apiRequest).toHaveBeenCalledWith("/events/event-1/duplicates/pair-1/dismiss", { method: "POST", token: "t" });
  expect(container.querySelector("[data-testid='duplicate-review']")).toBeNull();
});

test("merge is disabled when both records have their own account", async () => {
  const pair = { ...PAIR, people: PAIR.people.map((p) => ({ ...p, has_account: true })) };
  apiRequest.mockResolvedValue({ pairs: [pair] });
  await mount(<DuplicateReview event={event} token="t" />);
  expect(button("Merge into").disabled).toBe(true);
  expect(container.textContent).toContain("can't be merged here");
});

test("server refusal message is shown", async () => {
  apiRequest.mockImplementation(async (path) => {
    if (path.endsWith("/merge")) {
      const error = new Error("409");
      error.response = { data: { detail: { code: "already_merged", message: "One of these people was already merged." } } };
      throw error;
    }
    return { pairs: [PAIR] };
  });
  jest.spyOn(window, "confirm").mockReturnValue(true);
  await mount(<DuplicateReview event={event} token="t" />);
  await click(button("Merge into"));
  expect(toast.error).toHaveBeenCalledWith("One of these people was already merged.");
});

test("mergeSummary describes overlap and account moves", () => {
  expect(
    mergeSummary({ moved_event_answers: 1, moved_activity_answers: 0, overlapping_answers_resolved: 1, account_linked: true })
  ).toBe("Merged: 1 answer moved, newest answer kept where both replied, account link moved.");
});
