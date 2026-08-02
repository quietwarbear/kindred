export const toDateTimeLocalValue = (value, timezone) => {
  if (!value) return "";
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(value)) return value.slice(0, 16);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      day: "2-digit",
      hour: "2-digit",
      hour12: false,
      minute: "2-digit",
      month: "2-digit",
      timeZone: timezone || "UTC",
      year: "numeric",
    }).formatToParts(parsed).map((part) => [part.type, part.value])
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
};

export const uniqueGuestCount = (value) => new Set(
  String(value || "")
    .split(",")
    .map((candidate) => candidate.trim().toLowerCase())
    .filter(Boolean)
).size;

// Normalize the server's content-free aggregate counts for display. Every value
// is a non-negative integer; nothing here is derived from names, emails, links,
// or credentials — only the bounded counts the readiness endpoint returns.
export const invitationActivationSummary = (counts) => {
  const safe = (key) => {
    const value = Number((counts || {})[key]);
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
  };
  return {
    prepared: safe("active_invitations"),
    shared: safe("invitations_shared"),
    reached: safe("invitations_reached"),
    opened: safe("invitations_opened"),
    seen: safe("invitations_seen"),
    delivered: safe("invitations_delivered"),
    responses: safe("responses_received"),
    awaiting: safe("invitations_awaiting_response"),
  };
};
