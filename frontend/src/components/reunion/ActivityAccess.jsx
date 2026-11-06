import { Lock, Video } from "lucide-react";

export const VIRTUAL_LINK_WITHHELD_NOTICE = "Link shared with registered attendees.";

/**
 * Shows an activity's virtual link to people allowed to see it, and the
 * withheld notice to everyone else. The server decides who may see the link;
 * this component only renders what it was sent.
 */
export const ActivityAccess = ({ activity, className = "" }) => {
  if (activity?.virtual_link) {
    return (
      <p className={`flex items-center gap-2 text-sm ${className}`} data-testid={`activity-virtual-link-${activity.id}`}>
        <Video aria-hidden="true" className="h-4 w-4 shrink-0" />
        <a className="font-semibold underline" href={activity.virtual_link} rel="noopener noreferrer" target="_blank">
          Join online
        </a>
      </p>
    );
  }
  if (activity?.virtual_link_withheld) {
    return (
      <p className={`flex items-center gap-2 text-sm text-muted-foreground ${className}`} data-testid={`activity-virtual-link-withheld-${activity.id}`}>
        <Lock aria-hidden="true" className="h-4 w-4 shrink-0" />
        {activity.virtual_link_notice || VIRTUAL_LINK_WITHHELD_NOTICE}
      </p>
    );
  }
  return null;
};

export const choicesApply = (activity, status) => (
  Boolean(activity?.response_choices?.length) && (status === "coming" || status === "maybe")
);

/**
 * Organizer-defined options (for example "In person" / "Remote"), offered once
 * someone answers "coming" or "maybe".
 */
export const ActivityChoicePicker = ({ activity, status, value, onChange, disabled = false }) => {
  if (!choicesApply(activity, status)) return null;
  return (
    <fieldset className="mt-3" data-testid={`activity-choices-${activity.id}`}>
      <legend className="text-sm font-semibold">
        How will you join?<span className="sr-only"> ({activity.title})</span>
      </legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {activity.response_choices.map((choice) => (
          <button
            aria-pressed={value === choice}
            className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${value === choice ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}
            disabled={disabled}
            key={choice}
            onClick={() => onChange(choice)}
            type="button"
          >
            {choice}
          </button>
        ))}
      </div>
    </fieldset>
  );
};

/** "In person: 4 · Remote: 2" for organizer counts. */
export const choiceCountsLabel = (choiceSummary) => {
  const entries = Object.entries(choiceSummary?.choices || {});
  if (!entries.length) return "";
  const parts = entries.map(([label, counts]) => `${label}: ${counts.coming || 0}`);
  if (choiceSummary?.unspecified?.coming) parts.push(`No option chosen: ${choiceSummary.unspecified.coming}`);
  return parts.join(" · ");
};

export const closedResponseMessage = (activity) => (
  activity?.rsvp_deadline
    ? "This activity’s response deadline has passed. Your saved choice remains visible."
    : "This activity has ended and is no longer taking responses. Your saved choice remains visible."
);
