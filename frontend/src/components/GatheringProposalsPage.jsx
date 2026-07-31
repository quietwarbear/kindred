import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CalendarHeart, CheckCircle2, Clock3, MapPin, ShieldCheck, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import { toast } from "@/components/ui/sonner";

const stateCopy = {
  submitted: "Private organizer review",
  published: "Open family interest pulse",
  declined: "Reviewed and closed",
  withdrawn: "Withdrawn",
  converted: "Moved into private planning",
  expired: "Interest pulse closed",
  conflict: "Needs organizer attention",
};

const typeCopy = {
  family_reunion: "Family reunion",
  holiday: "Holiday gathering",
  milestone: "Milestone",
  day_trip: "Day trip",
  virtual: "Virtual gathering",
  other: "Another gathering",
};

const responseCopy = {
  interested: "Interested",
  maybe: "Maybe",
  not_available: "Not available",
};

const operationKey = (kind, reference = "new") => {
  const storageKey = `kindred:gathering-proposal:${kind}:${reference}`;
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const random = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const value = `${kind}:${random}`;
  window.sessionStorage.setItem(storageKey, value);
  return value;
};

const clearOperationKey = (kind, reference = "new") => {
  window.sessionStorage.removeItem(`kindred:gathering-proposal:${kind}:${reference}`);
};

