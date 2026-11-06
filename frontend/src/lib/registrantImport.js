// Helpers for the organizer's registrant import panel (K2).
// The server does all matching; these only shape what the organizer sees.

export const MAX_CSV_BYTES = 1_000_000;

export const ROW_STATUS_LABELS = {
  created: "Invited",
  updated: "Updated",
  skipped: "No change",
  flagged: "Possible duplicate",
  error: "Error",
};

export const webhookUrl = (backendUrl, path) =>
  path ? `${String(backendUrl || "").replace(/\/+$/, "")}${path}` : "";

export const reportSummary = (counts = {}) => {
  const parts = [];
  const add = (n, one, many) => {
    if (n) parts.push(`${n} ${n === 1 ? one : many}`);
  };
  add(counts.created, "invited", "invited");
  add(counts.updated, "updated", "updated");
  add(counts.skipped, "unchanged", "unchanged");
  add(counts.flagged, "possible duplicate", "possible duplicates");
  add(counts.error, "error", "errors");
  return parts.length ? parts.join(" · ") : "Nothing to import.";
};

export const deliverySummary = (delivery) => {
  if (!delivery || delivery.status === "not_requested") return "";
  if (delivery.status === "unavailable") {
    return delivery.error_code === "delivery_disabled"
      ? "Email delivery is off on this deployment, so share each person's link instead."
      : "Email delivery isn't fully configured yet, so share each person's link instead.";
  }
  const sent = delivery.counts?.submitted || 0;
  const skipped = delivery.counts?.skipped || 0;
  const problems =
    (delivery.counts?.rejected || 0) + (delivery.counts?.failed || 0) + (delivery.counts?.ambiguous || 0);
  let text = `Emailed ${sent} invitation${sent === 1 ? "" : "s"}.`;
  if (skipped) text += ` ${skipped} already had one.`;
  if (problems) text += ` ${problems} could not be sent.`;
  return text;
};

// Errors and flags first, so the rows that need the organizer are on top.
const STATUS_ORDER = { error: 0, flagged: 1, created: 2, updated: 3, skipped: 4 };

export const sortReportRows = (rows = []) =>
  [...rows].sort(
    (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) || (a.row || 0) - (b.row || 0)
  );

export const CSV_TEMPLATE = "Name,Email,Sessions purchased\nAda Example,ada@example.com,Day One; Day Two\n";

export const csvTemplateFor = (event) => {
  const titles = (event?.agenda || [])
    .filter((a) => a.visibility === "published" && a.attendance_requested !== false && a.title)
    .map((a) => a.title.replace(/[;|"\n]/g, " ").trim())
    .filter(Boolean);
  if (!titles.length) return CSV_TEMPLATE;
  const sessions = titles.slice(0, 2).join("; ");
  return `Name,Email,Sessions purchased\nAda Example,ada@example.com,"${sessions}"\n`;
};
