import { invitationActivationSummary } from "./holidayPilot";

// Friendly, organizer-facing labels for the server's next-action codes. The
// codes are categorical and content-free; this only translates them for display.
export const NEXT_ACTION_LABELS = {
  finish_setup: "Finish setup",
  prepare_invitations: "Prepare invitations",
  share_invitations: "Share the invitations",
  send_reminders: "Send a reminder",
  review_response_gaps: "Follow up on missing responses",
  review_recap: "Review the recap",
  review_pilot: "Review the plan",
  essential_details: "Add the essential details",
  schedule_and_timezone: "Set the schedule and timezone",
  rsvp_window: "Set the RSVP deadline",
  privacy_reviewed: "Complete the privacy review",
  guest_plan_reviewed: "Review the guest plan",
  organizer_previewed: "Preview what guests will see",
};

// Build a content-free activation funnel from the readiness aggregate counts.
// Every value is a bounded, non-negative integer; percentages are ratios of
// those counts. No names, contacts, or links are ever involved.
export const buildActivationFunnel = (counts, nextActionCode) => {
  const s = invitationActivationSummary(counts);
  const prepared = s.prepared;
  const pct = (n) => (prepared > 0 ? Math.round((Math.min(n, prepared) / prepared) * 100) : 0);

  // Stages are nested-by-construction on the server (prepared >= reached >= seen
  // >= responded), so the funnel is monotonic: a downstream stage can never show
  // a higher count than an upstream one. "Reached" = the invite left the app;
  // "Opened" = opened or answered.
  const stages = [
    { key: "prepared", label: "Prepared", count: prepared, pct: prepared > 0 ? 100 : 0 },
    { key: "reached", label: "Reached", count: s.reached, pct: pct(s.reached) },
    { key: "opened", label: "Opened", count: s.seen, pct: pct(s.seen) },
    { key: "responded", label: "Responded", count: s.responses, pct: pct(s.responses) },
  ];

  const code = nextActionCode || "";
  return {
    stages,
    prepared,
    shared: s.shared,
    delivered: s.delivered,
    awaiting: s.awaiting,
    hasActivity: prepared > 0,
    nextAction: code
      ? { code, label: NEXT_ACTION_LABELS[code] || "Review the plan" }
      : null,
  };
};
