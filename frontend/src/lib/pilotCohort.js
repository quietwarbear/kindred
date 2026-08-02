export const PILOT_STATUS_LABELS = {
  not_enrolled: "Not enrolled",
  enrolled: "Enrolled",
  consented: "Consent recorded",
  active: "Active",
  completed: "Completed",
  withdrawn: "Withdrawn",
};

export const PILOT_ACTION_LABELS = {
  enroll: "Enroll",
  record_consent: "Record consent",
  activate: "Activate",
  complete: "Mark complete",
  withdraw: "Withdraw",
};

export const pilotStatusLabel = (status) =>
  PILOT_STATUS_LABELS[status] || PILOT_STATUS_LABELS.not_enrolled;

export const pilotActionLabel = (action) => PILOT_ACTION_LABELS[action] || action;

// A status is "in the cohort" once it's past not_enrolled.
export const isInCohort = (status) => Boolean(status) && status !== "not_enrolled";
