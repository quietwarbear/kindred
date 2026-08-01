import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  Eye,
  LockKeyhole,
  Mail,
  RefreshCw,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { toast } from "@/components/ui/sonner";

const ACTIONS = {
  complete_reunion_details: ["Complete the reunion details", "Confirm the date, timezone, and location."],
  confirm_itinerary: ["Confirm the itinerary", "Publish the first guest-visible activity."],
  create_first_invitation: ["Create the first invitation", "Add one relative so the private RSVP loop can begin."],
  share_invitations: ["Share the private invitations", "Use a trusted channel; RSVP links stay in the browser fragment."],
  resolve_approaching_deadline: ["Resolve the approaching deadline", "Responses are still missing before a deadline."],
  follow_up_missing_responses: ["Follow up on missing responses", "Review the safe reminder preflight before contacting anyone."],
  fill_planning_roles: ["Fill the next planning role", "Give one clear responsibility to an authorized helper."],
  resolve_contribution_gaps: ["Resolve contribution gaps", "Potluck items or volunteer roles still need owners."],
  review_travel_gaps: ["Review travel and lodging gaps", "Capture the travel coordination the family still needs."],
  prepare_story_prompts: ["Prepare a family story prompt", "Invite one memory before everyone arrives."],
  review_reunion_plan: ["Review the reunion plan", "Everything essential is moving; check the next few details."],
};

const ACTION_DESTINATIONS = {
  complete_reunion_details: "itinerary",
  confirm_itinerary: "itinerary",
  create_first_invitation: "invitations",
  share_invitations: "invitations",
  resolve_approaching_deadline: "responses",
  follow_up_missing_responses: "responses",
  fill_planning_roles: "planning-team",
  resolve_contribution_gaps: "planning",
  review_travel_gaps: "planning",
  prepare_story_prompts: "planning",
  review_reunion_plan: "planning",
};

const STATUS_LABELS = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
  active: "Active",
  invited: "Invitation pending",
};