const ProposalCard = ({ proposal, organizer, onAction, onInterest, onBeginConversion }) => {
  const aggregate = proposal.interest?.aggregate || {};
  return (
    <article className="archival-card space-y-5" data-testid={`proposal-card-${proposal.proposal_reference}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="eyebrow-text">{typeCopy[proposal.gathering_type] || typeCopy.other}</p>
          <h2 className="mt-2 font-display text-2xl text-foreground">{proposal.working_title || "Former family proposal"}</h2>
          {organizer ? <p className="mt-2 text-sm text-muted-foreground">Suggested by {proposal.proposer_display_name}</p> : null}
        </div>
        <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{stateCopy[proposal.state] || "Unavailable"}</span>
      </div>

      {(proposal.broad_date_window || proposal.location_suggestion) ? (
        <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-2">
          {proposal.broad_date_window ? <p><Clock3 className="mr-2 inline h-4 w-4" />{proposal.broad_date_window}</p> : null}
          {proposal.location_suggestion ? <p><MapPin className="mr-2 inline h-4 w-4" />{proposal.location_suggestion}</p> : null}
        </div>
      ) : null}

      {organizer && proposal.organizer_note ? (
        <div className="soft-panel"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Private note to organizers</p><p className="mt-2 text-sm text-foreground">{proposal.organizer_note}</p></div>
      ) : null}

      {proposal.state === "published" ? (
        <div className="soft-panel space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(responseCopy).map(([key, label]) => <div key={key}><p className="text-2xl font-semibold text-foreground">{aggregate[key] || 0}</p><p className="text-xs text-muted-foreground">{label}</p></div>)}
            <div><p className="text-2xl font-semibold text-foreground">{aggregate.total || 0}</p><p className="text-xs text-muted-foreground">Responses</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(responseCopy).map(([value, label]) => (
              <Button key={value} onClick={() => onInterest(proposal, value)} type="button" variant={proposal.interest?.my_response === value ? "default" : "outline"}>{label}</Button>
            ))}
          </div>
          {proposal.interest?.my_response !== "none" ? <p className="text-xs text-muted-foreground">Your response: {responseCopy[proposal.interest.my_response]}. Individual family responses stay private.</p> : null}
        </div>
      ) : null}

      {proposal.is_mine && proposal.state === "submitted" ? (
        <Button onClick={() => onAction(proposal, "withdraw")} type="button" variant="outline">Withdraw proposal</Button>
      ) : null}

      {organizer ? (
        <div className="flex flex-wrap gap-2">
          {proposal.state === "submitted" ? <Button onClick={() => onAction(proposal, "publish")} type="button">Publish interest pulse</Button> : null}
          {["submitted", "published"].includes(proposal.state) ? <Button onClick={() => onAction(proposal, "decline")} type="button" variant="outline">Decline</Button> : null}
          {proposal.state === "published" ? <Button onClick={() => onAction(proposal, "close")} type="button" variant="outline">Close pulse</Button> : null}
          {proposal.state === "published" ? <Button onClick={() => onBeginConversion(proposal)} type="button">Preview private draft <ArrowRight className="ml-2 h-4 w-4" /></Button> : null}
        </div>
      ) : null}
    </article>
  );
};

export const GatheringProposalsPage = ({ token, user }) => {
  const organizer = ["host", "organizer"].includes(user?.role);
  const [proposals, setProposals] = useState([]);
  const [eligibleOrganizers, setEligibleOrganizers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ working_title: "", gathering_type: "family_reunion", broad_date_window: "", location_suggestion: "", organizer_note: "" });
  const [conversionFor, setConversionFor] = useState(null);
  const [conversion, setConversion] = useState({ title: "", start_at: "", end_at: "", timezone: "UTC", location: "", gathering_format: "in-person", max_attendees: 50, organizer_reference: "" });
  const [conversionPreview, setConversionPreview] = useState(null);
  const viewed = useRef(new Set());

  const load = useCallback(async () => {
    try {
      const payload = await apiRequest(organizer ? "/gathering-proposals/organizer/review" : "/gathering-proposals", { token });
      setProposals(payload.proposals || []);
      setEligibleOrganizers(payload.eligible_organizers || []);
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || error.response?.data?.detail || "Private gathering proposals could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [organizer, token]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    proposals.filter((item) => item.state === "published").forEach((item) => {
      if (viewed.current.has(item.proposal_reference)) return;
      viewed.current.add(item.proposal_reference);
      trackReunionEvent("gathering_pulse_viewed", { viewer_role: organizer ? "organizer" : "member", proposal_state: "published" });
    });
  }, [organizer, proposals]);

  const submit = async () => {
    setBusy("submit");
    try {
      await apiRequest("/gathering-proposals", { method: "POST", token, data: { ...form, idempotency_key: operationKey("submit") } });
      clearOperationKey("submit");
      setForm({ working_title: "", gathering_type: "family_reunion", broad_date_window: "", location_suggestion: "", organizer_note: "" });
      setShowForm(false);
      trackReunionEvent("gathering_proposal_submitted", { viewer_role: organizer ? "organizer" : "member", proposal_state: "submitted", next_action_category: "review_proposal" });
      await load();
      toast.success("Your private proposal is with the organizers.");
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || "The proposal could not be submitted.");
    } finally { setBusy(""); }
  };

  const action = async (proposal, kind) => {
    setBusy(`${kind}:${proposal.proposal_reference}`);
    try {
      const data = { expected_revision: proposal.revision, idempotency_key: operationKey(kind, proposal.proposal_reference) };
      if (kind === "decline") data.reason = "not_a_fit";
      await apiRequest(`/gathering-proposals/${proposal.proposal_reference}/${kind}`, { method: "POST", token, data });
      clearOperationKey(kind, proposal.proposal_reference);
      await load();
      toast.success("The private proposal status is updated.");
    } catch (error) {
      if (error.response?.status === 409) clearOperationKey(kind, proposal.proposal_reference);
      toast.error(error.response?.data?.detail?.message || "That proposal action could not be completed.");
      await load();
    } finally { setBusy(""); }
  };

  const interest = async (proposal, response) => {
    const kind = "interest";
    setBusy(`${kind}:${proposal.proposal_reference}`);
    try {
      await apiRequest(`/gathering-proposals/${proposal.proposal_reference}/interest`, {
        method: "PUT", token,
        data: { response, expected_revision: proposal.interest?.my_revision || 0, idempotency_key: operationKey(kind, proposal.proposal_reference) },
      });
      clearOperationKey(kind, proposal.proposal_reference);
      trackReunionEvent("gathering_interest_recorded", { viewer_role: "member", proposal_state: "published", response_category: response, next_action_category: "respond_to_pulse" });
      await load();
    } catch (error) {
      if (error.response?.status === 409) clearOperationKey(kind, proposal.proposal_reference);
      toast.error(error.response?.data?.detail?.message || "Your private interest response could not be saved.");
      await load();
    } finally { setBusy(""); }
  };

  const beginConversion = (proposal) => {
    const defaultOrganizer = eligibleOrganizers.find((item) => item.organizer_reference === user?.id) || eligibleOrganizers[0];
    setConversionFor(proposal);
    setConversion({ title: proposal.working_title, start_at: "", end_at: "", timezone: "UTC", location: proposal.location_suggestion || "", gathering_format: proposal.gathering_type === "virtual" ? "online" : "in-person", max_attendees: 50, organizer_reference: defaultOrganizer?.organizer_reference || "" });
    setConversionPreview(null);
  };

  const updateConversion = (key, value) => {
    setConversionPreview(null);
    setConversion((current) => ({ ...current, [key]: value }));
  };

  const previewConversion = async () => {
    setBusy("conversion-preview");
    try {
      const payload = await apiRequest(`/gathering-proposals/${conversionFor.proposal_reference}/conversion-preview`, { method: "POST", token, data: { ...conversion, max_attendees: Number(conversion.max_attendees) } });
      setConversionPreview(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail?.message || "The exact draft preview could not be prepared.");
    } finally { setBusy(""); }
  };

  const convert = async () => {
    setBusy("convert");
    try {
      const payload = await apiRequest(`/gathering-proposals/${conversionFor.proposal_reference}/convert`, {
        method: "POST", token,
        data: { ...conversion, max_attendees: Number(conversion.max_attendees), expected_revision: conversionFor.revision, preview_digest: conversionPreview.preview_digest, idempotency_key: operationKey("convert", conversionFor.proposal_reference) },
      });
      clearOperationKey("convert", conversionFor.proposal_reference);
      trackReunionEvent("gathering_proposal_converted", { viewer_role: "organizer", proposal_state: "converted", next_action_category: "continue_planning" });
      window.location.assign(payload.planning_path);
    } catch (error) {
      if (error.response?.status === 409) setConversionPreview(null);
      toast.error(error.response?.data?.detail?.message || "The private draft could not be created.");
    } finally { setBusy(""); }
  };

  const publishedCount = useMemo(() => proposals.filter((item) => item.state === "published").length, [proposals]);

  if (loading) return <div className="archival-card" aria-busy="true">Loading private gathering proposals…</div>;

  return (
    <div className="space-y-6" data-ph-no-capture="true" data-testid="gathering-proposals-page">
      <section className="archival-card overflow-hidden">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div><p className="eyebrow-text">Private family continuity</p><h1 className="mt-2 font-display text-4xl text-foreground">What should we gather for next?</h1><p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">Suggest a gathering privately. Organizers review it before the family sees an anonymous interest pulse.</p></div>
          <div className="soft-panel flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-primary" /><div><p className="text-sm font-semibold">{publishedCount} open pulse{publishedCount === 1 ? "" : "s"}</p><p className="text-xs text-muted-foreground">No named response roster</p></div></div>
        </div>
        <Button className="mt-5" onClick={() => setShowForm((value) => !value)} type="button">{showForm ? "Close proposal form" : "Suggest a gathering"}</Button>
      </section>

      {showForm ? (
        <section className="archival-card space-y-4" data-testid="proposal-submission-form">
          <div><p className="eyebrow-text">Organizer-only until reviewed</p><h2 className="mt-2 font-display text-2xl">A short private suggestion</h2></div>
          <label className="text-sm font-semibold">Working title<Input className="mt-2" maxLength={120} onChange={(event) => setForm((current) => ({ ...current, working_title: event.target.value }))} value={form.working_title} /></label>
          <label className="text-sm font-semibold">Gathering type<select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" onChange={(event) => setForm((current) => ({ ...current, gathering_type: event.target.value }))} value={form.gathering_type}>{Object.entries(typeCopy).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Broad date window<Input className="mt-2" maxLength={80} onChange={(event) => setForm((current) => ({ ...current, broad_date_window: event.target.value }))} placeholder="For example, early summer" value={form.broad_date_window} /></label><label className="text-sm font-semibold">General location suggestion<Input className="mt-2" maxLength={120} onChange={(event) => setForm((current) => ({ ...current, location_suggestion: event.target.value }))} placeholder="For example, near the family home" value={form.location_suggestion} /></label></div>
          <label className="text-sm font-semibold">Private note to organizers<Textarea className="mt-2" maxLength={1000} onChange={(event) => setForm((current) => ({ ...current, organizer_note: event.target.value }))} rows={4} value={form.organizer_note} /></label>
          <Button disabled={busy === "submit" || !form.working_title.trim()} onClick={submit} type="button">Submit privately</Button>
        </section>
      ) : null}

      {proposals.length ? <div className="space-y-4">{proposals.map((proposal) => <ProposalCard key={proposal.proposal_reference} onAction={action} onBeginConversion={beginConversion} onInterest={interest} organizer={organizer} proposal={proposal} />)}</div> : <section className="archival-card text-center"><CalendarHeart className="mx-auto h-8 w-8 text-primary" /><h2 className="mt-3 font-display text-2xl">No gathering proposals yet</h2><p className="mt-2 text-sm text-muted-foreground">The next family tradition can start with one thoughtful suggestion.</p></section>}

      {organizer && conversionFor ? (
        <section className="archival-card space-y-5" data-testid="proposal-conversion-panel">
          <div><p className="eyebrow-text">Explicit organizer conversion</p><h2 className="mt-2 font-display text-3xl">Preview one private reunion draft</h2><p className="mt-2 text-sm text-muted-foreground">These fields are new organizer selections. No interest identities, notes, invitations, or old identifiers are copied.</p></div>
          <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Draft title<Input className="mt-2" onChange={(event) => updateConversion("title", event.target.value)} value={conversion.title} /></label><label className="text-sm font-semibold">Organizer<select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" onChange={(event) => updateConversion("organizer_reference", event.target.value)} value={conversion.organizer_reference}>{eligibleOrganizers.map((item) => <option key={item.organizer_reference} value={item.organizer_reference}>{item.display_name} · {item.role}</option>)}</select></label><label className="text-sm font-semibold">Starts<Input className="mt-2" onChange={(event) => updateConversion("start_at", event.target.value)} type="datetime-local" value={conversion.start_at} /></label><label className="text-sm font-semibold">Ends<Input className="mt-2" onChange={(event) => updateConversion("end_at", event.target.value)} type="datetime-local" value={conversion.end_at} /></label><label className="text-sm font-semibold">Timezone<Input className="mt-2" onChange={(event) => updateConversion("timezone", event.target.value)} value={conversion.timezone} /></label><label className="text-sm font-semibold">Location<Input className="mt-2" onChange={(event) => updateConversion("location", event.target.value)} value={conversion.location} /></label><label className="text-sm font-semibold">Format<select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" onChange={(event) => updateConversion("gathering_format", event.target.value)} value={conversion.gathering_format}><option value="in-person">In person</option><option value="online">Online</option><option value="hybrid">Hybrid</option></select></label><label className="text-sm font-semibold">Capacity<Input className="mt-2" max={10000} min={1} onChange={(event) => updateConversion("max_attendees", event.target.value)} type="number" value={conversion.max_attendees} /></label></div>
          <div className="flex flex-wrap gap-2"><Button disabled={!conversion.start_at || !conversion.end_at || !conversion.organizer_reference || Boolean(busy)} onClick={previewConversion} type="button" variant="outline">Review exact draft</Button><Button onClick={() => { setConversionFor(null); setConversionPreview(null); }} type="button" variant="ghost">Cancel</Button></div>
          {conversionPreview ? <div className="soft-panel space-y-3" data-testid="proposal-conversion-preview"><div className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-primary" /><p className="font-semibold">Exact private draft</p></div><p className="text-sm text-muted-foreground">{conversionPreview.proposal.new_gathering.title} · {conversionPreview.proposal.new_gathering.start_at} to {conversionPreview.proposal.new_gathering.end_at} · {conversionPreview.proposal.new_gathering.timezone}</p><p className="text-sm text-muted-foreground"><Users className="mr-2 inline h-4 w-4" />Organizer: {conversionPreview.proposal.new_gathering.organizer_display_name}; zero invitations, responses, assignments, memories, or proposer identity.</p><Button disabled={Boolean(busy)} onClick={convert} type="button">Create one private draft <ArrowRight className="ml-2 h-4 w-4" /></Button></div> : null}
        </section>
      ) : null}
    </div>
  );
};
