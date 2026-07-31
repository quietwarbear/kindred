import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, CalendarDays, Check, Link2, Pencil, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

import { GatheringAgenda } from "@/components/gatherings/GatheringAgenda";
import { GatheringChecklist } from "@/components/gatherings/GatheringChecklist";
import { GatheringInvites } from "@/components/gatherings/GatheringInvites";
import { GatheringPotluck } from "@/components/gatherings/GatheringPotluck";
import { GatheringRoles } from "@/components/gatherings/GatheringRoles";
import { GatheringRsvp } from "@/components/gatherings/GatheringRsvp";
import { GatheringTravel } from "@/components/gatherings/GatheringTravel";
import { GatheringVolunteers } from "@/components/gatherings/GatheringVolunteers";

const initialEventForm = {
  title: "",
  description: "",
  start_at: "",
  location: "",
  map_url: "",
  event_template: "reunion",
  special_focus: "",
  gathering_format: "in-person",
  max_attendees: 150,
  subyard_id: "",
  assigned_roles: "organizer, historian, treasurer",
  suggested_contribution: 0,
  travel_coordination_notes: "",
  recurrence_frequency: "none",
  zoom_link: "",
  hidden_from_member_ids: [],
  agenda: [],
  volunteer_slots: [],
  potluck_items: [],
};

