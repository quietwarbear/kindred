import {
  clearReunionDraft,
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

test("requires only gathering, approximate date, and organizer", () => {
  expect(reunionDraftIsComplete(completeDraft)).toBe(true);
  expect(reunionDraftIsComplete({ ...completeDraft, organizer_name: "" })).toBe(false);
  expect(reunionDraftIsComplete({ ...completeDraft, location: "Oakland, CA" })).toBe(true);
  expect(reunionDraftIsComplete({ ...completeDraft, timezone: "Mars/Olympus" })).toBe(false);
  expect(reunionDraftIsComplete({
    ...completeDraft,
    multiday_enabled: true,
    end_date: "2027-07-17",
  })).toBe(false);
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
