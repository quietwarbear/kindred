import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock,
  Copy,
  Eye,
  EyeOff,
  MapPin,
  Pencil,
  Plus,
  Trash2,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "@/lib/api";
import { trackReunionEvent } from "@/lib/analytics";
import {
  findActivityOverlaps,
  groupActivitiesByDay,
  reunionDayCountFromEvent,
  runOfShow,
} from "@/lib/itinerary";
import { toast } from "@/components/ui/sonner";

const activityDraft = (event, source = {}) => {
  const date = String(source.start_at || event.start_at || "").slice(0, 10);
  return {
    title: source.title || "",
    description: source.description || "",
    start_at: source.start_at || (date ? `${date}T10:00` : ""),
    end_at: source.end_at || (date ? `${date}T11:00` : ""),
    timezone: source.timezone || "",
    venue_name: source.venue_name || "",
    venue_address: source.venue_address || "",
    venue_detail: source.venue_detail || "",
    map_url: source.map_url || "",
    virtual_link: source.virtual_link || "",
    location_tba: Boolean(source.location_tba),
    capacity: source.capacity || "",
    rsvp_deadline: source.rsvp_deadline || "",
    attendance_requested: source.attendance_requested !== false,
    notes: source.notes || "",
    visibility: source.visibility === "published" ? "published" : "draft",
    featured: Boolean(source.featured),
  };
};

const dayLabel = (value, timezone) => {
  try {
    return new Intl.DateTimeFormat(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
      timeZone: timezone || "UTC",
    }).format(new Date(`${value}T12:00:00Z`));
  } catch {
    return value;
  }
};

const timeLabel = (value) => {
  if (!value) return "";
  const [, time = ""] = value.split("T");
  const [hour = "0", minute = "00"] = time.split(":");
  const parsedHour = Number(hour);
  const suffix = parsedHour >= 12 ? "PM" : "AM";
  return `${parsedHour % 12 || 12}:${minute} ${suffix}`;
};

const runStateLabel = {
  past: "Past",
  happening: "Happening now",
  "up-next": "Up next",
  "later-today": "Later today",
  future: "Future day",
};

const apiErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail?.errors)) return detail.errors.join(" ");
  return fallback;
};

