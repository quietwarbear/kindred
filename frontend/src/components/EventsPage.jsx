import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, HandHelping, MapPinned, Soup, UsersRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, formatDateTime } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const initialEventForm = {
  title: "",
  description: "",
  start_at: "",
  location: "",
  map_url: "",
  event_template: "general",
  special_focus: "",
};

const initialAgendaForm = { time_label: "", title: "", notes: "" };

export const EventsPage = ({ token, user }) => {
  const [events, setEvents] = useState([]);
  const [activeEventId, setActiveEventId] = useState("");
  const [eventForm, setEventForm] = useState(initialEventForm);
  const [agendaForm, setAgendaForm] = useState(initialAgendaForm);
  const [volunteerTitle, setVolunteerTitle] = useState("");
  const [volunteerCount, setVolunteerCount] = useState(1);
  const [potluckItem, setPotluckItem] = useState("");
  const [rsvpStatus, setRsvpStatus] = useState("going");
  const [guestCount, setGuestCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canCreate = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);
  const activeEvent = useMemo(() => events.find((event) => event.id === activeEventId) || null, [activeEventId, events]);

  const mergeEvent = (updatedEvent) => {
    setEvents((current) => current.map((event) => (event.id === updatedEvent.id ? updatedEvent : event)));
  };

  const loadEvents = useCallback(async () => {
    try {
      const payload = await apiRequest("/events", { token });
      setEvents(payload || []);
      setActiveEventId((current) => current || payload?.[0]?.id || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to load events.");
    }
  }, [token]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const handleCreateEvent = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = await apiRequest("/events", {
        method: "POST",
        data: {
          ...eventForm,
          start_at: new Date(eventForm.start_at).toISOString(),
        },
        token,
      });
      setEvents((current) => [...current, payload].sort((a, b) => new Date(a.start_at) - new Date(b.start_at)));
      setActiveEventId(payload.id);
      setEventForm(initialEventForm);
      toast.success("Event created.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to create event.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRsvp = async () => {
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/rsvp`, {
        method: "POST",
        data: { guests: Number(guestCount), status: rsvpStatus },
        token,
      });
      mergeEvent(payload);
      toast.success("RSVP updated.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update RSVP.");
    }
  };

  const handleAgendaAdd = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/agenda`, {
        method: "POST",
        data: agendaForm,
        token,
      });
      mergeEvent(payload);
      setAgendaForm(initialAgendaForm);
      toast.success("Agenda item added.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to add agenda item.");
    }
  };

  const handleVolunteerSlot = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/volunteer-slots`, {
        method: "POST",
        data: { needed_count: Number(volunteerCount), title: volunteerTitle },
        token,
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
      const payload = await apiRequest(`/events/${activeEvent.id}/volunteer-signup`, {
        method: "POST",
        data: { slot_id: slotId },
        token,
      });
      mergeEvent(payload);
      toast.success("You joined the volunteer list.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to join that volunteer slot.");
    }
  };

  const handlePotluckItem = async (event) => {
    event.preventDefault();
    if (!activeEvent) return;
    try {
      const payload = await apiRequest(`/events/${activeEvent.id}/potluck-items`, {
        method: "POST",
        data: { item_name: potluckItem },
        token,
      });
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
      const payload = await apiRequest(`/events/${activeEvent.id}/potluck-claim`, {
        method: "POST",
        data: { item_id: itemId },
        token,
      });
      mergeEvent(payload);
      toast.success("Potluck item claimed.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to claim that dish.");
    }
  };

  return (
    <div className="space-y-6">
      <section className="archival-card">
        <p className="eyebrow-text">Events hub</p>
        <h2 className="mt-3 font-display text-3xl text-foreground sm:text-4xl" data-testid="events-page-title">
          Gatherings, roles, agendas, and shared logistics.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base" data-testid="events-page-copy">
          Organize private events, track participation, and coordinate who is bringing what without losing the relational context.
        </p>
      </section>

      {canCreate ? (
        <section className="archival-card" data-testid="events-create-section">
          <div className="flex items-center gap-3">
            <CalendarDays className="h-5 w-5 text-primary" />
            <h3 className="font-display text-3xl text-foreground">Create an event</h3>
          </div>
          <form className="mt-6 grid gap-4 xl:grid-cols-2" onSubmit={handleCreateEvent}>
            <label>
              <span className="field-label">Title</span>
              <Input className="field-input" data-testid="events-create-title-input" onChange={(e) => setEventForm((current) => ({ ...current, title: e.target.value }))} required value={eventForm.title} />
            </label>
            <label>
              <span className="field-label">Date + time</span>
              <Input className="field-input" data-testid="events-create-start-input" onChange={(e) => setEventForm((current) => ({ ...current, start_at: e.target.value }))} required type="datetime-local" value={eventForm.start_at} />
            </label>
            <label>
              <span className="field-label">Location</span>
              <Input className="field-input" data-testid="events-create-location-input" onChange={(e) => setEventForm((current) => ({ ...current, location: e.target.value }))} required value={eventForm.location} />
            </label>
            <label>
              <span className="field-label">Map link</span>
              <Input className="field-input" data-testid="events-create-map-input" onChange={(e) => setEventForm((current) => ({ ...current, map_url: e.target.value }))} placeholder="https://maps.google.com/..." value={eventForm.map_url} />
            </label>
            <label>
              <span className="field-label">Event template</span>
              <select className="field-input w-full" data-testid="events-create-template-select" onChange={(e) => setEventForm((current) => ({ ...current, event_template: e.target.value }))} value={eventForm.event_template}>
                <option value="general">General gathering</option>
                <option value="family-reunion">Family reunion</option>
                <option value="church-gathering">Church gathering</option>
              </select>
            </label>
            <label>
              <span className="field-label">Special focus</span>
              <Input className="field-input" data-testid="events-create-special-focus-input" onChange={(e) => setEventForm((current) => ({ ...current, special_focus: e.target.value }))} placeholder="Ancestral Roll Call, Ministry Assignments, etc." value={eventForm.special_focus} />
            </label>
            <label className="xl:col-span-2">
              <span className="field-label">Description</span>
              <Textarea className="field-textarea" data-testid="events-create-description-input" onChange={(e) => setEventForm((current) => ({ ...current, description: e.target.value }))} required value={eventForm.description} />
            </label>
            <div className="xl:col-span-2">
              <Button className="rounded-full py-6 text-base" data-testid="events-create-submit-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating..." : "Create event"}
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <article className="archival-card" data-testid="events-list-card">
          <h3 className="font-display text-3xl text-foreground">Upcoming and active events</h3>
          <div className="mt-6 space-y-4">
            {events.length ? (
              events.map((event) => (
                <button
                  className={`w-full rounded-[24px] border p-5 text-left transition duration-300 ${event.id === activeEventId ? "border-primary bg-primary/5" : "border-border bg-background/70 hover:border-primary/30"}`}
                  data-testid={`event-card-${event.id}`}
                  key={event.id}
                  onClick={() => setActiveEventId(event.id)}
                  type="button"
                >
                  <p className="text-lg font-semibold text-foreground">{event.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{formatDateTime(event.start_at)} · {event.location}</p>
                  <p className="mt-3 line-clamp-2 text-sm leading-7 text-muted-foreground">{event.description}</p>
                </button>
              ))
            ) : (
              <div className="soft-panel" data-testid="events-empty-state">
                <p className="text-sm text-muted-foreground">There are no events yet. Start by creating the next reunion, service, or gathering.</p>
              </div>
            )}
          </div>
        </article>

        <article className="archival-card" data-testid="events-detail-card">
          {activeEvent ? (
            <div className="space-y-6">
              <div>
                <p className="eyebrow-text">Event detail</p>
                <h3 className="mt-2 font-display text-3xl text-foreground" data-testid="events-active-title">{activeEvent.title}</h3>
                <p className="mt-3 text-sm text-muted-foreground">{formatDateTime(activeEvent.start_at)} · {activeEvent.location}</p>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{activeEvent.description}</p>
                {activeEvent.map_url ? (
                  <a className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-primary" data-testid="events-active-map-link" href={activeEvent.map_url} rel="noreferrer" target="_blank">
                    <MapPinned className="h-4 w-4" /> Open map
                  </a>
                ) : null}
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <div className="soft-panel space-y-4" data-testid="events-rsvp-panel">
                  <div>
                    <p className="text-lg font-semibold text-foreground">RSVP</p>
                    <p className="mt-2 text-sm text-muted-foreground">Track attendance and household guests.</p>
                  </div>
                  <select className="field-input w-full" data-testid="events-rsvp-status-select" onChange={(e) => setRsvpStatus(e.target.value)} value={rsvpStatus}>
                    <option value="going">Going</option>
                    <option value="maybe">Maybe</option>
                    <option value="not-going">Not going</option>
                  </select>
                  <Input className="field-input" data-testid="events-rsvp-guests-input" min={0} onChange={(e) => setGuestCount(e.target.value)} type="number" value={guestCount} />
                  <Button className="w-full rounded-full" data-testid="events-rsvp-submit-button" onClick={handleRsvp} type="button">
                    Save RSVP
                  </Button>
                  <div className="space-y-2">
                    {activeEvent.rsvp_records.map((record) => (
                      <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground" data-testid={`event-rsvp-record-${record.user_id}`} key={record.user_id}>
                        {record.user_name}: {record.status} {record.guests ? `(+${record.guests})` : ""}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="soft-panel space-y-4" data-testid="events-agenda-panel">
                  <div>
                    <p className="text-lg font-semibold text-foreground">Agenda builder</p>
                    <p className="mt-2 text-sm text-muted-foreground">Add the flow of the day or order of service.</p>
                  </div>
                  {canCreate ? (
                    <form className="space-y-3" onSubmit={handleAgendaAdd}>
                      <Input className="field-input" data-testid="events-agenda-time-input" onChange={(e) => setAgendaForm((current) => ({ ...current, time_label: e.target.value }))} placeholder="2:00 PM" required value={agendaForm.time_label} />
                      <Input className="field-input" data-testid="events-agenda-title-input" onChange={(e) => setAgendaForm((current) => ({ ...current, title: e.target.value }))} placeholder="Welcome + prayer" required value={agendaForm.title} />
                      <Textarea className="field-textarea" data-testid="events-agenda-notes-input" onChange={(e) => setAgendaForm((current) => ({ ...current, notes: e.target.value }))} placeholder="Optional notes" value={agendaForm.notes} />
                      <Button className="w-full rounded-full" data-testid="events-agenda-submit-button" type="submit">Add agenda item</Button>
                    </form>
                  ) : null}
                  <div className="space-y-2">
                    {activeEvent.agenda.length ? (
                      activeEvent.agenda.map((item) => (
                        <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`event-agenda-item-${item.id}`} key={item.id}>
                          <p className="text-sm font-semibold text-foreground">{item.time_label} · {item.title}</p>
                          {item.notes ? <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p> : null}
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No agenda items yet.</p>
                    )}
                  </div>
                </div>

                <div className="soft-panel space-y-4" data-testid="events-volunteer-panel">
                  <div className="flex items-center gap-3">
                    <HandHelping className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Volunteer sign-ups</p>
                  </div>
                  {canCreate ? (
                    <form className="space-y-3" onSubmit={handleVolunteerSlot}>
                      <Input className="field-input" data-testid="events-volunteer-title-input" onChange={(e) => setVolunteerTitle(e.target.value)} placeholder="Greeters" required value={volunteerTitle} />
                      <Input className="field-input" data-testid="events-volunteer-count-input" min={1} onChange={(e) => setVolunteerCount(e.target.value)} type="number" value={volunteerCount} />
                      <Button className="w-full rounded-full" data-testid="events-volunteer-submit-button" type="submit">Add volunteer slot</Button>
                    </form>
                  ) : null}
                  <div className="space-y-3">
                    {activeEvent.volunteer_slots.length ? (
                      activeEvent.volunteer_slots.map((slot) => (
                        <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`event-volunteer-slot-${slot.id}`} key={slot.id}>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-foreground">{slot.title}</p>
                              <p className="mt-1 text-xs text-muted-foreground">{slot.assigned_members.length}/{slot.needed_count} filled</p>
                            </div>
                            <Button className="rounded-full" data-testid={`event-volunteer-join-${slot.id}`} onClick={() => handleVolunteerSignup(slot.id)} size="sm" type="button" variant="secondary">
                              Join
                            </Button>
                          </div>
                          <p className="mt-2 text-sm text-muted-foreground">{slot.assigned_members.join(", ") || "No one assigned yet."}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No volunteer slots yet.</p>
                    )}
                  </div>
                </div>

                <div className="soft-panel space-y-4" data-testid="events-potluck-panel">
                  <div className="flex items-center gap-3">
                    <Soup className="h-4 w-4 text-primary" />
                    <p className="text-lg font-semibold text-foreground">Potluck coordination</p>
                  </div>
                  {canCreate ? (
                    <form className="space-y-3" onSubmit={handlePotluckItem}>
                      <Input className="field-input" data-testid="events-potluck-item-input" onChange={(e) => setPotluckItem(e.target.value)} placeholder="Mac and cheese tray" required value={potluckItem} />
                      <Button className="w-full rounded-full" data-testid="events-potluck-submit-button" type="submit">Add dish or supply</Button>
                    </form>
                  ) : null}
                  <div className="space-y-3">
                    {activeEvent.potluck_items.length ? (
                      activeEvent.potluck_items.map((item) => (
                        <div className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3" data-testid={`event-potluck-item-${item.id}`} key={item.id}>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-foreground">{item.item_name}</p>
                              <p className="mt-1 text-xs text-muted-foreground">{item.assigned_to || "Unclaimed"}</p>
                            </div>
                            {!item.assigned_to ? (
                              <Button className="rounded-full" data-testid={`event-potluck-claim-${item.id}`} onClick={() => handlePotluckClaim(item.id)} size="sm" type="button" variant="secondary">
                                Claim
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No potluck items yet.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="soft-panel" data-testid="events-detail-empty-state">
              <UsersRound className="h-5 w-5 text-primary" />
              <p className="mt-3 text-sm text-muted-foreground">Select an event to manage RSVP, agenda, volunteer help, and shared table planning.</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
};