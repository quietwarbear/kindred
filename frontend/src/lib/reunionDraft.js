const REUNION_DRAFT_KEY = "kindred-reunion-draft-v1";

export const emptyReunionDraft = Object.freeze({
  client_request_id: "",
  gathering_name: "",
  approximate_date: "",
  end_date: "",
  timezone: "UTC",
  multiday_enabled: false,
  organizer_name: "",
  location: "",
});

const clean = (value, maxLength) => String(value || "").trim().slice(0, maxLength);

const createClientRequestId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `reunion-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
};

export function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function validReunionTimezone(value) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value || "" }).format();
    return true;
  } catch {
    return false;
  }
}

export function normalizeReunionDraft(value = {}) {
  const startDate = clean(value.approximate_date, 10);
  const endDate = clean(value.end_date, 10);
  const multidayEnabled = Boolean(value.multiday_enabled || (endDate && endDate !== startDate));
  return {
    client_request_id: clean(value.client_request_id, 100) || createClientRequestId(),
    gathering_name: clean(value.gathering_name, 120),
    approximate_date: startDate,
    end_date: multidayEnabled ? endDate : "",
    timezone: clean(value.timezone, 80) || browserTimezone(),
    multiday_enabled: multidayEnabled,
    organizer_name: clean(value.organizer_name, 100),
    location: clean(value.location, 160),
  };
}

export function loadReunionDraft() {
  try {
    const stored = window.localStorage.getItem(REUNION_DRAFT_KEY);
    return stored
      ? normalizeReunionDraft(JSON.parse(stored))
      : normalizeReunionDraft({ ...emptyReunionDraft, timezone: browserTimezone() });
  } catch {
    return normalizeReunionDraft({ ...emptyReunionDraft, timezone: browserTimezone() });
  }
}

export function saveReunionDraft(value) {
  const draft = normalizeReunionDraft(value);
  window.localStorage.setItem(REUNION_DRAFT_KEY, JSON.stringify(draft));
  return draft;
}

export function clearReunionDraft() {
  window.localStorage.removeItem(REUNION_DRAFT_KEY);
}

export function reunionDraftIsComplete(draft) {
  const complete = Boolean(
    draft?.gathering_name
    && draft?.approximate_date
    && draft?.organizer_name
    && validReunionTimezone(draft?.timezone)
  );
  if (!complete) return false;
  return !draft.end_date || draft.end_date >= draft.approximate_date;
}

export function reunionDraftToEventPayload(draft) {
  const normalized = normalizeReunionDraft(draft);
  const endDate = normalized.end_date || normalized.approximate_date;
  const startAt = `${normalized.approximate_date}T09:00:00`;
  const endAt = `${endDate}T18:00:00`;
  return {
    client_request_id: normalized.client_request_id,
    title: normalized.gathering_name,
    description: `A private reunion gathering organized by ${normalized.organizer_name}.`,
    start_at: startAt,
    end_at: endAt,
    timezone: normalized.timezone,
    location: normalized.location,
    event_template: "reunion",
    gathering_format: "in-person",
    max_attendees: 50,
    recurrence_frequency: "none",
    assigned_roles: ["Organizer", "Historian", "Hospitality Lead"],
    agenda: [
      {
        time_label: "Arrival",
        title: "Welcome and family check-in",
        description: "A starting point for the reunion itinerary.",
        start_at: `${normalized.approximate_date}T10:00:00`,
        end_at: `${normalized.approximate_date}T11:00:00`,
        timezone: "",
        venue_name: "",
        venue_address: "",
        venue_detail: "",
        map_url: "",
        virtual_link: "",
        location_tba: true,
        attendance_requested: true,
        notes: "",
        visibility: "draft",
        featured: true,
      },
    ],
    volunteer_slots: [
      { title: "Welcome and check-in", needed_count: 2 },
      { title: "Photo and story team", needed_count: 2 },
    ],
    potluck_items: ["Main dish", "Side dish", "Dessert or drinks"],
    travel_coordination_notes: "",
    suggested_contribution: 0,
  };
}

export function reunionDayCount(draft) {
  const normalized = normalizeReunionDraft(draft);
  if (!normalized.approximate_date) return 0;
  const start = new Date(`${normalized.approximate_date}T12:00:00Z`);
  const end = new Date(`${normalized.end_date || normalized.approximate_date}T12:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return 1;
  return Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1;
}

export function provisionalCommunityName(draft) {
  const normalized = normalizeReunionDraft(draft);
  return `${normalized.gathering_name || "Reunion"} planning space`;
}
