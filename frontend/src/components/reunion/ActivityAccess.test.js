import React from "react";
import { createRoot } from "react-dom/client";

import {
  ActivityAccess,
  ActivityChoicePicker,
  VIRTUAL_LINK_WITHHELD_NOTICE,
  choiceCountsLabel,
  choicesApply,
  closedResponseMessage,
} from "./ActivityAccess";

jest.mock(
  "react-router-dom",
  () => ({ useParams: () => ({}) }),
  { virtual: true },
);

const act = React.act || require("react-dom/test-utils").act;

let container;
let root;

beforeAll(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
});

const render = async (element) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(element); });
};

afterEach(async () => {
  if (root) await act(async () => { root.unmount(); });
  container?.remove();
  root = null;
  container = null;
});

const activity = (overrides = {}) => ({
  id: "session-a",
  response_choices: ["In person", "Remote"],
  virtual_link: "",
  virtual_link_withheld: false,
  virtual_link_notice: "",
  ...overrides,
});

describe("ActivityAccess", () => {
  it("shows the link to someone the server sent it to", async () => {
    await render(<ActivityAccess activity={activity({ virtual_link: "https://meet.example.invalid/a" })} />);
    const link = container.querySelector("a");
    expect(link.getAttribute("href")).toBe("https://meet.example.invalid/a");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(container.textContent).not.toContain(VIRTUAL_LINK_WITHHELD_NOTICE);
  });

  it("shows the registered-attendees notice when the link is withheld", async () => {
    await render(<ActivityAccess activity={activity({ virtual_link_withheld: true, virtual_link_notice: VIRTUAL_LINK_WITHHELD_NOTICE })} />);
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe("Link shared with registered attendees.");
  });

  it("renders nothing for an activity with no link", async () => {
    await render(<ActivityAccess activity={activity()} />);
    expect(container.textContent).toBe("");
  });
});

describe("ActivityChoicePicker", () => {
  it("offers choices only after coming or maybe", async () => {
    expect(choicesApply(activity(), "coming")).toBe(true);
    expect(choicesApply(activity(), "maybe")).toBe(true);
    expect(choicesApply(activity(), "not-coming")).toBe(false);
    expect(choicesApply(activity(), undefined)).toBe(false);
    expect(choicesApply(activity({ response_choices: [] }), "coming")).toBe(false);

    await render(<ActivityChoicePicker activity={activity()} onChange={() => {}} status="not-coming" value="" />);
    expect(container.textContent).toBe("");
  });

  it("marks the saved choice and reports a new one", async () => {
    const onChange = jest.fn();
    await render(<ActivityChoicePicker activity={activity()} onChange={onChange} status="coming" value="Remote" />);
    const buttons = [...container.querySelectorAll("button")];
    expect(buttons.map((button) => button.textContent)).toEqual(["In person", "Remote"]);
    expect(buttons[1].getAttribute("aria-pressed")).toBe("true");
    await act(async () => { buttons[0].click(); });
    expect(onChange).toHaveBeenCalledWith("In person");
  });

  it("is disabled once responses close", async () => {
    await render(<ActivityChoicePicker activity={activity()} disabled onChange={() => {}} status="coming" value="" />);
    expect([...container.querySelectorAll("button")].every((button) => button.disabled)).toBe(true);
  });
});

describe("organizer counts and close messages", () => {
  it("summarizes coming counts per option", () => {
    expect(choiceCountsLabel({
      choices: { "In person": { coming: 4 }, Remote: { coming: 2 } },
      unspecified: { coming: 1 },
    })).toBe("In person: 4 · Remote: 2 · No option chosen: 1");
    expect(choiceCountsLabel(undefined)).toBe("");
  });

  it("explains why an activity stopped taking responses", () => {
    expect(closedResponseMessage({ rsvp_deadline: "2027-01-01T10:00" })).toMatch(/deadline has passed/);
    expect(closedResponseMessage({ rsvp_deadline: "" })).toMatch(/has ended/);
  });
});

describe("guest RSVP and organizer form helpers", () => {
  it("sends only the options a guest changed", () => {
    jest.isolateModules(() => {
      jest.doMock("@/lib/api", () => ({ API_URL: "" }));
      jest.doMock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));
      const { changedActivityChoices } = require("../PublicRSVPPage");
      const activities = [
        activity({ id: "a" }),
        activity({ id: "b" }),
        activity({ id: "c" }),
        activity({ id: "d", response_choices: [] }),
      ];
      expect(changedActivityChoices(
        activities,
        { a: "coming", b: "not-coming", c: "coming", d: "coming" },
        { a: "Remote", b: "Remote", c: "In person", d: "x" },
        { a: "Remote", b: "Remote" },
      )).toEqual({ b: "", c: "In person" });
    });
  });

  it("parses organizer options from a comma list", () => {
    jest.isolateModules(() => {
      jest.doMock("@/lib/api", () => ({ apiRequest: jest.fn() }));
      jest.doMock("@/lib/analytics", () => ({ trackReunionEvent: jest.fn() }));
      jest.doMock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
      const { parseResponseChoices } = require("./ReunionItinerary");
      expect(parseResponseChoices(" In  person, Remote, remote, , A, B, C, D, E")).toEqual([
        "In person", "Remote", "A", "B", "C", "D",
      ]);
      expect(parseResponseChoices("")).toEqual([]);
    });
  });
});
