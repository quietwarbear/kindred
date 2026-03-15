import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, ClipboardList, HandHelping, Link2, MailPlus, Pencil, Plane, Soup, Trash2, UsersRound, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime, shortCurrency } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

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
};

const initialChecklistForm = { category: "experience", title: "" };
const initialAgendaForm = { time_label: "", title: "", notes: "" };
const initialTravelForm = {
  title: "",
  travel_type: "hotel",
  details: "",
  coordinator_name: "",
  amount_estimate: 0,
  payment_status: "pending",
  seats_available: 0,
};
const initialInviteForm = {
  member_ids: [],
  guest_emails: "",
  note: "",
};
const initialRoleForm = {
  role_name: "",
  assignees: "",
};

export const GatheringsPage = ({ token, user }) => {
  const [templates, setTemplates] = useState([]);
  const [subyards, setSubyards] = useState([]);
  const [members, setMembers] = useState([]);
  const [events, setEvents] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [travelPlans, setTravelPlans] = useState([]);
  const [activeEventId, setActiveEventId] = useState("");
  const [eventForm, setEventForm] = useState(initialEventForm);
  const [checklistForm, setChecklistForm] = useState(initialChecklistForm);
  const [agendaForm, setAgendaForm] = useState(initialAgendaForm);
  const [volunteerTitle, setVolunteerTitle] = useState("");
  const [volunteerCount, setVolunteerCount] = useState(1);
  const [potluckItem, setPotluckItem] = useState("");
  const [travelForm, setTravelForm] = useState(initialTravelForm);
  const [inviteForm, setInviteForm] = useState(initialInviteForm);
  const [roleForm, setRoleForm] = useState(initialRoleForm);
  const [zoomLinkDraft, setZoomLinkDraft] = useState("");
  const [rsvpStatus, setRsvpStatus] = useState("going");
  const [guestCount, setGuestCount] = useState(0);
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
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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
      await loadData();
      toast.success("Gathering created with a smart checklist.");
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

  const handleAgendaAdd = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/agenda`, { method: "POST", token, data: agendaForm });
      mergeEvent(payload);
      setAgendaForm(initialAgendaForm);
      toast.success("Agenda item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add agenda item.");
    }
  };

  const handleChecklistAdd = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/checklist-items`, { method: "POST", token, data: checklistForm });
      mergeEvent(payload);
      setChecklistForm(initialChecklistForm);
      toast.success("Checklist item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add checklist item.");
    }
  };

  const handleChecklistToggle = async (itemId) => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/checklist-toggle`, { method: "POST", token, data: { item_id: itemId } });
      mergeEvent(payload);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update checklist item.");
    }
  };

  const handleVolunteerSlot = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/volunteer-slots`, {
        method: "POST",
        token,
        data: { title: volunteerTitle, needed_count: Number(volunteerCount) },
      });
      mergeEvent(payload);
      setVolunteerTitle("");
      setVolunteerCount(1);
      toast.success("Volunteer slot added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add volunteer slot.");
    }
  };

  const handleVolunteerSignup = async (slotId) => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/volunteer-signup`, { method: "POST", token, data: { slot_id: slotId } });
      mergeEvent(payload);
      toast.success("Volunteer role claimed.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to claim volunteer role.");
    }
  };

  const handlePotluckAdd = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/potluck-items`, { method: "POST", token, data: { item_name: potluckItem } });
      mergeEvent(payload);
      setPotluckItem("");
      toast.success("Potluck item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add potluck item.");
    }
  };

  const handlePotluckClaim = async (itemId) => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/potluck-claim`, { method: "POST", token, data: { item_id: itemId } });
      mergeEvent(payload);
      toast.success("Potluck item claimed.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to claim potluck item.");
    }
  };

  const handleRsvp = async () => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/rsvp`, { method: "POST", token, data: { status: rsvpStatus, guests: Number(guestCount) } });
      mergeEvent(payload);
      toast.success("RSVP updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update RSVP.");
    }
  };

  const handleCreateTravelPlan = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      await apiRequest("/travel-plans", {
        method: "POST",
        token,
        data: {
          ...travelForm,
          event_id: activeEvent.id,
          amount_estimate: Number(travelForm.amount_estimate) || 0,
          seats_available: Number(travelForm.seats_available) || 0,
        },
      });
      setTravelForm(initialTravelForm);
      toast.success("Travel coordination item added.");
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add travel coordination.");
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

  const handleToggleInviteMember = (memberId) => {
    setInviteForm((current) => ({
      ...current,
      member_ids: current.member_ids.includes(memberId)
        ? current.member_ids.filter((item) => item !== memberId)
        : [...current.member_ids, memberId],
    }));
  };

  const handleCreateInvites = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/invites`, {
        method: "POST",
        token,
        data: {
          member_ids: inviteForm.member_ids,
          guest_emails: inviteForm.guest_emails.split(",").map((item) => item.trim()).filter(Boolean),
          note: inviteForm.note,
        },
      });
      mergeEvent(payload);
      setInviteForm(initialInviteForm);
      toast.success("Event invites created.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create invites.");
    }
  };

  const handleAssignRoles = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/role-assignments`, {
        method: "POST",
        token,
        data: {
          role_name: roleForm.role_name,
          assignees: roleForm.assignees.split(",").map((item) => item.trim()).filter(Boolean),
        },
      });
      mergeEvent(payload);
      setRoleForm(initialRoleForm);
      toast.success("Event role assignments updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to assign event roles.");
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

  const handleTravelAssign = async (planId) => {
    try {
      await apiRequest(`/travel-plans/${planId}/assign-self`, { method: "POST", token });
      toast.success("Travel assignment updated.");
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to join that travel plan.");
    }
  };

  const selectedTravelPlans = useMemo(
    () => travelPlans.filter((item) => item.event_id === activeEventId),
    [activeEventId, travelPlans]
  );

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

      {reminders.length ? (
        <section className="archival-card" data-testid="gatherings-reminders-card">
          <p className="eyebrow-text">Smart invite reminders</p>
          <h3 className="mt-2 font-display text-3xl text-foreground">Recurring gatherings that still need RSVP attention</h3>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {reminders.map((reminder) => (
              <div className="soft-panel" data-testid={`gatherings-reminder-${reminder.id}`} key={reminder.id}>
                <p className="text-base font-semibold text-foreground">{reminder.title}</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{reminder.description}</p>
                {canCreate ? (
                  <Button className="mt-4 rounded-full" data-testid={`gatherings-reminder-send-${reminder.event_id}`} disabled={sendingReminderEventId === reminder.event_id} onClick={() => handleSendReminders(reminder.event_id)} type="button" variant="secondary">
                    {sendingReminderEventId === reminder.event_id ? "Preparing..." : "Prepare reminder batch"}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {canCreate ? (
        <section className="archival-card" data-testid="gatherings-create-section">
          <div className="flex items-center gap-3">
            <CalendarDays className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Create Gathering Flow</h3>
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
              <Input className="field-input" data-testid="gatherings-title-input" onChange={(e) => setEventForm((current) => ({ ...current, title: e.target.value }))} required value={eventForm.title} />
            </label>
            <label>
              <span className="field-label">Date + time</span>
              <Input className="field-input" data-testid="gatherings-start-input" onChange={(e) => setEventForm((current) => ({ ...current, start_at: e.target.value }))} required type="datetime-local" value={eventForm.start_at} />
            </label>
            <label>
              <span className="field-label">Location</span>
              <Input className="field-input" data-testid="gatherings-location-input" onChange={(e) => setEventForm((current) => ({ ...current, location: e.target.value }))} required value={eventForm.location} />
            </label>
            <label>
              <span className="field-label">Map link</span>
              <Input className="field-input" data-testid="gatherings-map-input" onChange={(e) => setEventForm((current) => ({ ...current, map_url: e.target.value }))} value={eventForm.map_url} />
            </label>
            <label>
              <span className="field-label">Format</span>
              <select className="field-input w-full" data-testid="gatherings-format-select" onChange={(e) => setEventForm((current) => ({ ...current, gathering_format: e.target.value }))} value={eventForm.gathering_format}>
                <option value="in-person">In-person</option>
                <option value="online">Online</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            <label>
              <span className="field-label">Max attendees</span>
              <Input className="field-input" data-testid="gatherings-max-attendees-input" min={1} onChange={(e) => setEventForm((current) => ({ ...current, max_attendees: e.target.value }))} type="number" value={eventForm.max_attendees} />
            </label>
            <label>
              <span className="field-label">Subyard</span>
              <select className="field-input w-full" data-testid="gatherings-subyard-select" onChange={(e) => setEventForm((current) => ({ ...current, subyard_id: e.target.value }))} value={eventForm.subyard_id}>
                <option value="">Whole courtyard</option>
                {subyards.map((subyard) => (
                  <option key={subyard.id} value={subyard.id}>{subyard.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Recurring</span>
              <select className="field-input w-full" data-testid="gatherings-recurrence-select" onChange={(e) => setEventForm((current) => ({ ...current, recurrence_frequency: e.target.value }))} value={eventForm.recurrence_frequency}>
                <option value="none">One-time</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="yearly">Yearly</option>
              </select>
            </label>
            <label>
              <span className="field-label">Event roles</span>
              <Input className="field-input" data-testid="gatherings-roles-input" onChange={(e) => setEventForm((current) => ({ ...current, assigned_roles: e.target.value }))} value={eventForm.assigned_roles} />
            </label>
            <label>
              <span className="field-label">Suggested contribution</span>
              <Input className="field-input" data-testid="gatherings-suggested-contribution-input" min={0} onChange={(e) => setEventForm((current) => ({ ...current, suggested_contribution: e.target.value }))} type="number" value={eventForm.suggested_contribution} />
            </label>
            <label>
              <span className="field-label">Special focus</span>
              <Input className="field-input" data-testid="gatherings-special-focus-input" onChange={(e) => setEventForm((current) => ({ ...current, special_focus: e.target.value }))} value={eventForm.special_focus} />
            </label>
            {eventForm.gathering_format !== "in-person" ? (
              <label>
                <span className="field-label">Zoom link for invites</span>
                <Input className="field-input" data-testid="gatherings-zoom-link-input" onChange={(e) => setEventForm((current) => ({ ...current, zoom_link: e.target.value }))} placeholder="https://zoom.us/j/..." value={eventForm.zoom_link} />
              </label>
            ) : null}
            <label className="xl:col-span-2">
              <span className="field-label">Description</span>
              <Textarea className="field-textarea" data-testid="gatherings-description-input" onChange={(e) => setEventForm((current) => ({ ...current, description: e.target.value }))} required value={eventForm.description} />
            </label>
            <label className="xl:col-span-2">
              <span className="field-label">Travel coordination notes</span>
              <Textarea className="field-textarea" data-testid="gatherings-travel-notes-input" onChange={(e) => setEventForm((current) => ({ ...current, travel_coordination_notes: e.target.value }))} value={eventForm.travel_coordination_notes} />
            </label>
            <div className="xl:col-span-2">
              <Button className="rounded-full py-6 text-base" data-testid="gatherings-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating..." : "Create gathering"}
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <article className="archival-card" data-testid="gatherings-list-card">
          <h3 className="font-display text-3xl text-foreground">Planned gatherings</h3>
          <div className="mt-6 space-y-4">
            {events.length ? (
              events.map((eventItem) => (
                <button
                  className={`w-full rounded-[24px] border p-5 text-left transition duration-300 ${eventItem.id === activeEventId ? "border-primary bg-primary/5" : "border-border bg-background/70 hover:border-primary/30"}`}
                  data-testid={`gathering-card-${eventItem.id}`}
                  key={eventItem.id}
                  onClick={() => setActiveEventId(eventItem.id)}
                  type="button"
                >
                  <p className="text-lg font-semibold text-foreground">{eventItem.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(eventItem.start_at)} · {eventItem.location}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{eventItem.gathering_format} · {eventItem.subyard_name || "whole courtyard"}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.16em] text-primary" data-testid={`gathering-card-recurrence-${eventItem.id}`}>
                    {eventItem.recurrence_frequency === "none" ? "one-time" : `${eventItem.recurrence_frequency} recurring`}
                  </p>
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
                {activeEvent.gathering_format !== "in-person" ? (
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
                    {activeEvent.zoom_link ? <p className="mt-3 text-sm text-muted-foreground" data-testid="gatherings-meeting-link-display">{activeEvent.zoom_link}</p> : null}
                  </div>
                ) : null}
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <div className="soft-panel" data-testid="gatherings-checklist-panel">
                  <div className="flex items-center gap-3">
                    <ClipboardList className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Auto-generated planning checklist</p>
                  </div>
                  <div className="mt-4 space-y-3">
                    {activeEvent.planning_checklist.map((item) => (
                      <button
                        className={`w-full rounded-2xl border px-4 py-3 text-left ${item.completed ? "border-primary bg-primary/5" : "border-border bg-background/70"}`}
                        data-testid={`gatherings-checklist-item-${item.id}`}
                        key={item.id}
                        onClick={() => handleChecklistToggle(item.id)}
                        type="button"
                      >
                        <p className="text-sm font-semibold text-foreground">{item.title}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">{item.category} · {item.completed ? "done" : "open"}</p>
                      </button>
                    ))}
                  </div>
                  {canCreate ? (
                    <form className="mt-4 space-y-3" onSubmit={handleChecklistAdd}>
                      <select className="field-input w-full" data-testid="gatherings-checklist-category-select" onChange={(e) => setChecklistForm((current) => ({ ...current, category: e.target.value }))} value={checklistForm.category}>
                        <option value="administrative">Administrative</option>
                        <option value="experience">Experience</option>
                        <option value="technology">Technology</option>
                        <option value="promotion">Promotion</option>
                        <option value="post-event">Post-event</option>
                      </select>
                      <Input className="field-input" data-testid="gatherings-checklist-title-input" onChange={(e) => setChecklistForm((current) => ({ ...current, title: e.target.value }))} placeholder="Add custom checklist item" required value={checklistForm.title} />
                      <Button className="w-full rounded-full" data-testid="gatherings-checklist-submit-button" type="submit" variant="secondary">
                        Add checklist item
                      </Button>
                    </form>
                  ) : null}
                </div>

                <div className="soft-panel" data-testid="gatherings-rsvp-panel">
                  <div className="flex items-center gap-3">
                    <UsersRound className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">RSVP + attendee tracking</p>
                  </div>
                  <div className="mt-4 space-y-3">
                    <select className="field-input w-full" data-testid="gatherings-rsvp-status-select" onChange={(e) => setRsvpStatus(e.target.value)} value={rsvpStatus}>
                      <option value="going">Going</option>
                      <option value="maybe">Maybe</option>
                      <option value="not-going">Not going</option>
                    </select>
                    <Input className="field-input" data-testid="gatherings-rsvp-guests-input" min={0} onChange={(e) => setGuestCount(e.target.value)} type="number" value={guestCount} />
                    <Button className="w-full rounded-full" data-testid="gatherings-rsvp-submit-button" onClick={handleRsvp} type="button">
                      Save RSVP
                    </Button>
                    <div className="space-y-2">
                      {activeEvent.rsvp_records.map((record) => (
                        <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground" data-testid={`gatherings-rsvp-record-${record.user_id}`} key={record.user_id}>
                          {record.user_name}: {record.status} {record.guests ? `(+${record.guests})` : ""}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="soft-panel" data-testid="gatherings-invites-panel">
                  <div className="flex items-center gap-3">
                    <MailPlus className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Invite people to this gathering</p>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {members.map((member) => (
                      <button
                        className={`rounded-full px-3 py-2 text-xs font-semibold transition ${inviteForm.member_ids.includes(member.id) ? "bg-primary text-primary-foreground" : "border border-border bg-background/80 text-foreground"}`}
                        data-testid={`gatherings-invite-member-${member.id}`}
                        key={member.id}
                        onClick={() => handleToggleInviteMember(member.id)}
                        type="button"
                      >
                        {member.full_name}
                      </button>
                    ))}
                  </div>
                  <form className="mt-4 space-y-3" onSubmit={handleCreateInvites}>
                    <Input className="field-input" data-testid="gatherings-invite-guests-input" onChange={(e) => setInviteForm((current) => ({ ...current, guest_emails: e.target.value }))} placeholder="guest1@example.com, guest2@example.com" value={inviteForm.guest_emails} />
                    <Textarea className="field-textarea" data-testid="gatherings-invite-note-input" onChange={(e) => setInviteForm((current) => ({ ...current, note: e.target.value }))} placeholder="Optional note for invitees" value={inviteForm.note} />
                    <Button className="w-full rounded-full" data-testid="gatherings-invite-submit-button" type="submit" variant="secondary">
                      Create gathering invites
                    </Button>
                  </form>
                  <div className="mt-4 space-y-3">
                    {activeEvent.event_invites?.map((invite) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-event-invite-${invite.id}`} key={invite.id}>
                        <p className="text-sm font-semibold text-foreground">{invite.invitee_name} · {invite.email}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">{invite.invite_source} · {invite.delivery_status}</p>
                        {invite.note ? <p className="mt-2 text-sm text-muted-foreground">{invite.note}</p> : null}
                        {invite.zoom_link ? <p className="mt-2 text-sm text-primary" data-testid={`gatherings-event-invite-zoom-${invite.id}`}>Zoom: {invite.zoom_link}</p> : null}
                        <p className="mt-2 text-sm leading-7 text-muted-foreground" data-testid={`gatherings-event-invite-message-${invite.id}`}>{invite.share_message}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="soft-panel" data-testid="gatherings-role-assignments-panel">
                  <p className="text-lg font-semibold text-foreground">Assign event roles</p>
                  <div className="mt-4 space-y-3">
                    {activeEvent.event_role_assignments?.map((assignment) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-role-assignment-${assignment.id}`} key={assignment.id}>
                        <p className="text-sm font-semibold text-foreground">{assignment.role_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{assignment.assignees?.join(", ") || "No one assigned yet."}</p>
                      </div>
                    ))}
                  </div>
                  <form className="mt-4 space-y-3" onSubmit={handleAssignRoles}>
                    <Input className="field-input" data-testid="gatherings-role-name-input" onChange={(e) => setRoleForm((current) => ({ ...current, role_name: e.target.value }))} placeholder="Zoom host, greeter, prayer lead" required value={roleForm.role_name} />
                    <Input className="field-input" data-testid="gatherings-role-assignees-input" onChange={(e) => setRoleForm((current) => ({ ...current, assignees: e.target.value }))} placeholder="Name or email, multiple separated by commas" required value={roleForm.assignees} />
                    <Button className="w-full rounded-full" data-testid="gatherings-role-submit-button" type="submit" variant="secondary">
                      Save role assignment
                    </Button>
                  </form>
                </div>

                <div className="soft-panel" data-testid="gatherings-agenda-panel">
                  <p className="text-lg font-semibold text-foreground">Agenda builder</p>
                  <div className="mt-4 space-y-3">
                    {activeEvent.agenda.map((item) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-agenda-item-${item.id}`} key={item.id}>
                        <p className="text-sm font-semibold text-foreground">{item.time_label} · {item.title}</p>
                        {item.notes ? <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p> : null}
                      </div>
                    ))}
                  </div>
                  {canCreate ? (
                    <form className="mt-4 space-y-3" onSubmit={handleAgendaAdd}>
                      <Input className="field-input" data-testid="gatherings-agenda-time-input" onChange={(e) => setAgendaForm((current) => ({ ...current, time_label: e.target.value }))} placeholder="2:00 PM" required value={agendaForm.time_label} />
                      <Input className="field-input" data-testid="gatherings-agenda-title-input" onChange={(e) => setAgendaForm((current) => ({ ...current, title: e.target.value }))} placeholder="Opening circle" required value={agendaForm.title} />
                      <Textarea className="field-textarea" data-testid="gatherings-agenda-notes-input" onChange={(e) => setAgendaForm((current) => ({ ...current, notes: e.target.value }))} placeholder="Optional notes" value={agendaForm.notes} />
                      <Button className="w-full rounded-full" data-testid="gatherings-agenda-submit-button" type="submit" variant="secondary">
                        Add agenda item
                      </Button>
                    </form>
                  ) : null}
                </div>

                <div className="soft-panel" data-testid="gatherings-volunteer-panel">
                  <div className="flex items-center gap-3">
                    <HandHelping className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Volunteer sign-ups</p>
                  </div>
                  <div className="mt-4 space-y-3">
                    {activeEvent.volunteer_slots.map((slot) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-volunteer-slot-${slot.id}`} key={slot.id}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-foreground">{slot.title}</p>
                            <p className="mt-1 text-xs text-muted-foreground">{slot.assigned_members.length}/{slot.needed_count} filled</p>
                          </div>
                          <Button className="rounded-full" data-testid={`gatherings-volunteer-join-${slot.id}`} onClick={() => handleVolunteerSignup(slot.id)} size="sm" type="button" variant="secondary">
                            Join
                          </Button>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">{slot.assigned_members.join(", ") || "No one assigned yet."}</p>
                      </div>
                    ))}
                  </div>
                  {canCreate ? (
                    <form className="mt-4 space-y-3" onSubmit={handleVolunteerSlot}>
                      <Input className="field-input" data-testid="gatherings-volunteer-title-input" onChange={(e) => setVolunteerTitle(e.target.value)} placeholder="Hospitality team" required value={volunteerTitle} />
                      <Input className="field-input" data-testid="gatherings-volunteer-count-input" min={1} onChange={(e) => setVolunteerCount(e.target.value)} type="number" value={volunteerCount} />
                      <Button className="w-full rounded-full" data-testid="gatherings-volunteer-submit-button" type="submit" variant="secondary">
                        Add volunteer slot
                      </Button>
                    </form>
                  ) : null}
                </div>

                <div className="soft-panel" data-testid="gatherings-potluck-panel">
                  <div className="flex items-center gap-3">
                    <Soup className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Shared table planning</p>
                  </div>
                  <div className="mt-4 space-y-3">
                    {activeEvent.potluck_items.map((item) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`gatherings-potluck-item-${item.id}`} key={item.id}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-foreground">{item.item_name}</p>
                            <p className="mt-1 text-xs text-muted-foreground">{item.assigned_to || "Unclaimed"}</p>
                          </div>
                          {!item.assigned_to ? (
                            <Button className="rounded-full" data-testid={`gatherings-potluck-claim-${item.id}`} onClick={() => handlePotluckClaim(item.id)} size="sm" type="button" variant="secondary">
                              Claim
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                  {canCreate ? (
                    <form className="mt-4 space-y-3" onSubmit={handlePotluckAdd}>
                      <Input className="field-input" data-testid="gatherings-potluck-item-input" onChange={(e) => setPotluckItem(e.target.value)} placeholder="Mac and cheese tray" required value={potluckItem} />
                      <Button className="w-full rounded-full" data-testid="gatherings-potluck-submit-button" type="submit" variant="secondary">
                        Add potluck item
                      </Button>
                    </form>
                  ) : null}
                </div>

                <div className="soft-panel xl:col-span-2" data-testid="gatherings-travel-panel">
                  <div className="flex items-center gap-3">
                    <Plane className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Travel coordination module</p>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{activeEvent.travel_coordination_notes || "Use this section for hotel blocks, flights, carpools, shuttles, and shared travel payment coordination."}</p>
                  <div className="mt-4 grid gap-4 lg:grid-cols-2">
                    {selectedTravelPlans.map((plan) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-4" data-testid={`gatherings-travel-plan-${plan.id}`} key={plan.id}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-foreground">{plan.title}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">{plan.travel_type}</p>
                          </div>
                          <Button className="rounded-full" data-testid={`gatherings-travel-join-${plan.id}`} onClick={() => handleTravelAssign(plan.id)} size="sm" type="button" variant="secondary">
                            Join
                          </Button>
                        </div>
                        <p className="mt-3 text-sm leading-7 text-muted-foreground">{plan.details}</p>
                        <div className="mt-3 flex flex-wrap gap-3 text-sm text-muted-foreground">
                          <span>{shortCurrency(plan.amount_estimate)}</span>
                          <span>{plan.payment_status}</span>
                          <span>{plan.assigned_members.length} assigned</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  {canCreate ? (
                    <form className="mt-4 grid gap-4 xl:grid-cols-2" onSubmit={handleCreateTravelPlan}>
                      <label>
                        <span className="field-label">Travel item title</span>
                        <Input className="field-input" data-testid="gatherings-travel-title-input" onChange={(e) => setTravelForm((current) => ({ ...current, title: e.target.value }))} required value={travelForm.title} />
                      </label>
                      <label>
                        <span className="field-label">Type</span>
                        <select className="field-input w-full" data-testid="gatherings-travel-type-select" onChange={(e) => setTravelForm((current) => ({ ...current, travel_type: e.target.value }))} value={travelForm.travel_type}>
                          <option value="hotel">Hotel</option>
                          <option value="flight">Flight</option>
                          <option value="carpool">Carpool</option>
                          <option value="shuttle">Shuttle</option>
                        </select>
                      </label>
                      <label>
                        <span className="field-label">Coordinator</span>
                        <Input className="field-input" data-testid="gatherings-travel-coordinator-input" onChange={(e) => setTravelForm((current) => ({ ...current, coordinator_name: e.target.value }))} value={travelForm.coordinator_name} />
                      </label>
                      <label>
                        <span className="field-label">Estimated amount</span>
                        <Input className="field-input" data-testid="gatherings-travel-amount-input" min={0} onChange={(e) => setTravelForm((current) => ({ ...current, amount_estimate: e.target.value }))} type="number" value={travelForm.amount_estimate} />
                      </label>
                      <label>
                        <span className="field-label">Seats available</span>
                        <Input className="field-input" data-testid="gatherings-travel-seats-input" min={0} onChange={(e) => setTravelForm((current) => ({ ...current, seats_available: e.target.value }))} type="number" value={travelForm.seats_available} />
                      </label>
                      <label>
                        <span className="field-label">Payment status</span>
                        <select className="field-input w-full" data-testid="gatherings-travel-payment-status-select" onChange={(e) => setTravelForm((current) => ({ ...current, payment_status: e.target.value }))} value={travelForm.payment_status}>
                          <option value="pending">Pending</option>
                          <option value="partially-funded">Partially funded</option>
                          <option value="funded">Funded</option>
                        </select>
                      </label>
                      <label className="xl:col-span-2">
                        <span className="field-label">Details</span>
                        <Textarea className="field-textarea" data-testid="gatherings-travel-details-input" onChange={(e) => setTravelForm((current) => ({ ...current, details: e.target.value }))} required value={travelForm.details} />
                      </label>
                      <div className="xl:col-span-2">
                        <Button className="w-full rounded-full" data-testid="gatherings-travel-submit-button" type="submit" variant="secondary">
                          Add travel coordination item
                        </Button>
                      </div>
                    </form>
                  ) : null}
                </div>
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