import React from "react";
import { createRoot } from "react-dom/client";

import { apiBlobRequest, apiRequest } from "@/lib/api";
import {
  ActivityRoster,
  ENDED_STILL_COMING,
  filterRosterPeople,
  rosterCsvPath,
} from "./ActivityRoster";

jest.mock("@/lib/api", () => ({ apiRequest: jest.fn(), apiBlobRequest: jest.fn() }));
jest.mock("@/components/ui/sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

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
  await act(async () => {});
};

afterEach(async () => {
  if (root) await act(async () => { root.unmount(); });
  container?.remove();
  root = null;
  container = null;
  jest.clearAllMocks();
});

const row = (key, name, status, extra = {}) => ({
  row_key: key, name, status, registered: true, choice: "", party_size: status === "coming" ? 2 : 0, responded_at: "", flags: [], ...extra,
});

const ROSTER = {
  registered: 3,
  ended_still_coming: 1,
  activities: [
    {
      id: "earlier",
      title: "Opening circle",
      ended: true,
      capacity: null,
      counts: { coming: 1, maybe: 0, "not-coming": 0, "no-response": 2 },
      expected_turnout: 2,
      possible_turnout: 2,
      people: [
        row("r1", "Ada Guest", "coming", { flags: [ENDED_STILL_COMING] }),
        row("r2", "Bea Guest", "no-response"),
        row("r3", "Cy Guest", "no-response", { registered: false }),
      ],
    },
    {
      id: "later",
      title: "Evening meal",
      ended: false,
      capacity: 40,
      counts: { coming: 0, maybe: 1, "not-coming": 0, "no-response": 2 },
      expected_turnout: 0,
      possible_turnout: 1,
      people: [row("r4", "Bea Guest", "maybe", { party_size: 1 })],
    },
  ],
};

const byTestId = (id) => container.querySelector(`[data-testid="${id}"]`);

const change = async (element, value) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
    setter.call(element, value);
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
};

describe("ActivityRoster", () => {
  beforeEach(() => apiRequest.mockResolvedValue(ROSTER));

  it("loads the roster for the event with the organizer token", async () => {
    await render(<ActivityRoster eventId="event-1" token="t" />);
    expect(apiRequest).toHaveBeenCalledWith("/events/event-1/activity-roster", { token: "t" });
    expect(container.textContent).toContain("3 registered for this event.");
  });

  it("warns about people still coming to ended activities and labels them", async () => {
    await render(<ActivityRoster eventId="event-1" token="t" />);
    expect(byTestId("activity-roster-ended-warning").textContent).toContain("1 person is still marked coming");
    expect(byTestId("activity-roster-row-r1").textContent).toContain("Activity ended");
    expect(byTestId("activity-roster-row-r3").textContent).toContain("Not registered");
    expect(byTestId("activity-roster-select").textContent).toContain("Opening circle (ended)");
  });

  it("shows counts and turnout for the chosen activity", async () => {
    await render(<ActivityRoster eventId="event-1" token="t" />);
    await change(byTestId("activity-roster-select"), "later");
    const counts = byTestId("activity-roster-counts-later").textContent;
    expect(counts).toContain("Maybe1");
    expect(counts).toContain("Expected0 / 40");
    expect(counts).toContain("With maybes1");
  });

  it("filters by status and flag", async () => {
    await render(<ActivityRoster eventId="event-1" token="t" />);
    await change(byTestId("activity-roster-status"), "no-response");
    expect(byTestId("activity-roster-row-r1")).toBeNull();
    expect(byTestId("activity-roster-row-r2")).not.toBeNull();
    await change(byTestId("activity-roster-status"), "flagged");
    expect(byTestId("activity-roster-row-r1")).not.toBeNull();
    expect(byTestId("activity-roster-row-r2")).toBeNull();
  });

  it("exports CSV with the bearer token, for all or one activity", async () => {
    apiBlobRequest.mockResolvedValue(new Blob(["a,b"], { type: "text/csv" }));
    global.URL.createObjectURL = jest.fn(() => "blob:local");
    global.URL.revokeObjectURL = jest.fn();
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await render(<ActivityRoster eventId="event-1" token="t" />);
    await act(async () => { byTestId("activity-roster-export-all").click(); });
    await act(async () => { byTestId("activity-roster-export-one").click(); });
    expect(apiBlobRequest.mock.calls).toEqual([
      ["/events/event-1/activity-roster.csv", { token: "t" }],
      ["/events/event-1/activity-roster.csv?activity_id=earlier", { token: "t" }],
    ]);
    expect(click).toHaveBeenCalledTimes(2);
    click.mockRestore();
  });

  it("offers a retry when loading fails", async () => {
    apiRequest.mockRejectedValueOnce(new Error("down"));
    await render(<ActivityRoster eventId="event-1" token="t" />);
    expect(byTestId("activity-roster").textContent).toContain("could not be loaded");
  });
});

describe("roster helpers", () => {
  it("builds CSV paths", () => {
    expect(rosterCsvPath("e")).toBe("/events/e/activity-roster.csv");
    expect(rosterCsvPath("e", "a b")).toBe("/events/e/activity-roster.csv?activity_id=a%20b");
  });

  it("filters people", () => {
    const people = ROSTER.activities[0].people;
    expect(filterRosterPeople(people, "all")).toHaveLength(3);
    expect(filterRosterPeople(people, "flagged").map((p) => p.row_key)).toEqual(["r1"]);
    expect(filterRosterPeople(people, "coming").map((p) => p.row_key)).toEqual(["r1"]);
  });
});
