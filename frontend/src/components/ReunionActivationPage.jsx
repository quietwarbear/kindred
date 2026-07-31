import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Eye,
  LockKeyhole,
  MapPin,
  MessageCircleHeart,
  Users,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { GatheringChecklist } from "@/components/gatherings/GatheringChecklist";
import { GatheringInvites } from "@/components/gatherings/GatheringInvites";
import { GatheringPotluck } from "@/components/gatherings/GatheringPotluck";
import { GatheringVolunteers } from "@/components/gatherings/GatheringVolunteers";
import { ReunionInvitePreview } from "@/components/ReunionStartPage";
import { ReunionItinerary } from "@/components/reunion/ReunionItinerary";
import { ReunionOperations } from "@/components/reunion/ReunionOperations";
import { apiRequest, formatDateTime } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { clearReunionDraft } from "@/lib/reunionDraft";
import { toast } from "@/components/ui/sonner";

const activationKey = (eventId) => `kindred-reunion-activated:${eventId}`;

export const ReunionActivationPage = ({ session }) => {
  const { eventId } = useParams();
  const [event, setEvent] = useState(null);
  const [members, setMembers] = useState([]);
  const [operations, setOperations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showPreview, setShowPreview] = useState(false);
  const [memory, setMemory] = useState("");
  const [savingMemory, setSavingMemory] = useState(false);

  const load = useCallback(async () => {
    if (!session?.token || !eventId) return;
    try {
      const [eventPayload, memberPayload, operationsPayload] = await Promise.all([
        apiRequest(`/events/${eventId}`, { token: session.token }),
        apiRequest("/community/members", { token: session.token }),
        apiRequest(`/events/${eventId}/operations`, { token: session.token }),
      ]);
      setEvent(eventPayload);
      setMembers(memberPayload.members || []);
      setOperations(operationsPayload);
      clearReunionDraft();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load this reunion.");
    } finally {
      setLoading(false);
    }
  }, [eventId, session?.token]);

  useEffect(() => {
    load();
  }, [load]);

  const updateEvent = async (payload) => {
    setEvent(payload);
    try {
      const operationsPayload = await apiRequest(`/events/${eventId}/operations`, { token: session.token });
      setOperations(operationsPayload);
    } catch {
      // The itinerary mutation succeeded; a stale operations summary is non-blocking.
    }
  };

  const activation = useMemo(() => {
    if (!event) {
      return {
        invited: 0,
        evidencedInvites: 0,
        accepted: 0,
        meaningful: false,
        activated: false,
        days: 0,
      };
    }
    const invites = event.event_invites || [];
    const evidencedInvites = invites.filter(
      (invite) =>
        (invite.rsvp_status || "pending") !== "pending"
        || Boolean(invite.opened_at)
        || Boolean(invite.delivery_verified_at)
    ).length;
    const accepted = invites.filter((invite) => ["going", "some"].includes(invite.rsvp_status)).length;
    const publicRsvp = (event.rsvp_records || []).some((record) => String(record.user_id || "").startsWith("invite:"));
    const guestVolunteer = (event.volunteer_slots || []).some((slot) =>
      (slot.assigned_members || []).some((name) => name && name !== session?.user?.full_name)
    );
    const guestPotluck = (event.potluck_items || []).some(
      (item) => item.assigned_to && item.assigned_to !== session?.user?.full_name
    );
    const days = Math.max(0, Math.floor((Date.now() - new Date(event.created_at).getTime()) / 86_400_000) || 0);
    const meaningful = publicRsvp || guestVolunteer || guestPotluck;
    return {
      invited: invites.length,
      evidencedInvites,
      accepted,
      meaningful,
      activated: days <= 7 && evidencedInvites >= 3 && accepted >= 2 && meaningful,
      days,
    };
  }, [event, session?.user?.full_name]);

  useEffect(() => {
    if (!event?.id || !activation.activated) return;
    const key = activationKey(event.id);
    if (window.sessionStorage.getItem(key)) return;
    trackReunionEvent("community_activated", {
      invite_count: activation.invited,
      verified_invite_count: activation.evidencedInvites,
      accepted_count: activation.accepted,
      days_since_created: activation.days,
    });
    window.sessionStorage.setItem(key, "1");
  }, [activation, event?.id]);

  if (!session?.token) {
    return <Navigate replace to="/login?intent=reunion" />;
  }

  const saveMemory = async (submitEvent) => {
    submitEvent.preventDefault();
    if (!memory.trim() || !event) return;
    setSavingMemory(true);
    try {
      await apiRequest("/memories", {
        method: "POST",
        token: session.token,
        data: {
          title: "A story for the reunion",
          description: memory.trim(),
          memory_type: "story",
          category: "oral-history",
          event_id: event.id,
          tags: ["reunion"],
        },
      });
      setMemory("");
      trackReunionEvent("memory_prompt_completed", { source: "reunion_activation" });
      toast.success("Your first reunion story is preserved.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to preserve this story.");
    } finally {
      setSavingMemory(false);
    }
  };

  const preview = () => {
    setShowPreview(true);
    trackReunionEvent("reunion_preview_viewed", { source: "reunion_activation" });
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Opening your reunion plan…</p>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-6">
        <div className="archival-card max-w-lg text-center">
          <h1 className="font-display text-3xl">This reunion could not be opened.</h1>
          <Link className="mt-5 inline-flex text-sm font-semibold text-primary hover:underline" to="/reunion/start">Return to reunion planning</Link>
        </div>
      </div>
    );
  }

  const draft = {
    gathering_name: event.title,
    approximate_date: String(event.start_at || "").slice(0, 10),
    end_date: String(event.end_at || "").slice(0, 10),
    timezone: event.timezone || "UTC",
    multiday_enabled: Boolean(event.end_at && String(event.end_at).slice(0, 10) !== String(event.start_at).slice(0, 10)),
    organizer_name: event.created_by_name || session.user?.full_name || "your family organizer",
    location: event.location,
  };

  return (
    <div className="app-canvas min-h-screen py-6 sm:py-10" data-ph-no-capture="true" data-testid="reunion-activation-page">
      <main className="page-section space-y-6">
        <header className="archival-card overflow-hidden p-0">
          <div className="grid lg:grid-cols-[1.1fr_0.9fr]">
            <div className="p-6 sm:p-8">
              <p className="eyebrow-text">Your reunion is ready to coordinate</p>
              <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl" data-testid="reunion-activation-title">{event.title}</h1>
              <div className="mt-5 flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-2"><CalendarDays className="h-4 w-4 text-primary" /> {formatDateTime(event.start_at)}</span>
                {event.end_at ? <span>through {formatDateTime(event.end_at)}</span> : null}
                <span>{event.timezone || "UTC"}</span>
                <span className="inline-flex items-center gap-2"><MapPin className="h-4 w-4 text-primary" /> {event.location || "Location to be confirmed"}</span>
              </div>
              <div className="mt-6 flex flex-wrap gap-3">
                <Button data-testid="reunion-activation-preview-button" onClick={preview} type="button" variant="outline">
                  <Eye className="mr-2 h-4 w-4" /> Preview invitee view
                </Button>
                <Button asChild>
                  <Link to={`/reunion/command/${event.id}`}>Open organizer command center <ArrowRight className="ml-2 h-4 w-4" /></Link>
                </Button>
              </div>
            </div>
            <div className="bg-stone-950 p-6 text-white sm:p-8">
              <p className="eyebrow-text text-orange-200">Seven-day activation</p>
              <div className="mt-5 space-y-3">
                {[
                  [true, "Host created a gathering"],
                  [
                    activation.evidencedInvites >= 3,
                    `${activation.evidencedInvites}/3 invitations opened, answered, or delivery-verified`,
                  ],
                  [activation.accepted >= 2, `${activation.accepted}/2 people accepted`],
                  [activation.meaningful, "A guest completed an RSVP, potluck, volunteer, or memory action"],
                ].map(([done, label]) => (
                  <p className={`flex items-start gap-2 text-sm ${done ? "text-emerald-200" : "text-stone-300"}`} key={label}>
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> {label}
                  </p>
                ))}
              </div>
              <p className="mt-6 text-xs leading-5 text-stone-300">
                No payment is required to create, preview, or coordinate this gathering.
              </p>
            </div>
          </div>
        </header>

        {showPreview ? <ReunionInvitePreview activities={event.agenda || []} draft={draft} /> : null}

        <ReunionItinerary
          canCreate
          event={event}
          onUpdate={updateEvent}
          token={session.token}
        />

        <ReunionOperations event={event} operations={operations} />

        <section className="grid gap-6 xl:grid-cols-2">
          <GatheringChecklist canCreate event={event} onUpdate={updateEvent} token={session.token} />
          <GatheringInvites event={event} members={members} onUpdate={updateEvent} token={session.token} />
          <GatheringPotluck canCreate event={event} onUpdate={updateEvent} token={session.token} />
          <GatheringVolunteers canCreate event={event} onUpdate={updateEvent} token={session.token} />
        </section>

        <section className="archival-card" data-testid="reunion-memory-prompt">
          <div className="flex items-start gap-3">
            <MessageCircleHeart className="mt-1 h-5 w-5 text-primary" />
            <div className="flex-1">
              <p className="eyebrow-text">Keep the stories</p>
              <h2 className="mt-2 font-display text-3xl">What family story should every younger cousin know?</h2>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                Start with a short note. Photos, voice recordings, and fuller profiles can come later.
              </p>
              <form className="mt-5 space-y-3" onSubmit={saveMemory}>
                <label className="sr-only" htmlFor="reunion-memory-answer">Family story</label>
                <Textarea
                  className="field-textarea"
                  data-testid="reunion-memory-answer"
                  id="reunion-memory-answer"
                  maxLength={2000}
                  onChange={(changeEvent) => setMemory(changeEvent.target.value)}
                  placeholder="A story, saying, recipe, journey, or tradition…"
                  required
                  value={memory}
                />
                <Button data-testid="reunion-memory-save-button" disabled={savingMemory || !memory.trim()} type="submit">
                  {savingMemory ? "Preserving…" : "Preserve this story"}
                </Button>
              </form>
            </div>
          </div>
        </section>

        <section className="archival-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <LockKeyhole className="mt-1 h-5 w-5 text-primary" />
            <div>
              <p className="font-semibold">Family-space setup can wait.</p>
              <p className="mt-1 text-sm text-muted-foreground">Name the permanent space, enrich profiles, choose modules, and create subyards after the first shared action.</p>
            </div>
          </div>
          <Button asChild variant="outline">
            <Link to="/home"><Users className="mr-2 h-4 w-4" /> Continue to Kindred</Link>
          </Button>
        </section>
      </main>
    </div>
  );
};

export default ReunionActivationPage;
