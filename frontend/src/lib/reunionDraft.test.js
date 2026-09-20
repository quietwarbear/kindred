import {
  clearReunionDraft,
  draftLandingPath,
  gatheringTypeDetails,
  loadReunionDraft,
  normalizeReunionDraft,
  provisionalCommunityName,
  reunionDayCount,
  reunionDraftIsComplete,
  reunionDraftToEventPayload,
  saveReunionDraft,
} from "./reunionDraft";

const completeDraft = {
  gathering_name: "The Johnson Family Reunion",
  approximate_date: "2027-07-18",
  end_date: "",
  timezone: "America/Los_Angeles",
  multiday_enabled: false,
  organizer_name: "Avery Johnson",
  location: "",
};

afterEach(() => {
  clearReunionDraft();
});

test("keeps the pre-account draft local and limits stored fields", () => {
  saveReunionDraft({ ...completeDraft, email: "private@example.com", invitation_token: "secret" });
  expect(loadReunionDraft()).toEqual(expect.objectContaining(completeDraft));
  expect(loadReunionDraft().client_request_id).toEqual(expect.any(String));
  expect(window.localStorage.getItem("kindred-reunion-draft-v1")).not.toContain("private@example.com");
  expect(window.localStorage.getItem("kindred-reunion-draft-v1")).not.toContain("secret");
});

test("requires only a gathering name and an organizer", () => {
  expect(reunionDraftIsComplete(completeDraft)).toBe(true);
  expect(reunionDraftIsComplete({ ...completeDraft, gathering_name: "" })).toBe(false);
  expect(reunionDraftIsComplete({ ...completeDraft, organizer_name: "" })).toBe(false);
  expect(reunionDraftIsComplete({ ...completeDraft, location: "Oakland, CA" })).toBe(true);
  expect(reunionDraftIsComplete({ ...completeDraft, timezone: "Mars/Olympus" })).toBe(false);
  expect(reunionDraftIsComplete({
    ...completeDraft,
    multiday_enabled: true,
    end_date: "2027-07-17",
  })).toBe(false);
});

test("a draft with no date yet is still a draft", () => {
  // The organizer who has not agreed a date with the family is exactly the
  // person this page is for. Requiring the date was the wall.
  const undated = { ...completeDraft, approximate_date: "" };
  expect(reunionDraftIsComplete(undated)).toBe(true);
  // With no start date there is nothing for an end date to contradict.
  expect(reunionDraftIsComplete({
    ...undated,
    multiday_enabled: true,
    end_date: "2027-07-17",
  })).toBe(true);
});

test("creates a useful reunion event without billing or community setup fields", () => {
  const payload = reunionDraftToEventPayload(completeDraft);
  expect(payload.event_template).toBe("reunion");
  expect(payload.volunteer_slots).toHaveLength(2);
  expect(payload.potluck_items).toHaveLength(3);
  expect(payload.agenda).toHaveLength(1);
  expect(payload.agenda[0].visibility).toBe("draft");
  expect(payload.timezone).toBe("America/Los_Angeles");
  expect(payload.end_at).toBe("2027-07-18T18:00:00");
  expect(payload.client_request_id).toEqual(expect.any(String));
  expect(payload).not.toHaveProperty("price");
  expect(payload).not.toHaveProperty("subscription");
  expect(payload).not.toHaveProperty("community_name");
});

test("keeps one idempotency key across save and retry", () => {
  const first = saveReunionDraft(completeDraft);
  const retry = reunionDraftToEventPayload(loadReunionDraft());
  expect(retry.client_request_id).toBe(first.client_request_id);
});

test("supports a one-day default and an optional multiday range", () => {
  expect(reunionDayCount(completeDraft)).toBe(1);
  const multiday = {
    ...completeDraft,
    end_date: "2027-07-20",
    multiday_enabled: true,
  };
  expect(reunionDayCount(multiday)).toBe(3);
  expect(reunionDraftToEventPayload(multiday).end_at).toBe("2027-07-20T18:00:00");
});

test("uses an explicit provisional planning-space name", () => {
  expect(provisionalCommunityName(completeDraft)).toBe("The Johnson Family Reunion planning space");
  expect(normalizeReunionDraft({ ...completeDraft, location: undefined }).location).toBe("");
});

test("defaults to a reunion and ignores unknown gathering types", () => {
  expect(normalizeReunionDraft(completeDraft).gathering_type).toBe("reunion");
  expect(normalizeReunionDraft({ ...completeDraft, gathering_type: "rave" }).gathering_type).toBe("reunion");
  expect(normalizeReunionDraft({ ...completeDraft, gathering_type: "toString" }).gathering_type).toBe("reunion");
  expect(gatheringTypeDetails({ ...completeDraft, gathering_type: "birthday" }).noun).toBe("birthday");
});

test("keeps the chosen gathering type through save and reload", () => {
  saveReunionDraft({ ...completeDraft, gathering_type: "wedding" });
  expect(loadReunionDraft().gathering_type).toBe("wedding");
});

test("holiday meal uses the holiday template and its starter content", () => {
  const payload = reunionDraftToEventPayload({ ...completeDraft, gathering_type: "holiday_meal" });
  expect(payload.event_template).toBe("holiday_meal");
  expect(payload.recurrence_frequency).toBe("none");
  expect(payload.client_request_id.length).toBeGreaterThanOrEqual(16);
  expect(payload.agenda.map((item) => item.title)).toEqual(["Welcome or arrival", "Meal time", "Cleanup"]);
  expect(payload.potluck_items).toHaveLength(4);
  expect(payload.volunteer_slots.map((slot) => slot.title)).toEqual(["Setup", "Cleanup"]);
  expect(payload.description).toBe("A private holiday meal organized by Avery Johnson.");
});

test.each(["birthday", "wedding", "custom"])("%s starts with its template and no reunion starter content", (type) => {
  const payload = reunionDraftToEventPayload({ ...completeDraft, gathering_type: type });
  expect(payload.event_template).toBe(type);
  expect(payload.agenda).toEqual([]);
  expect(payload.potluck_items).toEqual([]);
  expect(payload.volunteer_slots).toEqual([]);
  expect(payload.assigned_roles).toContain("Organizer");
  expect(payload.description).not.toContain("reunion");
});

test("only reunions land on the reunion activation flow", () => {
  expect(draftLandingPath(completeDraft, "evt-1")).toBe("/reunion/activate/evt-1");
  for (const type of ["holiday_meal", "birthday", "wedding", "custom"]) {
    expect(draftLandingPath({ ...completeDraft, gathering_type: type }, "evt-1")).toBe("/gatherings/evt-1");
  }
});
