import React from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({
  apiRequest: jest.fn(),
  errorDetail: (_e, fallback) => fallback,
}));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { apiRequest } = require("@/lib/api");
const { IleUbuntuHandoff, reportLines } = require("./IleUbuntuHandoff");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act || require("react-dom/test-utils").act;

const STATE = {
  configured: true,
  event_ended: true,
  connected: true,
  key_last4: "abcd",
  teacher_name: "Teacher",
  course_map: { a1: "course-1" },
  activities: [{ id: "a1", title: "Day One" }, { id: "a2", title: "Day Two" }],
  courses: [{ id: "course-1", title: "First course" }, { id: "course-2", title: "Second course" }],
  courses_error: "",
  last_send: null,
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
const button = (text) => [...container.querySelectorAll("button")].find((b) => b.textContent.trim() === text);
const setValue = async (node, value) => {
  const proto = node.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(node, value);
  await act(async () => node.dispatchEvent(new Event(node.tagName === "SELECT" ? "change" : "input", { bubbles: true })));
};

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.clearAllMocks();
  jest.restoreAllMocks();
});

test("stays hidden until the server is set up for Ile Ubuntu", async () => {
  apiRequest.mockResolvedValue({ ...STATE, configured: false });
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  expect(container.querySelector("[data-testid='ile-ubuntu-handoff']")).toBeNull();
});

test("saves a pasted key and shows only its last four characters", async () => {
  apiRequest.mockImplementation(async (path, options = {}) =>
    options.method === "PUT" ? { ...STATE, key_last4: "wxyz" } : { ...STATE, connected: false, courses: [] });
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  const input = container.querySelector("#ile-ubuntu-key");
  expect(input.type).toBe("password");
  await setValue(input, "kh_secretvaluewxyz");
  await click(button("Save"));
  const put = apiRequest.mock.calls.find(([, o]) => o?.method === "PUT");
  expect(put[1].data).toEqual({ course_map: { a1: "course-1" }, connection_key: "kh_secretvaluewxyz" });
  expect(container.textContent).toContain("key ending wxyz");
  expect(container.textContent).not.toContain("kh_secretvaluewxyz");
  expect(input.value).toBe("");
});

test("matching an activity must be saved before sending", async () => {
  apiRequest.mockImplementation(async (path, options = {}) =>
    options.method === "PUT" ? { ...STATE, course_map: options.data.course_map } : STATE);
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  expect(container.querySelector("legend").textContent).toContain("Match activities");
  await setValue(container.querySelector("#ile-course-a2"), "course-2");
  expect(button("Send attendees to Ile Ubuntu").disabled).toBe(true);
  await click(button("Save"));
  const put = apiRequest.mock.calls.find(([, o]) => o?.method === "PUT");
  expect(put[1].data.course_map).toEqual({ a1: "course-1", a2: "course-2" });
  expect(button("Send attendees to Ile Ubuntu").disabled).toBe(false);
});

test("send is held until the event ends but preview works", async () => {
  apiRequest.mockImplementation(async (path) =>
    path.endsWith("/send")
      ? { dry_run: true, local: { sending: 2 }, report: { counts: { created: 1, enrolled: 2 } } }
      : { ...STATE, event_ended: false });
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  expect(button("Send attendees to Ile Ubuntu").disabled).toBe(true);
  expect(container.textContent).toContain("You can send once the event has ended");
  await click(button("Preview"));
  const call = apiRequest.mock.calls.find(([path]) => path.endsWith("/send"));
  expect(call[1].data).toEqual({ dry_run: true });
  const report = container.querySelector("[data-testid='ile-ubuntu-report']");
  expect(report.textContent).toContain("Preview — nothing sent yet");
  expect(report.textContent).toContain("1 new account would be created");
});

test("sending after confirmation shows the returned report", async () => {
  apiRequest.mockImplementation(async (path) =>
    path.endsWith("/send")
      ? {
        dry_run: false,
        local: { sending: 3, no_email: 1 },
        report: {
          counts: { created: 2, enrolled: 3, skipped: 1, errors: 1 },
          welcome_emails: 2,
          errors: [{ row: 3, email: "x@example.invalid", error: "Unknown session: course-9" }],
        },
      }
      : STATE);
  jest.spyOn(window, "confirm").mockReturnValue(true);
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  await click(button("Send attendees to Ile Ubuntu"));
  const report = container.querySelector("[data-testid='ile-ubuntu-report']");
  expect(report.textContent).toContain("3 people marked coming");
  expect(report.textContent).toContain("1 person left out: no email on file");
  expect(report.textContent).toContain("2 welcome emails with a sign-in link");
  expect(report.textContent).toContain("Unknown session: course-9");
});

test("cancelling the confirmation sends nothing", async () => {
  apiRequest.mockResolvedValue(STATE);
  jest.spyOn(window, "confirm").mockReturnValue(false);
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  await click(button("Send attendees to Ile Ubuntu"));
  expect(apiRequest.mock.calls.some(([path]) => path.endsWith("/send"))).toBe(false);
});

test("a server refusal is announced", async () => {
  apiRequest.mockImplementation(async (path) => {
    if (path.endsWith("/send")) {
      const error = new Error("403");
      error.response = { data: { detail: { code: "connection_key_invalid", message: "Ile Ubuntu didn't accept the connection key." } } };
      throw error;
    }
    return STATE;
  });
  await mount(<IleUbuntuHandoff event={event} token="t" />);
  await click(button("Preview"));
  expect(container.querySelector("[role='alert']").textContent).toContain("didn't accept the connection key");
});

test("reportLines handles an empty send", () => {
  expect(reportLines({ dry_run: true, local: { sending: 0 }, report: null })).toEqual([
    "0 people marked coming for a matched activity",
  ]);
});