export const GatheringsPage = ({ token, user }) => {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState([]);
  const [subyards, setSubyards] = useState([]);
  const [members, setMembers] = useState([]);
  const [events, setEvents] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [travelPlans, setTravelPlans] = useState([]);
  const [activeEventId, setActiveEventId] = useState("");
  const [eventForm, setEventForm] = useState(initialEventForm);
  const [surpriseOn, setSurpriseOn] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [planning, setPlanning] = useState(false);
  const [planPreview, setPlanPreview] = useState(null);

  const planWithAI = async () => {
    if (!aiPrompt.trim()) { toast.error("Tell the steward what you're planning."); return; }
    setPlanning(true);
    try {
      const res = await apiRequest("/gatherings/ai-plan", { method: "POST", token, data: { prompt: aiPrompt.trim() } });
      const plan = res.plan || {};
      setEventForm((c) => ({
        ...c,
        title: plan.title || c.title,
        description: plan.description || c.description,
        special_focus: plan.special_focus || c.special_focus,
        agenda: plan.agenda || [],
        volunteer_slots: plan.volunteer_slots || [],
        potluck_items: plan.potluck_items || [],
      }));
      setPlanPreview(plan);
      toast.success("The steward drafted a plan — review and create.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Couldn't draft a plan.");
    } finally {
      setPlanning(false);
    }
  };
  const [zoomLinkDraft, setZoomLinkDraft] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sendingReminderEventId, setSendingReminderEventId] = useState("");
  const [editingEvent, setEditingEvent] = useState(null);
  const [deletingEventId, setDeletingEventId] = useState("");

  const canCreate = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);
  const activeEvent = useMemo(() => events.find((item) => item.id === activeEventId) || null, [activeEventId, events]);

  const mergeEvent = (nextEvent) => {
    setEvents((current) => current.map((item) => (item.id === nextEvent.id ? nextEvent : item)));
  };

  const loadData = useCallback(async () => {
    try {
      if (!canCreate) {
        const eventPayload = await apiRequest("/events", { token });
        setEvents(eventPayload || []);
        setActiveEventId((current) => current || eventPayload?.[0]?.id || "");
        return;
      }
      const [templatePayload, subyardPayload, memberPayload, eventPayload, reminderPayload, travelPayload] = await Promise.all([
        apiRequest("/gatherings/templates", { token }),
        apiRequest("/subyards", { token }),
        apiRequest("/community/members", { token }),
        apiRequest("/events", { token }),
        apiRequest("/gatherings/reminders", { token }),
        apiRequest("/travel-plans", { token }),
      ]);
      setTemplates(templatePayload.templates || []);
      setSubyards(subyardPayload.subyards || []);
      setMembers(memberPayload.members || []);
      setEvents(eventPayload || []);
      setReminders(reminderPayload.reminders || []);
      setTravelPlans(travelPayload.travel_plans || []);
      setActiveEventId((current) => current || eventPayload?.[0]?.id || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load gathering planner.");
    }
  }, [canCreate, token]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    setZoomLinkDraft(activeEvent?.zoom_link || "");
  }, [activeEvent?.id, activeEvent?.zoom_link]);

  const handleCreateEvent = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/events", {
        method: "POST",
        token,
        data: {
          ...eventForm,
          start_at: new Date(eventForm.start_at).toISOString(),
          assigned_roles: eventForm.assigned_roles.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean),
          max_attendees: Number(eventForm.max_attendees) || null,
          suggested_contribution: Number(eventForm.suggested_contribution) || 0,
        },
      });
      setActiveEventId(payload.id);
      setEventForm(initialEventForm);
      setSurpriseOn(false);
      setPlanPreview(null);
      setAiPrompt("");
      await loadData();
      toast.success(eventForm.hidden_from_member_ids.length ? "Surprise gathering created — hidden from the guest(s) of honor." : "Gathering created with a smart checklist.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create gathering.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEditEvent = () => {
    if (!activeEvent) return;
    setEditingEvent({
      title: activeEvent.title,
      description: activeEvent.description || "",
      start_at: activeEvent.start_at ? new Date(activeEvent.start_at).toISOString().slice(0, 16) : "",
      location: activeEvent.location || "",
      gathering_format: activeEvent.gathering_format || "in-person",
      max_attendees: activeEvent.max_attendees || 50,
    });
  };

  const handleSaveEditEvent = async () => {
    if (!activeEvent || !editingEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}`, {
        method: "PUT",
        token,
        data: {
          ...editingEvent,
          start_at: editingEvent.start_at ? new Date(editingEvent.start_at).toISOString() : "",
          max_attendees: Number(editingEvent.max_attendees) || null,
        },
      });
      mergeEvent(payload);
      setEditingEvent(null);
      toast.success("Gathering updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update gathering.");
    }
  };

  const revealEvent = async () => {
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/reveal`, { method: "POST", token });
      mergeEvent(payload);
      toast.success("Revealed — the gathering is now visible to everyone.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to reveal the gathering.");
    }
  };

  const handleDeleteEvent = async (eventId) => {
    try {
      await apiRequest(`/events/${eventId}`, { method: "DELETE", token });
      setDeletingEventId("");
      if (activeEventId === eventId) setActiveEventId("");
      await loadData();
      toast.success("Gathering deleted.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete gathering.");
    }
  };

  const handleSaveMeetingLink = async () => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/meeting-link`, {
        method: "POST",
        token,
        data: { zoom_link: zoomLinkDraft },
      });
      mergeEvent(payload);
      toast.success("Meeting link saved.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to save meeting link.");
    }
  };

  const handleSendReminders = async (eventId) => {
    setSendingReminderEventId(eventId);
    try {
      const payload = await apiRequest(`/gatherings/${eventId}/send-reminders`, { method: "POST", token });
      toast.success(`${payload.sent_count} reminder(s) prepared. Delivery: ${payload.delivery_status}.`);
      await loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to prepare reminders.");
    } finally {
      setSendingReminderEventId("");
    }
  };

  const selectedTravelPlans = useMemo(
    () => travelPlans.filter((item) => item.event_id === activeEventId),
    [activeEventId, travelPlans]
  );

  if (!canCreate) {
    return (
      <div className="space-y-6" data-testid="attendee-gatherings-list">
        <section className="archival-card">
          <p className="eyebrow-text">Your gatherings</p>
          <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl">
            Reunion plans, responses, and ways to help.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">
            Open a reunion to see its published itinerary, your own response, safe attendance totals, and your commitments.
          </p>
        </section>
        <section className="grid gap-4 md:grid-cols-2">
          {events.map((eventItem) => (
            <article className="archival-card" key={eventItem.id}>
              <p className="eyebrow-text">{eventItem.event_template === "reunion" ? "Reunion" : "Gathering"}</p>
              <h3 className="mt-2 font-display text-3xl">{eventItem.title}</h3>
              <p className="mt-3 text-sm text-muted-foreground">{formatDateTime(eventItem.start_at)} · {eventItem.location || "Location to be announced"}</p>
              <Button
                className="mt-5"
                onClick={() => navigate(eventItem.event_template === "reunion" ? `/reunion/hub/${eventItem.id}` : `/gatherings/${eventItem.id}`)}
                type="button"
              >
                {eventItem.event_template === "reunion" ? "Open my reunion hub" : "Open gathering"}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </article>
          ))}
          {!events.length ? (
            <div className="soft-panel">
              <p className="text-sm text-muted-foreground">No visible gatherings are scheduled yet.</p>
            </div>
          ) : null}
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Gatherings Engine</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="gatherings-page-title">
          Smart event planning with templates, checklists, roles, travel, and community memory built in.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="gatherings-page-copy">
          This is the hero feature: choose a template, assign event roles, auto-generate the planning checklist, and coordinate the logistics people usually have to manage across too many tools.
        </p>
      </section>

      {reminders.length > 0 && (
        <section className="archival-card" data-testid="gatherings-reminders-card">
          <p className="eyebrow-text">Smart invite reminders</p>
          <h3 className="mt-2 font-display text-3xl text-foreground">Recurring gatherings that still need RSVP attention</h3>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {reminders.map((reminder) => (
              <div className="soft-panel" data-testid={`gatherings-reminder-${reminder.id}`} key={reminder.id}>
                <p className="text-base font-semibold text-foreground">{reminder.title}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{reminder.description}</p>
                {canCreate && (
                  <Button className="mt-4 rounded-full" data-testid={`gatherings-reminder-send-${reminder.event_id}`} disabled={sendingReminderEventId === reminder.event_id} onClick={() => handleSendReminders(reminder.event_id)} type="button" variant="secondary">
                    {sendingReminderEventId === reminder.event_id ? "Preparing..." : "Prepare reminder batch"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {canCreate && (
        <section className="archival-card" data-testid="gatherings-create-section">
          <div className="flex items-center gap-3">
            <CalendarDays className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Create Gathering Flow</h3>
          </div>

          <div className="mt-4 rounded-2xl border border-primary/30 bg-primary/5 p-4" data-testid="gatherings-ai-plan">
            <p className="eyebrow-text">✨ Plan with the Ubuntu Steward</p>
            <p className="mt-1 text-sm text-muted-foreground">Describe it in a sentence — the steward drafts the whole gathering (agenda, volunteers, potluck), and it all saves when you create.</p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <Input className="field-input flex-1" data-testid="gatherings-ai-prompt" onChange={(e) => setAiPrompt(e.target.value)} placeholder="e.g. Our August family reunion in Oakland, about 40 people" value={aiPrompt} />
              <Button className="rounded-full" data-testid="gatherings-ai-plan-btn" disabled={planning} onClick={planWithAI} type="button">
                {planning ? "Planning…" : "Draft it"}
              </Button>
            </div>
            {planPreview && (
              <div className="mt-3 grid gap-3 text-xs sm:grid-cols-3" data-testid="gatherings-ai-preview">
                <div className="soft-panel">
                  <p className="font-semibold text-foreground">Agenda ({planPreview.agenda?.length || 0})</p>
                  {(planPreview.agenda || []).slice(0, 5).map((a, i) => <p className="mt-1 text-muted-foreground" key={i}>{a.time_label ? `${a.time_label}: ` : ""}{a.title}</p>)}
                </div>
                <div className="soft-panel">
                  <p className="font-semibold text-foreground">Volunteers ({planPreview.volunteer_slots?.length || 0})</p>
                  {(planPreview.volunteer_slots || []).slice(0, 5).map((s, i) => <p className="mt-1 text-muted-foreground" key={i}>{s.title} ×{s.needed_count}</p>)}
                </div>
                <div className="soft-panel">
                  <p className="font-semibold text-foreground">Potluck ({planPreview.potluck_items?.length || 0})</p>
                  {(planPreview.potluck_items || []).slice(0, 6).map((p, i) => <p className="mt-1 text-muted-foreground" key={i}>{p}</p>)}
                </div>
                <p className="text-muted-foreground sm:col-span-3">Title, description, and focus are filled in below — these items save with the gathering when you create it.</p>
              </div>
            )}
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-5">
            {templates.map((template) => (
              <button
                className={`soft-panel text-left ${eventForm.event_template === template.id ? "border-primary bg-primary/5" : ""}`}
                data-testid={`gathering-template-${template.id}`}
                key={template.id}
                onClick={() => setEventForm((current) => ({ ...current, event_template: template.id, assigned_roles: template.roles.join(", ") }))}
                type="button"
              >
                <p className="text-base font-semibold text-foreground">{template.label}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{template.description}</p>
              </button>
            ))}
          </div>
          <form className="mt-6 grid gap-4 xl:grid-cols-2" onSubmit={handleCreateEvent}>
            <label>
              <span className="field-label">Gathering name</span>
              <Input className="field-input" data-testid="gatherings-title-input" onChange={(e) => setEventForm((c) => ({ ...c, title: e.target.value }))} required value={eventForm.title} />
            </label>
            <label>
              <span className="field-label">Date + time</span>
              <Input className="field-input" data-testid="gatherings-start-input" onChange={(e) => setEventForm((c) => ({ ...c, start_at: e.target.value }))} required type="datetime-local" value={eventForm.start_at} />
            </label>
            <label>
              <span className="field-label">Location</span>
              <Input className="field-input" data-testid="gatherings-location-input" onChange={(e) => setEventForm((c) => ({ ...c, location: e.target.value }))} required value={eventForm.location} />
            </label>
            <label>
              <span className="field-label">Map link</span>
              <Input className="field-input" data-testid="gatherings-map-input" onChange={(e) => setEventForm((c) => ({ ...c, map_url: e.target.value }))} value={eventForm.map_url} />
            </label>
            <label>
              <span className="field-label">Format</span>
              <select className="field-input w-full" data-testid="gatherings-format-select" onChange={(e) => setEventForm((c) => ({ ...c, gathering_format: e.target.value }))} value={eventForm.gathering_format}>
                <option value="in-person">In-person</option>
                <option value="online">Online</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            <label>
              <span className="field-label">Max attendees</span>
              <Input className="field-input" data-testid="gatherings-max-attendees-input" min={1} onChange={(e) => setEventForm((c) => ({ ...c, max_attendees: e.target.value }))} type="number" value={eventForm.max_attendees} />
            </label>
            <label>
              <span className="field-label">Subyard</span>
              <select className="field-input w-full" data-testid="gatherings-subyard-select" onChange={(e) => setEventForm((c) => ({ ...c, subyard_id: e.target.value }))} value={eventForm.subyard_id}>
                <option value="">Whole courtyard</option>
                {subyards.map((subyard) => (
                  <option key={subyard.id} value={subyard.id}>{subyard.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Recurring</span>
              <select className="field-input w-full" data-testid="gatherings-recurrence-select" onChange={(e) => setEventForm((c) => ({ ...c, recurrence_frequency: e.target.value }))} value={eventForm.recurrence_frequency}>
                <option value="none">One-time</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="yearly">Yearly</option>
              </select>
            </label>
            <label>
              <span className="field-label">Event roles</span>
              <Input className="field-input" data-testid="gatherings-roles-input" onChange={(e) => setEventForm((c) => ({ ...c, assigned_roles: e.target.value }))} value={eventForm.assigned_roles} />
            </label>
            <label>
              <span className="field-label">Suggested contribution</span>
              <Input className="field-input" data-testid="gatherings-suggested-contribution-input" min={0} onChange={(e) => setEventForm((c) => ({ ...c, suggested_contribution: e.target.value }))} type="number" value={eventForm.suggested_contribution} />
            </label>
            <label>
              <span className="field-label">Special focus</span>
              <Input className="field-input" data-testid="gatherings-special-focus-input" onChange={(e) => setEventForm((c) => ({ ...c, special_focus: e.target.value }))} value={eventForm.special_focus} />
            </label>
            {eventForm.gathering_format !== "in-person" && (
              <label>
                <span className="field-label">Zoom link for invites</span>
                <Input className="field-input" data-testid="gatherings-zoom-link-input" onChange={(e) => setEventForm((c) => ({ ...c, zoom_link: e.target.value }))} placeholder="https://zoom.us/j/..." value={eventForm.zoom_link} />
              </label>
            )}
            <div className="xl:col-span-2 rounded-2xl border border-border/60 bg-muted/30 p-4" data-testid="gatherings-surprise-block">
              <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-foreground">
                <input
                  type="checkbox"
                  data-testid="gatherings-surprise-toggle"
                  checked={surpriseOn}
                  onChange={(e) => {
                    setSurpriseOn(e.target.checked);
                    if (!e.target.checked) setEventForm((c) => ({ ...c, hidden_from_member_ids: [] }));
                  }}
                />
                🎉 Surprise gathering — hide it from the guest(s) of honor
              </label>
              {surpriseOn && (
                <div className="mt-3" data-testid="gatherings-surprise-members">
                  <p className="text-xs text-muted-foreground">Pick who it should stay hidden from. They won't see it anywhere — gatherings list, dashboard, the weekly digest email, or notifications — until you're ready.</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {members.map((m) => {
                      const picked = eventForm.hidden_from_member_ids.includes(m.id);
                      return (
                        <button
                          key={m.id}
                          type="button"
                          data-testid={`gatherings-surprise-member-${m.id}`}
                          onClick={() => setEventForm((c) => ({
                            ...c,
                            hidden_from_member_ids: picked
                              ? c.hidden_from_member_ids.filter((id) => id !== m.id)
                              : [...c.hidden_from_member_ids, m.id],
                          }))}
                          className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${picked ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
                        >
                          {m.full_name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
            <label className="xl:col-span-2">
              <span className="field-label">Description</span>
              <Textarea className="field-textarea" data-testid="gatherings-description-input" onChange={(e) => setEventForm((c) => ({ ...c, description: e.target.value }))} required value={eventForm.description} />
            </label>
            <label className="xl:col-span-2">
              <span className="field-label">Travel coordination notes</span>
              <Textarea className="field-textarea" data-testid="gatherings-travel-notes-input" onChange={(e) => setEventForm((c) => ({ ...c, travel_coordination_notes: e.target.value }))} value={eventForm.travel_coordination_notes} />
            </label>
            <div className="xl:col-span-2">
              <Button className="rounded-full py-6 text-base" data-testid="gatherings-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating..." : "Create gathering"}
              </Button>
            </div>
          </form>
        </section>
      )}

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <article className="archival-card" data-testid="gatherings-list-card">
          <h3 className="font-display text-3xl text-foreground">Planned gatherings</h3>
          <div className="mt-6 space-y-4">
            {events.length > 0 ? (
              events.map((eventItem) => (
                <button
                  className={`w-full rounded-[24px] border p-5 text-left transition duration-300 ${eventItem.id === activeEventId ? "border-primary bg-primary/5" : "border-border bg-background/70 hover:border-primary/30"}`}
                  data-testid={`gathering-card-${eventItem.id}`}
                  key={eventItem.id}
                  onClick={() => navigate(`/gatherings/${eventItem.id}`)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="text-lg font-semibold text-foreground">{eventItem.title}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(eventItem.start_at)} · {eventItem.location}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{eventItem.gathering_format} · {eventItem.subyard_name || "whole courtyard"}</p>
                      <p className="mt-2 text-xs uppercase tracking-[0.16em] text-primary" data-testid={`gathering-card-recurrence-${eventItem.id}`}>
                        {eventItem.recurrence_frequency === "none" ? "one-time" : `${eventItem.recurrence_frequency} recurring`}
                      </p>
                    </div>
                    <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                  </div>
                </button>
              ))
            ) : (
              <div className="soft-panel" data-testid="gatherings-empty-state">
                <p className="text-sm text-muted-foreground">No gatherings yet. Choose a template above and create the first one.</p>
              </div>
            )}
          </div>
        </article>

        <article className="archival-card" data-testid="gatherings-detail-card">
          {activeEvent ? (
            <div className="space-y-6">
              <div>
                <div className="flex items-center justify-between">
                  <p className="eyebrow-text">Active gathering</p>
                  {canCreate && !editingEvent && (
                    <div className="flex gap-2">
                      <Button className="rounded-full h-8" data-testid="event-edit-btn" onClick={startEditEvent} size="sm" variant="outline">
                        <Pencil className="mr-1 h-3 w-3" /> Edit
                      </Button>
                      <Button className="rounded-full h-8" data-testid="event-delete-btn" onClick={() => setDeletingEventId(activeEvent.id)} size="sm" variant="outline">
                        <Trash2 className="mr-1 h-3 w-3" /> Delete
                      </Button>
                    </div>
                  )}
                </div>
                {deletingEventId === activeEvent.id && (
                  <div className="mt-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
                    <p className="text-sm font-semibold text-destructive">Delete this gathering?</p>
                    <p className="text-sm text-muted-foreground">This action cannot be undone.</p>
                    <div className="mt-3 flex gap-2">
                      <Button className="rounded-full" data-testid="event-delete-confirm" onClick={() => handleDeleteEvent(activeEvent.id)} size="sm" variant="destructive">Confirm delete</Button>
                      <Button className="rounded-full" data-testid="event-delete-cancel" onClick={() => setDeletingEventId("")} size="sm" variant="outline">Cancel</Button>
                    </div>
                  </div>
                )}
                {editingEvent ? (
                  <div className="mt-3 space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4" data-testid="event-inline-edit-form">
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Title</span>
                      <Input className="field-input mt-1" data-testid="event-edit-title" onChange={(e) => setEditingEvent((c) => ({ ...c, title: e.target.value }))} value={editingEvent.title} />
                    </label>
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Description</span>
                      <Textarea className="field-textarea mt-1" data-testid="event-edit-description" onChange={(e) => setEditingEvent((c) => ({ ...c, description: e.target.value }))} rows={3} value={editingEvent.description} />
                    </label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block">
                        <span className="text-xs font-semibold text-muted-foreground">Date & Time</span>
                        <Input className="field-input mt-1" data-testid="event-edit-start" onChange={(e) => setEditingEvent((c) => ({ ...c, start_at: e.target.value }))} type="datetime-local" value={editingEvent.start_at} />
                      </label>
                      <label className="block">
                        <span className="text-xs font-semibold text-muted-foreground">Location</span>
                        <Input className="field-input mt-1" data-testid="event-edit-location" onChange={(e) => setEditingEvent((c) => ({ ...c, location: e.target.value }))} value={editingEvent.location} />
                      </label>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block">
                        <span className="text-xs font-semibold text-muted-foreground">Format</span>
                        <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="event-edit-format" onChange={(e) => setEditingEvent((c) => ({ ...c, gathering_format: e.target.value }))} value={editingEvent.gathering_format}>
                          <option value="in-person">In-person</option>
                          <option value="online">Online</option>
                          <option value="hybrid">Hybrid</option>
                        </select>
                      </label>
                      <label className="block">
                        <span className="text-xs font-semibold text-muted-foreground">Capacity</span>
                        <Input className="field-input mt-1" data-testid="event-edit-capacity" min={1} onChange={(e) => setEditingEvent((c) => ({ ...c, max_attendees: e.target.value }))} type="number" value={editingEvent.max_attendees} />
                      </label>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <Button className="rounded-full" data-testid="event-edit-save" onClick={handleSaveEditEvent} size="sm"><Check className="mr-1 h-3 w-3" /> Save</Button>
                      <Button className="rounded-full" data-testid="event-edit-cancel" onClick={() => setEditingEvent(null)} size="sm" variant="outline"><X className="mr-1 h-3 w-3" /> Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <h3 className="mt-2 font-display text-3xl text-foreground" data-testid="gatherings-active-title">{activeEvent.title}</h3>
                    <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(activeEvent.start_at)} · {activeEvent.location}</p>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">{activeEvent.description}</p>
                    {activeEvent.hidden_from_user_ids?.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl bg-amber-50 px-4 py-3 dark:bg-amber-900/20" data-testid="gatherings-surprise-banner">
                        <span className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                          🎉 Surprise — hidden from {activeEvent.hidden_from_user_ids.length} {activeEvent.hidden_from_user_ids.length === 1 ? "person" : "people"}
                        </span>
                        <Button className="rounded-full h-8" data-testid="gatherings-reveal-btn" onClick={revealEvent} size="sm">
                          Reveal to everyone
                        </Button>
                      </div>
                    )}
                  </>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  {activeEvent.assigned_roles.map((role) => (
                    <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" data-testid={`gatherings-active-role-${role.replace(/\s+/g, "-")}`} key={role}>
                      {role}
                    </span>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
                  <span data-testid="gatherings-active-format">Format: {activeEvent.gathering_format}</span>
                  <span data-testid="gatherings-active-max-attendees">Capacity: {activeEvent.max_attendees || "Flexible"}</span>
                  <span data-testid="gatherings-active-suggested-contribution">Suggested contribution: {shortCurrency(activeEvent.suggested_contribution || 0)}</span>
                  <span data-testid="gatherings-active-recurrence">Recurs: {activeEvent.recurrence_frequency === "none" ? "One-time" : activeEvent.recurrence_frequency}</span>
                </div>
                {activeEvent.gathering_format !== "in-person" && (
                  <div className="soft-panel mt-5" data-testid="gatherings-meeting-link-panel">
                    <div className="flex items-center gap-3">
                      <Link2 className="h-4 w-4 text-primary" />
                      <p className="text-sm font-semibold text-foreground">Meeting link for hybrid/online invites</p>
                    </div>
                    <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                      <Input className="field-input" data-testid="gatherings-meeting-link-input" onChange={(e) => setZoomLinkDraft(e.target.value)} placeholder="https://zoom.us/j/..." value={zoomLinkDraft} />
                      <Button className="rounded-full" data-testid="gatherings-meeting-link-save-button" onClick={handleSaveMeetingLink} type="button">
                        Save Zoom link
                      </Button>
                    </div>
                    {activeEvent.zoom_link && <p className="mt-3 text-sm text-muted-foreground" data-testid="gatherings-meeting-link-display">{activeEvent.zoom_link}</p>}
                  </div>
                )}
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <GatheringChecklist canCreate={canCreate} event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringRsvp event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringInvites event={activeEvent} members={members} onUpdate={mergeEvent} token={token} />
                <GatheringRoles event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringAgenda canCreate={canCreate} event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringVolunteers canCreate={canCreate} event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringPotluck canCreate={canCreate} event={activeEvent} onUpdate={mergeEvent} token={token} />
                <GatheringTravel canCreate={canCreate} event={activeEvent} onReload={loadData} token={token} travelPlans={selectedTravelPlans} />
              </div>
            </div>
          ) : (
            <div className="soft-panel" data-testid="gatherings-detail-empty-state">
              <p className="text-sm text-muted-foreground">Select a gathering to manage roles, checklist, agenda, volunteers, potluck, and travel coordination.</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
};
