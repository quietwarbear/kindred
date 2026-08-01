import { useCallback, useState } from "react";
import { CheckCircle2, Circle, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api";
import { invitationActivationSummary } from "@/lib/holidayPilot";
import { toast } from "@/components/ui/sonner";

const STAGE_COPY = {
  active: "Dinner in progress",
  archived: "Pilot archived",
  completed: "Dinner completed",
  draft: "Private organizer draft",
  invitations_sent: "Invitations sent",
  ready_to_invite: "Ready to invite",
};

const CHECK_COPY = {
  essential_details: ["Essential details", "Name, location, and capacity are complete."],
  schedule_and_timezone: ["Schedule and timezone", "Start and end resolve to one valid local timeline."],
  rsvp_window: ["RSVP deadline", "The response deadline is valid and no later than dinner."],
  privacy_reviewed: ["Privacy review", "Confirm who can see the draft and what guests will receive."],
  guest_plan_reviewed: ["Guest plan", "Preview the intended member and guest groups before generating links."],
  food_coordination: ["Food and help", "At least one dish or volunteer need is ready; optional for setup."],
  reminder_plan_reviewed: ["Reminder plan", "Choose how the organizer will follow up; optional for setup."],
  organizer_previewed: ["Organizer preview", "Review the attendee-facing schedule and invitation plan."],
  invitations_shared: ["Invitations shared", "Confirm only after the prepared private links have been shared."],
};

export const HolidayPilotReadiness = ({ event, onFinishSetup, onUpdate, token }) => {
  const [savingCode, setSavingCode] = useState("");
  const readiness = event.holiday_pilot_readiness || {};
  const checklist = readiness.checklist || [];
  const counts = readiness.aggregate_counts || {};
  const activation = invitationActivationSummary(counts);
  const isDraft = readiness.pilot_stage === "draft";

  const updateConfirmation = useCallback(async (item) => {
    if (!item.confirmation_action) return;
    setSavingCode(item.code);
    try {
      const payload = await apiRequest(`/events/${event.id}/holiday-pilot-checklist`, {
        method: "POST",
        token,
        data: {
          code: item.confirmation_action,
          checked: item.status !== "complete",
        },
      });
      onUpdate(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail?.code || "Unable to update the pilot checklist.");
    } finally {
      setSavingCode("");
    }
  }, [event.id, onUpdate, token]);

  if (!readiness.pilot_stage) return null;

  return (
    <section className="rounded-2xl border border-primary/30 bg-primary/5 p-4" data-testid="holiday-pilot-readiness">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <p className="eyebrow-text">Thanksgiving pilot readiness</p>
          </div>
          <h4 className="mt-2 font-display text-2xl text-foreground" data-testid="holiday-pilot-stage">
            {STAGE_COPY[readiness.pilot_stage] || "Pilot review"}
          </h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {readiness.required_complete_count || 0} of {readiness.required_total_count || 0} required checks complete. Creating and reviewing this draft sends nothing.
          </p>
        </div>
        {isDraft ? (
          <Button
            className="rounded-full"
            data-testid="holiday-pilot-finish-setup"
            disabled={!readiness.can_finish_setup}
            onClick={onFinishSetup}
            size="sm"
            type="button"
          >
            Finish setup
          </Button>
        ) : null}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2" data-testid="holiday-pilot-checklist">
        {checklist.map((item) => {
          const complete = item.status === "complete";
          const copy = CHECK_COPY[item.code] || [item.code, "Review this pilot item."];
          const sharedWithoutInvites = item.code === "invitations_shared" && !(counts.active_invitations > 0);
          return (
            <button
              className={`rounded-xl border p-3 text-left ${complete ? "border-emerald-300 bg-emerald-50/70 dark:bg-emerald-950/20" : "border-border bg-background/70"}`}
              data-testid={`holiday-pilot-check-${item.code}`}
              disabled={!item.confirmation_action || savingCode === item.code || sharedWithoutInvites}
              key={item.code}
              onClick={() => updateConfirmation(item)}
              type="button"
            >
              <span className="flex items-start gap-2">
                {complete ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />}
                <span>
                  <span className="block text-sm font-semibold text-foreground">{copy[0]}</span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">{copy[1]}</span>
                  <span className="mt-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">
                    {item.required_for_setup ? "Required before finish setup" : "Recommended"}
                  </span>
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4" data-testid="holiday-pilot-counts">
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground">{counts.active_invitations || 0}</strong>invites prepared</div>
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground">{counts.responses_received || 0}</strong>responses</div>
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground">{counts.potluck_items || 0}</strong>dish needs</div>
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground">{counts.volunteer_positions || 0}</strong>helping spots</div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs" data-testid="holiday-pilot-activation">
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground" data-testid="holiday-pilot-activation-shared">{activation.shared}</strong>shared</div>
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground" data-testid="holiday-pilot-activation-opened">{activation.opened}</strong>opened</div>
        <div className="rounded-xl bg-background/70 p-3"><strong className="block text-lg text-foreground" data-testid="holiday-pilot-activation-delivered">{activation.delivered}</strong>delivered</div>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
        Activation is measured privately from bounded counts only — never names, contacts, or links.
      </p>
    </section>
  );
};
