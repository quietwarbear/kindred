import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookHeart,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  Clock,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/sonner";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { zonedDateTimeToEpoch } from "@/lib/itinerary";

const operationKey = (kind, eventId) => {
  const storageKey = `kindred:recap:${kind}:${eventId}`;
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${kind}:${random}`;
  window.sessionStorage.setItem(storageKey, value);
  return value;
};

const clearOperationKey = (kind, eventId) => {
  window.sessionStorage.removeItem(`kindred:recap:${kind}:${eventId}`);
};

const formatMoment = (value, timezone, options = {}) => {
  if (!value) return "";
  const epoch = zonedDateTimeToEpoch(value, timezone || "UTC");
  if (Number.isNaN(epoch)) return value;
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone || "UTC",
    ...options,
  }).format(new Date(epoch));
};

const lifecycleCopy = {
  not_ready: ["The reunion is still underway", "Kindred will open the recap after the validated final activity ends."],
  ready: ["Ready for organizer review", "Review the private recap and optional message before publishing it to the family."],
  published: ["The family recap is published", "Eligible family-space members can now revisit this reunion."],
  unpublished: ["The recap is unpublished", "Only organizers can preview it until it is published again."],
  legacy_conflict: ["Completion needs organizer attention", "Kindred found ambiguous legacy timing and left the reunion unchanged."],
};

const memoryActionCopy = {
  finish_memory_draft: "Finish your private memory draft",
  contribute_memory: "Contribute a family memory",
  review_memories: "Review the family memories",
  publish_recap: "Open memories",
  start_next_gathering: "Open memories",
  wait_for_completion: "Open memories",
};

export const ReunionRecapPage = ({ session }) => {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const organizer = ["host", "organizer"].includes(session?.user?.role);
  const [recap, setRecap] = useState(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState("");
  const [nextForm, setNextForm] = useState({
    title: "",
    start_at: "",
    end_at: "",
    timezone: "UTC",
    itinerary_selection_references: [],
    contribution_selection_references: [],
    carry_gathering_format: false,
    carry_capacity: false,
  });
  const [nextPreview, setNextPreview] = useState(null);
  const viewedRef = useRef(false);

  const load = useCallback(async () => {
    if (!session?.token || !eventId) return;
    setLoadError("");
    try {
      const payload = await apiRequest(
        organizer ? `/events/${eventId}/recap/organizer` : `/events/${eventId}/recap`,
        { token: session.token }
      );
      setRecap(payload);
      setMessage(payload.message || "");
      setNextForm((current) => ({
        ...current,
        title: current.title || `${payload.reunion?.title || "Family reunion"} — Next gathering`,
        timezone: current.timezone === "UTC" ? (payload.reunion?.timezone || "UTC") : current.timezone,
      }));
    } catch (error) {
      setLoadError(
        error.response?.status === 404
          ? "This private recap is not available to your current family-space account."
          : "The reunion recap could not be opened. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }, [eventId, organizer, session?.token]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!recap || viewedRef.current) return;
    viewedRef.current = true;
    trackReunionEvent("reunion_recap_viewed", {
      viewer_role: organizer ? "organizer" : "member",
      recap_state: recap.state,
    });
  }, [organizer, recap]);

  if (!session?.token) return <Navigate replace to="/login?intent=reunion" />;

  const mutateRecap = async (kind, path, method, data, success) => {
    setBusy(kind);
    try {
      await apiRequest(path, { method, token: session.token, data });
      clearOperationKey(kind, eventId);
      await load();
      toast.success(success);
      return true;
    } catch (error) {
      if (error.response?.status === 409) {
        clearOperationKey(kind, eventId);
        await load();
      }
      toast.error(error.response?.data?.detail?.message || "That recap change could not be saved.");
      return false;
    } finally {
      setBusy("");
    }
  };

  const editMessage = () => mutateRecap(
    "message",
    `/events/${eventId}/recap/message`,
    "PUT",
    {
      message,
      expected_revision: recap.revision,
      idempotency_key: operationKey("message", eventId),
    },
    "The private recap message is saved."
  );

  const transition = (action) => mutateRecap(
    action,
    `/events/${eventId}/recap/${action}`,
    "POST",
    {
      expected_revision: recap.revision,
      idempotency_key: operationKey(action, eventId),
    },
    action === "publish" ? "The recap is published to eligible family members." : "The recap is now unpublished."
  ).then((saved) => {
    if (saved && action === "publish") {
      trackReunionEvent("reunion_recap_published", {
        viewer_role: "organizer",
        recap_state: "published",
      });
    }
  });

  const toggleSelection = (key, value) => {
    setNextPreview(null);
    setNextForm((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value],
    }));
  };

  const updateNext = (key, value) => {
    setNextPreview(null);
    setNextForm((current) => ({ ...current, [key]: value }));
  };

  const previewNext = async () => {
    setBusy("preview-next");
    try {
      const payload = await apiRequest(`/events/${eventId}/next-gathering/preview`, {
        method: "POST",
        token: session.token,
        data: nextForm,
      });
      setNextPreview(payload);
      toast.success("Review every proposed carry-forward field before creating the draft.");
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || "The next-gathering preview could not be prepared.");
    } finally {
      setBusy("");
    }
  };

  const createNext = async () => {
    if (!nextPreview) return;
    const kind = "create-next";
    setBusy(kind);
    try {
      const payload = await apiRequest(`/events/${eventId}/next-gathering`, {
        method: "POST",
        token: session.token,
        data: {
          ...nextForm,
          preview_digest: nextPreview.preview_digest,
          idempotency_key: operationKey(kind, eventId),
        },
      });
      clearOperationKey(kind, eventId);
      trackReunionEvent("next_gathering_started", {
        viewer_role: "organizer",
        recap_state: recap.state,
        next_action_category: "continue_planning",
      });
      trackReunionEvent("next_private_draft_started", {
        source: "reunion_recap",
        viewer_role: "organizer",
      });
      navigate(payload.planning_path);
    } catch (error) {
      if (error.response?.status === 409) setNextPreview(null);
      toast.error(error.response?.data?.detail?.message || "The private reunion draft could not be created.");
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true"><p className="text-sm text-muted-foreground">Preparing the private reunion recap…</p></div>;
  }

  if (loadError || !recap) {
    return (
      <div className="app-canvas flex min-h-screen items-center justify-center px-5">
        <section className="archival-card max-w-lg text-center" role="alert">
          <h1 className="font-display text-3xl">Recap unavailable</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError}</p>
          <Button className="mt-5" onClick={load} type="button" variant="outline"><RefreshCw className="mr-2 h-4 w-4" /> Try again</Button>
        </section>
      </div>
    );
  }

  const [stateTitle, stateCopy] = lifecycleCopy[recap.state] || lifecycleCopy.legacy_conflict;
  const catalog = recap.carry_forward_catalog || { itinerary_templates: [], contribution_categories: [] };
  const proposal = nextPreview?.proposal;
  const canManage = organizer && ["ready", "published", "unpublished"].includes(recap.state);
  const totals = recap.aggregate_participation;

  return (
    <div className="app-canvas min-h-screen" data-ph-no-capture="true" data-testid="reunion-recap">
      <main className="page-section space-y-6 py-5 sm:py-10">
        <header className="space-y-4">
          <Link className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground" to="/home"><ChevronLeft className="mr-1 h-4 w-4" /> Family space</Link>
          <div className="archival-card overflow-hidden">
            <p className="eyebrow-text">Private reunion recap</p>
            <h1 className="mt-2 font-display text-4xl text-foreground">{recap.reunion.title}</h1>
            <p className="mt-3 text-sm text-muted-foreground">
              {formatMoment(recap.reunion.start_at, recap.reunion.timezone, { dateStyle: "long" })}
              {recap.reunion.end_at ? ` — ${formatMoment(recap.reunion.end_at, recap.reunion.timezone, { dateStyle: "long" })}` : ""}
            </p>
            <div className="soft-panel mt-5 flex gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div><p className="font-semibold text-foreground">{stateTitle}</p><p className="mt-1 text-sm text-muted-foreground">{stateCopy}</p></div>
            </div>
          </div>
        </header>

        {recap.message && (
          <section className="archival-card" data-testid="published-recap-message">
            <p className="eyebrow-text">A note from the organizers</p>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-foreground">{recap.message}</p>
          </section>
        )}

        <section className="grid gap-4 md:grid-cols-3">
          <div className="archival-card"><CheckCircle2 className="h-5 w-5 text-primary" /><p className="mt-3 text-2xl font-semibold">{totals.going + totals.some}</p><p className="text-sm text-muted-foreground">Going or joining part</p></div>
          <div className="archival-card"><BookHeart className="h-5 w-5 text-primary" /><p className="mt-3 text-2xl font-semibold">{totals.published_memory_count}</p><p className="text-sm text-muted-foreground">Published family memories</p></div>
          <div className="archival-card"><CalendarDays className="h-5 w-5 text-primary" /><p className="mt-3 text-2xl font-semibold">{totals.claimed_categories}</p><p className="text-sm text-muted-foreground">Contributions completed</p></div>
        </section>

        <section className="archival-card space-y-4">
          <div><p className="eyebrow-text">Your participation</p><h2 className="mt-2 font-display text-2xl">What you shared with the family</h2></div>
          <p className="text-sm text-muted-foreground">Overall response: <span className="font-medium text-foreground">{recap.my_participation.rsvp_status.replaceAll("_", " ")}</span></p>
          <div className="space-y-3">
            {recap.itinerary.map((activity) => (
              <div className="soft-panel" key={`${activity.position}:${activity.title}`}>
                <div className="flex items-start justify-between gap-4"><div><p className="font-semibold text-foreground">{activity.title}</p><p className="mt-1 text-xs text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" />{formatMoment(activity.start_at, activity.timezone, { dateStyle: "medium", timeStyle: "short" })}</p></div><span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">{activity.my_response.replaceAll("_", " ")}</span></div>
              </div>
            ))}
          </div>
        </section>

        <section className="archival-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="eyebrow-text">Keep the stories</p><h2 className="mt-2 font-display text-2xl">Continue to the private memory capsule</h2><p className="mt-2 text-sm text-muted-foreground">Review published, non-withdrawn family memories or add your own.</p></div>
          <Button asChild><Link onClick={() => trackReunionEvent("reunion_memory_continued", { viewer_role: organizer ? "organizer" : "member", recap_state: recap.state, next_action_category: "memory_capsule" })} to={`/reunion/memories/${eventId}`}>{memoryActionCopy[recap.next_action?.code] || "Open memories"} <ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
        </section>

        {organizer && (
          <section className="archival-card space-y-4" data-testid="organizer-recap-controls">
            <div><p className="eyebrow-text">Organizer message</p><h2 className="mt-2 font-display text-2xl">A private note for the family</h2><p className="mt-2 text-sm text-muted-foreground">Up to 2,000 characters. This text stays out of analytics, notifications, URLs, and provider systems.</p></div>
            <Textarea maxLength={2000} onChange={(event) => setMessage(event.target.value)} rows={6} value={message} />
            <div className="flex flex-wrap gap-3">
              <Button disabled={!canManage || busy === "message"} onClick={editMessage} type="button" variant="outline">Save message</Button>
              {recap.state !== "published" ? <Button disabled={!canManage || Boolean(busy)} onClick={() => transition("publish")} type="button">Publish recap</Button> : <Button disabled={Boolean(busy)} onClick={() => transition("unpublish")} type="button" variant="destructive">Unpublish recap</Button>}
            </div>
          </section>
        )}

        {organizer && canManage && (
          <section className="archival-card space-y-5" data-testid="next-gathering-controls">
            <div><p className="eyebrow-text">Plan the next gathering</p><h2 className="mt-2 font-display text-2xl">Create a new private reunion draft</h2><p className="mt-2 text-sm text-muted-foreground">Nothing is created until you review the exact carry-forward preview and confirm.</p></div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm font-semibold">Gathering title<Input className="mt-2" onChange={(event) => updateNext("title", event.target.value)} value={nextForm.title} /></label>
              <label className="text-sm font-semibold">Timezone<Input className="mt-2" onChange={(event) => updateNext("timezone", event.target.value)} placeholder="For example America/New_York" value={nextForm.timezone} /></label>
              <label className="text-sm font-semibold">Starts<Input className="mt-2" onChange={(event) => updateNext("start_at", event.target.value)} type="datetime-local" value={nextForm.start_at} /></label>
              <label className="text-sm font-semibold">Ends<Input className="mt-2" onChange={(event) => updateNext("end_at", event.target.value)} type="datetime-local" value={nextForm.end_at} /></label>
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              <div><p className="text-sm font-semibold">Itinerary templates</p>{catalog.itinerary_templates.map((item) => <label className="mt-3 flex items-center gap-3 text-sm" key={item.selection_reference}><Checkbox checked={nextForm.itinerary_selection_references.includes(item.selection_reference)} onCheckedChange={() => toggleSelection("itinerary_selection_references", item.selection_reference)} />{item.title}</label>)}</div>
              <div><p className="text-sm font-semibold">Contribution categories</p>{catalog.contribution_categories.map((item) => <label className="mt-3 flex items-center gap-3 text-sm" key={item.selection_reference}><Checkbox checked={nextForm.contribution_selection_references.includes(item.selection_reference)} onCheckedChange={() => toggleSelection("contribution_selection_references", item.selection_reference)} />{item.label} <span className="text-xs text-muted-foreground">({item.kind})</span></label>)}</div>
            </div>
            <div className="flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-3"><Checkbox checked={nextForm.carry_gathering_format} onCheckedChange={(checked) => updateNext("carry_gathering_format", Boolean(checked))} /> Carry gathering format</label><label className="flex items-center gap-3"><Checkbox checked={nextForm.carry_capacity} onCheckedChange={(checked) => updateNext("carry_capacity", Boolean(checked))} /> Carry capacity</label></div>
            <Button disabled={Boolean(busy) || !nextForm.start_at || !nextForm.end_at || !nextForm.title.trim()} onClick={previewNext} type="button" variant="outline">Review carry-forward preview</Button>

            {proposal && (
              <div className="soft-panel space-y-4" data-testid="next-gathering-preview">
                <div><p className="font-semibold text-foreground">Exact proposed draft</p><p className="mt-1 text-sm text-muted-foreground">{proposal.new_gathering.title} · {proposal.new_gathering.start_at} to {proposal.new_gathering.end_at} · {proposal.new_gathering.timezone}</p></div>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground"><li>Private organizer draft with {proposal.new_gathering.invitation_count} invitations and {proposal.new_gathering.rsvp_response_count} responses</li><li>Format: {proposal.carried_forward.gathering_format}; capacity: {proposal.carried_forward.max_attendees}</li><li>Zero assignments or inherited identifiers</li></ul>
                {proposal.carried_forward.itinerary_templates.length ? <div><p className="text-sm font-semibold text-foreground">Carried itinerary fields</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{proposal.carried_forward.itinerary_templates.map((item) => <li key={item.selection_reference}>{item.title} · attendance {item.attendance_requested ? "requested" : "not requested"}</li>)}</ul></div> : <p className="text-sm text-muted-foreground">No itinerary fields will be carried.</p>}
                {proposal.carried_forward.contribution_categories.length ? <div><p className="text-sm font-semibold text-foreground">Carried contribution fields</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{proposal.carried_forward.contribution_categories.map((item) => <li key={item.selection_reference}>{item.label} · {item.kind}</li>)}</ul></div> : <p className="text-sm text-muted-foreground">No contribution fields will be carried.</p>}
                <Button disabled={Boolean(busy)} onClick={createNext} type="button">Create private draft <ArrowRight className="ml-2 h-4 w-4" /></Button>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
};