const ActivityForm = ({ event, initial, onCancel, onSaved, token, activityId = "" }) => {
  const [form, setForm] = useState(() => activityDraft(event, initial));
  const [saving, setSaving] = useState(false);
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (submitEvent) => {
    submitEvent.preventDefault();
    setSaving(true);
    try {
      const payload = await apiRequest(
        activityId ? `/events/${event.id}/agenda/${activityId}` : `/events/${event.id}/agenda`,
        {
          method: activityId ? "PUT" : "POST",
          token,
          data: {
            ...form,
            capacity: form.capacity ? Number(form.capacity) : null,
          },
        }
      );
      onSaved(payload);
      if (!activityId) {
        const created = payload.agenda?.find(
          (activity) => activity.title === form.title && activity.start_at === form.start_at
        );
        trackReunionEvent("itinerary_activity_created", {
          activity_count: payload.agenda?.filter((activity) => activity.start_at).length || 0,
          venue_assigned: Boolean(form.venue_name || form.virtual_link),
          activity_position: created
            ? payload.agenda.findIndex((activity) => activity.id === created.id) + 1
            : undefined,
          actor_type: "host",
        });
        if (form.visibility === "published") {
          trackReunionEvent("itinerary_activity_published", {
            activity_count: payload.agenda?.filter((activity) => activity.visibility === "published").length || 0,
            venue_assigned: Boolean(form.venue_name || form.virtual_link),
            actor_type: "host",
          });
        }
      }
      toast.success(activityId ? "Activity updated." : "Activity added to the itinerary.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Unable to save this activity."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="mt-5 space-y-4 rounded-2xl border border-primary/20 bg-primary/5 p-4" data-testid="itinerary-activity-form" onSubmit={submit}>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="sm:col-span-2">
          <span className="field-label">Activity title</span>
          <Input data-testid="itinerary-title-input" maxLength={160} onChange={(eventChange) => update("title", eventChange.target.value)} required value={form.title} />
        </label>
        <label className="sm:col-span-2">
          <span className="field-label">Description or instructions</span>
          <Textarea maxLength={2000} onChange={(eventChange) => update("description", eventChange.target.value)} value={form.description} />
        </label>
        <label>
          <span className="field-label">Starts</span>
          <Input data-testid="itinerary-start-input" onChange={(eventChange) => update("start_at", eventChange.target.value)} required type="datetime-local" value={form.start_at} />
        </label>
        <label>
          <span className="field-label">Ends</span>
          <Input data-testid="itinerary-end-input" onChange={(eventChange) => update("end_at", eventChange.target.value)} required type="datetime-local" value={form.end_at} />
        </label>
        <label>
          <span className="field-label">Timezone override <span className="font-normal">(optional)</span></span>
          <Input list="itinerary-timezones" onChange={(eventChange) => update("timezone", eventChange.target.value)} placeholder={`Inherits ${event.timezone || "UTC"}`} value={form.timezone} />
        </label>
        <label>
          <span className="field-label">RSVP deadline <span className="font-normal">(optional)</span></span>
          <Input onChange={(eventChange) => update("rsvp_deadline", eventChange.target.value)} type="datetime-local" value={form.rsvp_deadline} />
        </label>
        <datalist id="itinerary-timezones">
          {["America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York", "Europe/London", "Africa/Lagos", "Africa/Nairobi", "UTC"].map((zone) => <option key={zone} value={zone} />)}
        </datalist>
        <label>
          <span className="field-label">Venue name</span>
          <Input maxLength={160} onChange={(eventChange) => update("venue_name", eventChange.target.value)} value={form.venue_name} />
        </label>
        <label>
          <span className="field-label">Room, pavilion, or meeting point</span>
          <Input maxLength={160} onChange={(eventChange) => update("venue_detail", eventChange.target.value)} value={form.venue_detail} />
        </label>
        <label className="sm:col-span-2">
          <span className="field-label">Venue address</span>
          <Input maxLength={300} onChange={(eventChange) => update("venue_address", eventChange.target.value)} value={form.venue_address} />
        </label>
        <label>
          <span className="field-label">Map link <span className="font-normal">(optional)</span></span>
          <Input onChange={(eventChange) => update("map_url", eventChange.target.value)} type="url" value={form.map_url} />
        </label>
        <label>
          <span className="field-label">Virtual meeting link <span className="font-normal">(optional)</span></span>
          <Input onChange={(eventChange) => update("virtual_link", eventChange.target.value)} type="url" value={form.virtual_link} />
        </label>
        <label>
          <span className="field-label">Capacity <span className="font-normal">(optional)</span></span>
          <Input min={1} onChange={(eventChange) => update("capacity", eventChange.target.value)} type="number" value={form.capacity} />
        </label>
        <label>
          <span className="field-label">Invitee visibility</span>
          <select className="field-input w-full" onChange={(eventChange) => update("visibility", eventChange.target.value)} value={form.visibility}>
            <option value="draft">Draft — organizer only</option>
            <option value="published">Published to invitees</option>
          </select>
        </label>
        <label className="sm:col-span-2">
          <span className="field-label">Dress, transportation, accessibility, or what to bring</span>
          <Textarea maxLength={2000} onChange={(eventChange) => update("notes", eventChange.target.value)} value={form.notes} />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex items-center gap-2 text-sm">
          <input checked={form.location_tba} onChange={(eventChange) => update("location_tba", eventChange.target.checked)} type="checkbox" />
          Location to be announced
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input checked={form.attendance_requested} onChange={(eventChange) => update("attendance_requested", eventChange.target.checked)} type="checkbox" />
          Ask who is coming
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input checked={form.featured} onChange={(eventChange) => update("featured", eventChange.target.checked)} type="checkbox" />
          Feature in invitation
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="itinerary-save-button" disabled={saving} type="submit">
          {saving ? "Saving…" : activityId ? "Save activity" : "Add activity"}
        </Button>
        <Button onClick={onCancel} type="button" variant="outline">Cancel</Button>
      </div>
    </form>
  );
};

export const ReunionItinerary = ({ event, token, canCreate, onUpdate }) => {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState("");
  const [localResponses, setLocalResponses] = useState({});
  const viewedTracked = useRef(false);
  const groups = useMemo(() => groupActivitiesByDay(event), [event]);
  const overlapIds = useMemo(
    () => new Set(findActivityOverlaps(event).flat()),
    [event]
  );
  const rolling = useMemo(() => runOfShow(event), [event]);
  const runStates = Object.fromEntries(rolling.map((activity) => [activity.id, activity.run_state]));

  useEffect(() => {
    if (viewedTracked.current) return;
    viewedTracked.current = true;
    trackReunionEvent("itinerary_viewed", {
      activity_count: event.agenda?.filter((activity) => activity.start_at).length || 0,
      actor_type: canCreate ? "host" : "invitee",
    });
  }, [canCreate, event.agenda]);

  const mutate = async (path, method = "POST") => {
    try {
      const payload = await apiRequest(path, { method, token });
      onUpdate(payload);
      return payload;
    } catch (error) {
      toast.error(apiErrorMessage(error, "Unable to update the itinerary."));
      return null;
    }
  };

  const publish = async (activity, position) => {
    const payload = await mutate(`/events/${event.id}/agenda/${activity.id}/publish`);
    if (payload) {
      trackReunionEvent("itinerary_activity_published", {
        activity_count: payload.agenda?.filter((item) => item.visibility === "published").length || 0,
        venue_assigned: Boolean(activity.venue_name || activity.virtual_link),
        activity_position: position,
        actor_type: "host",
      });
    }
  };

  const duplicate = async (activity) => {
    const payload = await mutate(`/events/${event.id}/agenda/${activity.id}/duplicate`);
    if (payload) toast.success("Activity duplicated as a private draft.");
  };

  const remove = async (activity, confirmed = false) => {
    try {
      const suffix = confirmed ? "?confirm_responses=true" : "";
      const payload = await apiRequest(`/events/${event.id}/agenda/${activity.id}${suffix}`, {
        method: "DELETE",
        token,
      });
      onUpdate(payload);
      setConfirmDeleteId("");
      toast.success(confirmed ? "Activity archived and responses preserved." : "Activity deleted.");
    } catch (error) {
      if (error.response?.status === 409) {
        setConfirmDeleteId(activity.id);
      } else {
        toast.error(apiErrorMessage(error, "Unable to remove this activity."));
      }
    }
  };

  const rsvp = async (activity, response) => {
    try {
      const payload = await apiRequest(`/events/${event.id}/activity-rsvp`, {
        method: "POST",
        token,
        data: { activity_id: activity.id, status: response, party_size: 1 },
      });
      setLocalResponses((current) => ({ ...current, [activity.id]: response }));
      onUpdate(payload);
      trackReunionEvent("activity_rsvp_updated", {
        response_category: response,
        actor_type: "invitee",
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to update this activity response.");
    }
  };

  return (
    <section className="archival-card print:border-0 print:shadow-none" data-testid="reunion-itinerary">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow-text">Rolling run of show</p>
          <h2 className="mt-2 font-display text-3xl">Reunion itinerary</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {reunionDayCountFromEvent(event)} day{reunionDayCountFromEvent(event) === 1 ? "" : "s"} · {event.timezone || "UTC"} · Activities remain part of this one gathering.
          </p>
        </div>
        {canCreate ? (
          <Button data-testid="itinerary-add-button" onClick={() => { setEditingId(""); setShowForm(true); }} type="button">
            <Plus className="mr-2 h-4 w-4" /> Add activity
          </Button>
        ) : null}
      </div>

      {showForm ? (
        <ActivityForm
          event={event}
          initial={editingId ? event.agenda.find((activity) => activity.id === editingId) : undefined}
          activityId={editingId}
          onCancel={() => { setShowForm(false); setEditingId(""); }}
          onSaved={(payload) => { onUpdate(payload); setShowForm(false); setEditingId(""); }}
          token={token}
        />
      ) : null}

      {overlapIds.size ? (
        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p>Some activities overlap. That is allowed, but invitees will see the schedule conflict.</p>
        </div>
      ) : null}

      <div className="mt-6 space-y-8">
        {Object.entries(groups).map(([day, activities]) => (
          <section key={day}>
            <h3 className="flex items-center gap-2 border-b border-border pb-2 font-semibold">
              <CalendarDays className="h-4 w-4 text-primary" />
              {dayLabel(day, event.timezone)}
            </h3>
            <div className="mt-3 space-y-3">
              {activities.map((activity, activityIndex) => {
                const summary = event.activity_rsvp_summaries?.[activity.id] || {};
                const full = activity.capacity && (summary.party_size || 0) >= activity.capacity;
                const editing = editingId === activity.id && showForm;
                if (editing) return null;
                return (
                  <article
                    className={`rounded-2xl border p-4 ${runStates[activity.id] === "happening" ? "border-emerald-400 bg-emerald-500/10" : runStates[activity.id] === "up-next" ? "border-primary bg-primary/5" : "border-border bg-background/70"}`}
                    data-testid={`itinerary-activity-${activity.id}`}
                    key={activity.id}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full bg-muted px-2 py-1 text-xs font-semibold">{runStateLabel[runStates[activity.id]] || "Scheduled"}</span>
                          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs">
                            {activity.visibility === "published" ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                            {activity.visibility === "published" ? "Published" : "Draft"}
                          </span>
                          {overlapIds.has(activity.id) ? <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900">Overlaps</span> : null}
                          {activity.revision_history?.length ? <span className="rounded-full bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-900">Schedule updated · responses preserved</span> : null}
                        </div>
                        <h4 className="mt-3 text-lg font-semibold">{activity.title}</h4>
                        <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                          <Clock className="h-4 w-4" /> {timeLabel(activity.start_at)}–{timeLabel(activity.end_at)}
                          {activity.end_at?.slice(0, 10) !== activity.start_at?.slice(0, 10) ? " · ends next day" : ""}
                        </p>
                        <p className="mt-1 flex items-start gap-2 text-sm text-muted-foreground">
                          <MapPin className="mt-0.5 h-4 w-4 shrink-0" />
                          {activity.location_tba
                            ? "Location to be announced"
                            : [activity.venue_name, activity.venue_detail, activity.venue_address].filter(Boolean).join(" · ") || "Venue missing"}
                        </p>
                        {activity.description ? <p className="mt-3 text-sm leading-6 text-muted-foreground">{activity.description}</p> : null}
                        {activity.notes ? <p className="mt-2 text-sm"><strong>Know before you go:</strong> {activity.notes}</p> : null}
                      </div>
                      <div className="min-w-32 text-sm">
                        <p className="flex items-center gap-2 font-semibold"><Users className="h-4 w-4" /> Who’s coming?</p>
                        <p className="mt-2 text-muted-foreground">{summary.coming || 0} coming · {summary.maybe || 0} maybe</p>
                        <p className="text-muted-foreground">{summary.no_response || 0} no response</p>
                        {activity.capacity ? <p className={full ? "mt-1 font-semibold text-amber-600" : "mt-1 text-muted-foreground"}>{summary.party_size || 0}/{activity.capacity} places</p> : null}
                      </div>
                    </div>

                    {!canCreate && activity.visibility === "published" && activity.attendance_requested ? (
                      <fieldset className="mt-4">
                        <legend className="text-sm font-semibold">Are you joining this activity?</legend>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {[
                            ["coming", "Coming"],
                            ["maybe", "Maybe"],
                            ["not-coming", "Not coming"],
                          ].map(([value, label]) => (
                            <Button
                              aria-pressed={localResponses[activity.id] === value}
                              key={value}
                              onClick={() => rsvp(activity, value)}
                              size="sm"
                              type="button"
                              variant={localResponses[activity.id] === value ? "default" : "outline"}
                            >
                              {label}
                            </Button>
                          ))}
                        </div>
                      </fieldset>
                    ) : null}

                    {canCreate ? (
                      <div className="mt-4 flex flex-wrap gap-2 print:hidden">
                        <Button onClick={() => { setEditingId(activity.id); setShowForm(true); }} size="sm" type="button" variant="outline"><Pencil className="mr-1 h-3 w-3" /> Edit</Button>
                        <Button onClick={() => duplicate(activity)} size="sm" type="button" variant="outline"><Copy className="mr-1 h-3 w-3" /> Duplicate</Button>
                        {activity.visibility !== "published" ? (
                          <Button onClick={() => publish(activity, activityIndex + 1)} size="sm" type="button" variant="outline"><CheckCircle2 className="mr-1 h-3 w-3" /> Publish</Button>
                        ) : null}
                        <Button onClick={() => remove(activity)} size="sm" type="button" variant="outline"><Trash2 className="mr-1 h-3 w-3" /> Remove</Button>
                      </div>
                    ) : null}

                    {confirmDeleteId === activity.id ? (
                      <div className="mt-3 rounded-xl border border-destructive/30 bg-destructive/5 p-3">
                        <p className="text-sm font-semibold">This activity has responses.</p>
                        <p className="mt-1 text-sm text-muted-foreground">Removing it will archive the activity and preserve its attendance history.</p>
                        <div className="mt-3 flex gap-2">
                          <Button onClick={() => remove(activity, true)} size="sm" type="button" variant="destructive">Archive activity</Button>
                          <Button onClick={() => setConfirmDeleteId("")} size="sm" type="button" variant="outline">Keep activity</Button>
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        ))}
        {!Object.keys(groups).length ? (
          <div className="rounded-2xl border border-dashed border-border p-6 text-center">
            <p className="font-semibold">No timed activities yet.</p>
            <p className="mt-2 text-sm text-muted-foreground">The reunion is already usable. Add the run of show when you are ready.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
};
