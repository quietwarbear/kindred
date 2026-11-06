// Helpers for the organizer's announcements & reminders panel (K5).
// The server resolves audiences, schedules and delivery; these only shape
// what the organizer sees and sends.

export const OFFSET_PRESETS = [
  { minutes: 10080, label: "1 week before" },
  { minutes: 2880, label: "2 days before" },
  { minutes: 1440, label: "24 hours before" },
  { minutes: 180, label: "3 hours before" },
  { minutes: 60, label: "1 hour before" },
  { minutes: 15, label: "15 minutes before" },
];
export const DEFAULT_OFFSETS = [1440, 60];
export const MAX_OFFSETS = 4;

export const offsetLabel = (minutes) => {
  const preset = OFFSET_PRESETS.find((p) => p.minutes === minutes);
  if (preset) return preset.label;
  if (minutes % 1440 === 0) return `${minutes / 1440} days before`;
  if (minutes % 60 === 0) return `${minutes / 60} hours before`;
  return `${minutes} minutes before`;
};

export const describeOffsets = (offsets = []) =>
  offsets.length ? [...offsets].sort((a, b) => b - a).map(offsetLabel).join(", ") : "No reminders";

// Toggle one offset in a list, keeping it sorted (largest first) and bounded.
export const toggleOffset = (offsets = [], minutes) => {
  const set = new Set(offsets);
  if (set.has(minutes)) set.delete(minutes);
  else if (set.size < MAX_OFFSETS) set.add(minutes);
  return [...set].sort((a, b) => b - a);
};

// Per-activity override for the settings payload: "default" omits the
// activity, "off" sends an empty list, "custom" sends its own offsets.
export const buildOverrides = (choices = {}) => {
  const overrides = {};
  Object.entries(choices).forEach(([activityId, choice]) => {
    if (!choice || choice.mode === "default") return;
    overrides[activityId] = choice.mode === "off" ? [] : [...(choice.offsets || [])];
  });
  return overrides;
};

export const choicesFromSettings = (activities = [], overrides = {}) =>
  Object.fromEntries(
    activities.map((a) => {
      if (!(a.id in overrides)) return [a.id, { mode: "default", offsets: [] }];
      const offsets = overrides[a.id] || [];
      return [a.id, { mode: offsets.length ? "custom" : "off", offsets }];
    })
  );

export const dayLabel = (day) => {
  const parsed = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return day;
  return parsed.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" });
};

export const sendTimeLabel = (iso) => {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

export const audienceSummary = (preview) => {
  if (!preview) return "";
  const n = preview.recipients || 0;
  if (!n) return "Nobody matches this audience yet.";
  const people = `${n} ${n === 1 ? "person" : "people"}`;
  const email = preview.with_email === n ? "all with email" : `${preview.with_email || 0} with email`;
  const app = `${preview.with_account || 0} in the app`;
  return `${people} · ${email} · ${app}`;
};

const EMAIL_RESULT_LABELS = {
  accepted: "emailed",
  opted_out: "opted out of email",
  no_address: "without an email address",
  unavailable: "not emailed (email is off)",
  rejected: "rejected",
  ambiguous: "unconfirmed",
  failed: "failed",
};

export const deliveryLine = (summary) => {
  if (!summary || !summary.recipients) return "In the app only";
  const parts = [];
  Object.entries(summary.email || {}).forEach(([key, n]) => {
    parts.push(`${n} ${EMAIL_RESULT_LABELS[key] || key}`);
  });
  const pushed = summary.push?.delivered || 0;
  if (pushed) parts.push(`${pushed} push`);
  if (summary.opted_out) parts.push(`${summary.opted_out} opted out`);
  if (summary.pending) parts.push(`${summary.pending} sending`);
  return parts.length ? parts.join(" · ") : `${summary.recipients} recipients`;
};

export const readinessNotes = (delivery = {}) => {
  const notes = [];
  if (delivery.email === "off") notes.push("Email delivery is off on this deployment; messages still appear in the app.");
  if (delivery.email === "unverified_sender") notes.push("Email is paused: the sending address isn't on a verified domain.");
  if (delivery.push === "off") notes.push("Push notifications are off on this deployment.");
  if (delivery.scheduler === "not_configured") notes.push("Scheduled reminders aren't running yet: the reminder schedule hasn't been connected.");
  return notes;
};
