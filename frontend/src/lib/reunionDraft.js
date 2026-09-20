const REUNION_DRAFT_KEY = "kindred-reunion-draft-v1";

// The first gathering a new family plans. Ids match the backend
// GATHERING_TEMPLATES; roles mirror each template's defaults.
export const GATHERING_TYPES = Object.freeze({
  reunion: {
    label: "Event",
    noun: "event",
    placeholder: "The family event",
    roles: ["Organizer", "Historian", "Contributor"],
  },
  holiday_meal: {
    label: "Holiday meal",
    noun: "holiday meal",
    placeholder: "Thanksgiving at Grandma's",
    roles: ["Organizer", "Contributor", "Historian"],
  },
  birthday: {
    label: "Birthday",
    noun: "birthday",
    placeholder: "Aunt Ruth's 80th Birthday",
    roles: ["Organizer", "Historian", "Contributor"],
  },
  wedding: {
    label: "Wedding",
    noun: "wedding",
    placeholder: "Amara and Kofi's Wedding",
    roles: ["Organizer", "Treasurer", "Communications Lead"],
  },
  custom: {
    label: "Other",
    noun: "gathering",
    placeholder: "Sunday family dinner",
    roles: ["Organizer", "Historian", "Contributor"],
  },
});

const DEFAULT_GATHERING_TYPE = "reunion";

export const emptyReunionDraft = Object.freeze({
  client_request_id: "",
  gathering_type: DEFAULT_GATHERING_TYPE,
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
  const gatheringType = Object.prototype.hasOwnProperty.call(GATHERING_TYPES, value.gathering_type)
    ? value.gathering_type
    : DEFAULT_GATHERING_TYPE;
  return {
    client_request_id: clean(value.client_request_id, 100) || createClientRequestId(),
    gathering_type: gatheringType,
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

export function applyPreferredGatheringType(value, requestedType) {
  const draft = normalizeReunionDraft(value);
  if (!Object.prototype.hasOwnProperty.call(GATHERING_TYPES, requestedType)) return draft;
  const alreadyStarted = Boolean(
    draft.gathering_name
    || draft.approximate_date
    || draft.end_date
    || draft.organizer_name
    || draft.location
  );
  return alreadyStarted ? draft : { ...draft, gathering_type: requestedType };
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
  // The date is deliberately NOT required. An organizer arrives because the
  // date is the thing they are still negotiating with forty relatives, and
  // demanding it before they can see anything was the wall the start form
  // died on. The invitation preview already renders "Date to be confirmed".
  const complete = Boolean(
    draft?.gathering_name
    && draft?.organizer_name
    && validReunionTimezone(draft?.timezone)
  );
  if (!complete) return false;
  // An end date only has to follow a start date that actually exists.
  if (!draft.end_date) return true;
  return !draft.approximate_date || draft.end_date >= draft.approximate_date;
}

export function gatheringTypeDetails(draft) {
  return GATHERING_TYPES[normalizeReunionDraft(draft).gathering_type];
}

// Holiday meal mirrors the backend template defaults. Every other public
// starting point remains a general event until the organizer adds details.
function starterContent(normalized) {
  if (normalized.gathering_type === "holiday_meal") {
    return {
      agenda: ["Welcome or arrival", "Meal time", "Cleanup"].map((title) => ({ title, visibility: "draft" })),
      volunteer_slots: [
        { title: "Setup", needed_count: 1 },
        { title: "Cleanup", needed_count: 1 },
      ],
      potluck_items: ["Main dish", "Side dish", "Dessert", "Drinks or supplies"],
    };
  }
  return {
    agenda: [],
    volunteer_slots: [],
    potluck_items: [],
  };
}

export function reunionDraftToEventPayload(draft) {
  const normalized = normalizeReunionDraft(draft);
  const type = GATHERING_TYPES[normalized.gathering_type];
  const endDate = normalized.end_date || normalized.approximate_date;
  const startAt = `${normalized.approximate_date}T09:00:00`;
  const endAt = `${endDate}T18:00:00`;
  const description = `A private ${type.noun} organized by ${normalized.organizer_name}.`;
  return {
    client_request_id: normalized.client_request_id,
    title: normalized.gathering_name,
    description,
    start_at: startAt,
    end_at: endAt,
    timezone: normalized.timezone,
    location: normalized.location,
    event_template: normalized.gathering_type === "reunion" ? "custom" : normalized.gathering_type,
    gathering_format: "in-person",
    max_attendees: 50,
    recurrence_frequency: "none",
    assigned_roles: [...type.roles],
    ...starterContent(normalized),
    travel_coordination_notes: "",
    suggested_contribution: 0,
  };
}

// New public drafts open the general gathering page. Existing reunion events
// keep their dedicated activation route elsewhere in the product.
export function draftLandingPath(_draft, eventId) {
  return `/gatherings/${eventId}`;
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
  return `${normalized.gathering_name || "Event"} planning space`;
}