const stableOperationKey = (prefix, eventId) => {
  const storageKey = `kindred:${prefix}:${eventId}`;
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${prefix}:${random}`;
  window.sessionStorage.setItem(storageKey, value);
  return value;
};

const StatusCard = ({ label, value, detail, testId }) => (
  <article className="soft-panel" data-testid={testId}>
    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
    <p className="mt-3 text-2xl font-semibold text-foreground">{value}</p>
    {detail ? <p className="mt-1 text-sm text-muted-foreground">{detail}</p> : null}
  </article>
);

export const OrganizerCommandCenterPage = ({ session }) => {
  const { eventId } = useParams();
  const [command, setCommand] = useState(null);
  const [event, setEvent] = useState(null);
  const [members, setMembers] = useState([]);
  const [planningTeam, setPlanningTeam] = useState({ assigned: [], pending_invitations: [] });
  const [preview, setPreview] = useState(null);
  const [familyReadiness, setFamilyReadiness] = useState(null);
  const [familyAccessRequests, setFamilyAccessRequests] = useState([]);
  const [familyAccessBusy, setFamilyAccessBusy] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [planningEmail, setPlanningEmail] = useState("");
  const [planningBusy, setPlanningBusy] = useState("");
  const [reminderBusy, setReminderBusy] = useState(false);
  const viewedRef = useRef(false);
  const plannerInviteKeysRef = useRef(new Map());
  const plannerAssignmentKeysRef = useRef(new Map());

  const load = useCallback(async () => {
    if (!session?.token || !eventId) return;
    setLoadError("");
    try {
      const [commandPayload, eventPayload, membersPayload, planningTeamPayload, familyPayload, familyAccessPayload] = await Promise.all([
        apiRequest(`/events/${eventId}/command-center`, { token: session.token }),
        apiRequest(`/events/${eventId}`, { token: session.token }),
        apiRequest("/community/members", { token: session.token }),
        apiRequest(`/events/${eventId}/planning-team`, { token: session.token }),
        apiRequest("/family-space/activation", { token: session.token }),
        apiRequest("/family-access/organizer/requests", { token: session.token }).catch((error) => {
          if (error.response?.status === 404) return { requests: [] };
          throw error;
        }),
      ]);
      setCommand(commandPayload);
      setEvent(eventPayload);
      setMembers(membersPayload.members || []);
      setPlanningTeam(planningTeamPayload);
      setFamilyReadiness(familyPayload);
      setFamilyAccessRequests(familyAccessPayload.requests || []);
    } catch (error) {
      setLoadError(
        error.response?.status === 403
          ? "This command center is available only to reunion organizers."
          : error.response?.data?.detail || "This reunion command center could not be opened."
      );
    } finally {
      setLoading(false);
    }
  }, [eventId, session?.token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!command || viewedRef.current) return;
    viewedRef.current = true;
    const nextCode = command.next_action?.code || "review_reunion_plan";
    trackReunionEvent("command_center_viewed", {
      source: "organizer_command_center",
      status: command.responses?.responded > 0 ? "responses_started" : "awaiting_first_response",
    });
    trackReunionEvent("next_action_viewed", {
      source: "organizer_command_center",
      action_code: nextCode,
    });
    const pendingKey = `kindred:pending-next-action:${eventId}`;
    const pending = window.sessionStorage.getItem(pendingKey);
    if (pending && pending !== nextCode) {
      trackReunionEvent("next_action_completed", {
        source: "organizer_command_center",
        action_code: pending,
      });
      window.sessionStorage.removeItem(pendingKey);
    }
    if (command.responses?.responded > 0) {
      const returnKey = `kindred:organizer-returned:${eventId}`;
      if (!window.sessionStorage.getItem(returnKey)) {
        trackReunionEvent("organizer_returned_after_first_rsvp", {
          source: "organizer_command_center",
          return_reason: "response_received",
        });
        window.sessionStorage.setItem(returnKey, "1");
      }
    }
  }, [command, eventId]);

  const organizerMembers = useMemo(
    () => members.filter((member) => ["host", "organizer"].includes(member.role)),
    [members]
  );
  const assignedIds = useMemo(
    () => new Set(event?.planning_team_member_ids || []),
    [event?.planning_team_member_ids]
  );

  if (!session?.token) {
    return <Navigate replace to="/login?intent=reunion" />;
  }

  const openPreview = async () => {
    try {
      if (!preview) {
        setPreview(await apiRequest(`/events/${eventId}/guest-preview`, { token: session.token }));
      }
      setShowPreview((current) => !current);
      trackReunionEvent("reunion_preview_viewed", { source: "organizer_command_center" });
    } catch (error) {
      toast.error(error.response?.data?.detail || "Guest preview is unavailable.");
    }
  };

  const beginNextAction = () => {
    const actionCode = command?.next_action?.code || "review_reunion_plan";
    window.sessionStorage.setItem(`kindred:pending-next-action:${eventId}`, actionCode);
    document.getElementById(ACTION_DESTINATIONS[actionCode] || "planning")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const checkReminderPreflight = async () => {
    setReminderBusy(true);
    try {
      const result = await apiRequest(`/events/${eventId}/reminders/preflight`, {
        method: "POST",
        token: session.token,
        data: { idempotency_key: stableOperationKey("reminder", eventId) },
      });
      setCommand((current) => ({ ...current, reminders: result }));
      trackReunionEvent(
        result.available ? "reminder_preflight_passed" : "reminder_preflight_failed",
        {
          source: "organizer_command_center",
          reminder_code: result.code,
          result: result.available ? "passed" : "failed",
        }
      );
      toast[result.available ? "success" : "info"](
        result.available
          ? "Reminder delivery preflight passed."
          : "Reminder delivery is safely unavailable. Nothing was sent or changed."
      );
    } catch (error) {
      trackReunionEvent("reminder_preflight_failed", {
        source: "organizer_command_center",
        result: "request_failed",
      });
      toast.error(error.response?.data?.detail || "Reminder preflight could not be completed.");
    } finally {
      setReminderBusy(false);
    }
  };

  const invitePlanner = async (submitEvent) => {
    submitEvent.preventDefault();
    setPlanningBusy("invite");
    const normalizedPlanningEmail = planningEmail.trim().toLowerCase();
    if (!plannerInviteKeysRef.current.has(normalizedPlanningEmail)) {
      const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      plannerInviteKeysRef.current.set(normalizedPlanningEmail, `planner-invite:${random}`);
    }
    trackReunionEvent("planning_team_setup_started", {
      source: "organizer_command_center",
      planning_team_state: "invitation",
    });
    try {
      await apiRequest(`/events/${eventId}/planning-team/invitations`, {
        method: "POST",
        token: session.token,
        data: {
          email: planningEmail,
          idempotency_key: plannerInviteKeysRef.current.get(normalizedPlanningEmail),
        },
      });
      setPlanningEmail("");
      plannerInviteKeysRef.current.delete(normalizedPlanningEmail);
      trackReunionEvent("planning_team_setup_completed", {
        source: "organizer_command_center",
        planning_team_state: "invited_or_assigned",
      });
      toast.success("Planning help was added safely.");
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Planning help could not be added.");
    } finally {
      setPlanningBusy("");
    }
  };

  const togglePlanner = async (memberId, assigned) => {
    setPlanningBusy(memberId);
    try {
      if (assigned) {
        await apiRequest(`/events/${eventId}/planning-team/assignments/${memberId}`, {
          method: "DELETE",
          token: session.token,
        });
      } else {
        if (!plannerAssignmentKeysRef.current.has(memberId)) {
          const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
          plannerAssignmentKeysRef.current.set(memberId, `planner-assignment:${random}`);
        }
        trackReunionEvent("planning_team_setup_started", {
          source: "organizer_command_center",
          planning_team_state: "assignment",
        });
        await apiRequest(`/events/${eventId}/planning-team/assignments`, {
          method: "POST",
          token: session.token,
          data: {
            member_id: memberId,
            idempotency_key: plannerAssignmentKeysRef.current.get(memberId),
          },
        });
        trackReunionEvent("planning_team_setup_completed", {
          source: "organizer_command_center",
          planning_team_state: "assigned",
        });
        plannerAssignmentKeysRef.current.delete(memberId);
      }
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Planning-team assignment could not be updated.");
    } finally {
      setPlanningBusy("");
    }
  };

  const revokePlanningInvitation = async (invitationId) => {
    setPlanningBusy(invitationId);
    try {
      await apiRequest(`/events/${eventId}/planning-team/invitations/${invitationId}`, {
        method: "DELETE",
        token: session.token,
      });
      toast.success("Planning-team invitation revoked.");
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Planning-team invitation could not be revoked.");
    } finally {
      setPlanningBusy("");
    }
  };

  const decideFamilyAccess = async (request, decision) => {
    const busyKey = `${request.request_reference}:${decision}`;
    setFamilyAccessBusy(busyKey);
    const storageKey = `kindred:family-access-decision:${busyKey}`;
    let idempotencyKey = window.sessionStorage.getItem(storageKey);
    if (!idempotencyKey) {
      idempotencyKey = `family-access-decision:${window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`}`;
      window.sessionStorage.setItem(storageKey, idempotencyKey);
    }
    try {
      const result = await apiRequest("/family-access/organizer/decision", {
        method: "POST", token: session.token,
        data: {
          request_reference: request.request_reference,
          decision,
          expected_revision: request.revision,
          idempotency_key: idempotencyKey,
        },
      });
      window.sessionStorage.removeItem(storageKey);
      trackReunionEvent("guest_family_access_decided", {
        source: "organizer_command_center", request_state: result.status, decision,
      });
      if (decision === "approved" && result.status === "approved") {
        trackReunionEvent("family_access_approved", {
          source: "organizer_command_center", request_state: "approved", decision: "approved",
        });
      }
      toast.success(`Family access request ${result.status}.`);
      await load();
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || "This request changed. Refresh before deciding.");
    } finally {
      setFamilyAccessBusy("");
    }
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true">
        <p className="text-sm text-muted-foreground">Preparing the organizer command center…</p>
      </div>
    );
  }

  if (loadError || !command || !event) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-6">
        <section className="archival-card max-w-xl text-center" role="alert">
          <LockKeyhole className="mx-auto h-6 w-6 text-primary" />
          <h1 className="mt-4 font-display text-3xl">Organizer access required</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError}</p>
          <Button asChild className="mt-5" variant="outline">
            <Link to="/gatherings">Return to gatherings</Link>
          </Button>
        </section>
      </div>
    );
  }

  const [actionTitle, actionCopy] = ACTIONS[command.next_action.code] || ACTIONS.review_reunion_plan;
  const progressEntries = Object.entries(command.progress).filter(
    ([key, value]) => key !== "budget" || value
  );

  return (
    <div
      className="app-canvas min-h-screen"
      data-ph-no-capture="true"
      data-testid="organizer-command-center"
      style={{
        paddingTop: "env(safe-area-inset-top, 0px)",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        paddingLeft: "env(safe-area-inset-left, 0px)",
        paddingRight: "env(safe-area-inset-right, 0px)",
      }}
    >
      <main className="page-section space-y-6 py-6 sm:py-10">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <Button asChild variant="ghost">
            <Link to={`/reunion/activate/${eventId}`}>
              <ChevronLeft className="mr-2 h-4 w-4" /> Reunion workspace
            </Link>
          </Button>
          <Button onClick={openPreview} type="button" variant="outline">
            <Eye className="mr-2 h-4 w-4" /> {showPreview ? "Hide guest preview" : "Preview guest experience"}
          </Button>
        </header>

        {familyReadiness?.lifecycle_state === "provisional" ? (
          <section className="archival-card flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between" data-testid="command-center-family-activation-card">
            <div>
              <p className="eyebrow-text">After the reunion</p>
              <h2 className="mt-2 font-display text-3xl">{familyReadiness.ready ? "Your family space is ready to keep." : "Your family space is taking shape."}</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">
                {familyReadiness.ready
                  ? "Choose its enduring name without changing invitations, members, memories, or reunion history."
                  : "Keep coordinating the reunion. You can activate later without losing access to this command center."}
              </p>
            </div>
            <Button asChild variant={familyReadiness.ready ? "default" : "outline"}>
              <Link to="/family/activate">Review family-space readiness <ArrowRight className="ml-2 h-4 w-4" /></Link>
            </Button>
          </section>
        ) : null}

        {command.recap?.completion_state === "ready" ? (
          <section className="archival-card flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between" data-testid="command-center-recap-card">
            <div>
              <p className="eyebrow-text">Reunion concluded</p>
              <h2 className="mt-2 font-display text-3xl">Review the private family recap</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">Publish an optional family message, review safe participation totals, or explicitly begin the next gathering.</p>
            </div>
            <Button asChild><Link to={`/reunion/recap/${eventId}`}>Open recap and continuity <ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
          </section>
        ) : null}

        <section className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.2fr_0.8fr]">
            <div className="p-6 sm:p-8">
              <p className="eyebrow-text">Organizer command center</p>
              <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl">{actionTitle}</h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">{actionCopy}</p>
              <Button className="mt-6" data-testid="command-center-next-action" onClick={beginNextAction} type="button">
                Take the next step <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
            <div className="bg-stone-950 p-6 text-white sm:p-8">
              <ShieldCheck className="h-6 w-6 text-orange-200" />
              <p className="mt-4 text-lg font-semibold">Private organizer view</p>
              <p className="mt-3 text-sm leading-6 text-stone-300">
                Response gaps, internal progress, and planning-team status stay here. The guest preview below uses the same field boundary as the real private RSVP link.
              </p>
            </div>
          </div>
        </section>

        {showPreview && preview ? (
          <section className="archival-card" data-testid="command-center-guest-preview">
            <p className="eyebrow-text">Exactly what an invited guest can see</p>
            <h2 className="mt-2 font-display text-3xl">{preview.gathering?.title}</h2>
            <p className="mt-3 text-sm text-muted-foreground">
              {preview.gathering?.start_at || "Date to be confirmed"} · {preview.gathering?.location || "Location to be confirmed"}
            </p>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">{preview.gathering?.description}</p>
            <p className="mt-4 text-xs text-muted-foreground">
              {preview.gathering?.activity_count || 0} published guest-visible activities. No response gaps, invite ledger, planning roles, budget, travel records, or organizer notes are included.
            </p>
          </section>
        ) : null}

        <section className="archival-card" id="responses">
          <div className="flex items-start gap-3">
            <Users className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Responses</p>
              <h2 className="mt-2 font-display text-3xl">Who has answered?</h2>
            </div>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatusCard detail="Active invitations" label="Invited" testId="command-response-total" value={command.responses.total} />
            <StatusCard detail="Canonical responses" label="Responded" testId="command-response-responded" value={command.responses.responded} />
            <StatusCard detail="Safe aggregate only" label="Still missing" testId="command-response-missing" value={command.responses.missing} />
            <StatusCard detail={command.responses.reconciles ? "Counts reconcile" : "Needs review"} label="Integrity" testId="command-response-integrity" value={command.responses.reconciles ? "Confirmed" : "Check"} />
          </div>
        </section>

        <section className="archival-card" id="family-access" data-testid="organizer-family-access-requests">
          <div className="flex items-start gap-3">
            <LockKeyhole className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="eyebrow-text">Family access requests</p>
              <h2 className="mt-2 font-display text-3xl">Approve one canonical member</h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
                These guests authenticated after using their private reunion relationship. Email is not proof of membership, and cross-family accounts fail closed.
              </p>
            </div>
          </div>
          <div className="mt-6 space-y-3">
            {familyAccessRequests.length ? familyAccessRequests.map((request) => (
              <article className="soft-panel flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between" key={request.request_reference}>
                <div>
                  <p className="font-semibold">{request.applicant_name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{request.status} · {request.requested_at ? new Date(request.requested_at).toLocaleDateString() : "Recently"}</p>
                </div>
                {request.status === "pending" ? (
                  <div className="flex gap-2">
                    <Button disabled={Boolean(familyAccessBusy)} onClick={() => decideFamilyAccess(request, "approved")} size="sm" type="button">Approve</Button>
                    <Button disabled={Boolean(familyAccessBusy)} onClick={() => decideFamilyAccess(request, "declined")} size="sm" type="button" variant="outline">Decline</Button>
                  </div>
                ) : <span className="text-sm font-semibold capitalize text-muted-foreground">{request.status}</span>}
              </article>
            )) : <p className="text-sm text-muted-foreground">No guest family-access requests yet.</p>}
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <article className="archival-card" id="itinerary">
            <div className="flex items-start gap-3">
              <CalendarClock className="mt-1 h-5 w-5 text-primary" />
              <div>
                <p className="eyebrow-text">Deadlines</p>
                <h2 className="mt-2 font-display text-3xl">What is approaching?</h2>
              </div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <StatusCard label="Approaching" value={command.deadlines.approaching} />
              <StatusCard label="Invalid or ambiguous" value={command.deadlines.invalid} />
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              {command.deadlines.next
                ? `Next ${command.deadlines.next.kind.replaceAll("_", " ")}: ${new Date(command.deadlines.next.at).toLocaleString()}`
                : "No valid upcoming RSVP deadline is set."}
            </p>
          </article>

          <article className="archival-card" id="invitations">
            <div className="flex items-start gap-3">
              <Mail className="mt-1 h-5 w-5 text-primary" />
              <div>
                <p className="eyebrow-text">Share + remind safely</p>
                <h2 className="mt-2 font-display text-3xl">Private invitation controls</h2>
              </div>
            </div>
            <p className="mt-4 text-sm leading-7 text-muted-foreground">
              Use the existing fragment-link invitation controls to share privately. Reminder delivery remains disabled unless every privacy-safe preflight gate is available.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button
                asChild
                onClick={() => trackReunionEvent("invitation_share_initiated", {
                  source: "organizer_command_center",
                  status: "open_existing_controls",
                })}
              >
                <Link to={`/reunion/activate/${eventId}`}>Open invitation controls</Link>
              </Button>
              <Button disabled={reminderBusy || command.responses.missing === 0} onClick={checkReminderPreflight} type="button" variant="outline">
                {reminderBusy ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                Check reminder availability
              </Button>
            </div>
            <p className="mt-4 text-xs text-muted-foreground" data-testid="command-reminder-state">
              Reminder state: {command.reminders.code.replaceAll("_", " ")}. No ordinary reminder rotates or invalidates an invitation credential.
            </p>
          </article>
        </section>

        <section className="archival-card" id="planning">
          <p className="eyebrow-text">Planning status</p>
          <h2 className="mt-2 font-display text-3xl">The next few planning areas</h2>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {progressEntries.map(([key, value]) => (
              <StatusCard
                detail={
                  "done" in value
                    ? `${value.done} of ${value.total}`
                    : "plans" in value
                    ? `${value.plans} record${value.plans === 1 ? "" : "s"}`
                    : `${value.assigned || 0} assigned · ${value.pending_invitations || 0} pending`
                }
                key={key}
                label={key.replaceAll("_", " ")}
                value={STATUS_LABELS[value.status] || value.status}
              />
            ))}
          </div>
        </section>

        <section className="archival-card" id="planning-team">
          <p className="eyebrow-text">Planning team</p>
          <h2 className="mt-2 font-display text-3xl">Invite or assign trusted help</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
            An event assignment never elevates permissions. New planning-team invitations explicitly use the existing community organizer role.
          </p>
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              {organizerMembers.map((member) => {
                const assigned = assignedIds.has(member.id);
                return (
                  <div className="soft-panel flex items-center justify-between gap-3" key={member.id}>
                    <div>
                      <p className="font-semibold">{member.full_name}</p>
                      <p className="text-xs text-muted-foreground">{member.role}</p>
                    </div>
                    <Button
                      disabled={planningBusy === member.id}
                      onClick={() => togglePlanner(member.id, assigned)}
                      size="sm"
                      type="button"
                      variant={assigned ? "outline" : "secondary"}
                    >
                      {assigned ? "Remove from team" : "Assign to team"}
                    </Button>
                  </div>
                );
              })}
            </div>
            <form className="soft-panel" onSubmit={invitePlanner}>
              <label htmlFor="planning-team-email">
                <span className="field-label">Invite a new organizer by email</span>
                <Input
                  className="field-input mt-2"
                  id="planning-team-email"
                  onChange={(changeEvent) => setPlanningEmail(changeEvent.target.value)}
                  required
                  type="email"
                  value={planningEmail}
                />
              </label>
              <Button className="mt-4 w-full" disabled={planningBusy === "invite"} type="submit" variant="secondary">
                {planningBusy === "invite" ? "Adding safely…" : "Add planning help"}
              </Button>
              {planningTeam.pending_invitations?.length ? (
                <div className="mt-5 space-y-3 border-t border-border pt-5">
                  <p className="field-label">Pending invitations</p>
                  {planningTeam.pending_invitations.map((invitation) => (
                    <div className="flex items-center justify-between gap-3" key={invitation.id}>
                      <p className="min-w-0 truncate text-sm text-muted-foreground">{invitation.email}</p>
                      <Button
                        disabled={planningBusy === invitation.id}
                        onClick={() => revokePlanningInvitation(invitation.id)}
                        size="sm"
                        type="button"
                        variant="ghost"
                      >
                        Revoke
                      </Button>
                    </div>
                  ))}
                </div>
              ) : null}
            </form>
          </div>
        </section>

        <section className="archival-card">
          <p className="eyebrow-text">Recent planning changes</p>
          <h2 className="mt-2 font-display text-3xl">What changed recently?</h2>
          <div className="mt-5 space-y-3">
            {command.recent_changes.length ? command.recent_changes.map((change, index) => (
              <div className="soft-panel flex items-center gap-3" key={`${change.kind}:${change.at}:${index}`}>
                <CheckCircle2 className="h-4 w-4 text-primary" />
                <p className="text-sm text-muted-foreground">
                  {change.kind.replaceAll("-", " ")} · {change.at ? new Date(change.at).toLocaleString() : "Recently"}
                </p>
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">No meaningful planning changes yet.</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
};

export default OrganizerCommandCenterPage;
