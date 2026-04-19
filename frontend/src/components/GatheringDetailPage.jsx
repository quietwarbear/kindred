import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, CalendarDays, Check, Clock, Link2, MapPin, Pencil, Trash2, Users, Video, X } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

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

const formatBadge = {
  "in-person": { icon: MapPin, label: "In-person" },
  online: { icon: Video, label: "Online" },
  hybrid: { icon: Video, label: "Hybrid" },
};

export const GatheringDetailPage = ({ token, user }) => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [event, setEvent] = useState(null);
  const [members, setMembers] = useState([]);
  const [travelPlans, setTravelPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingEvent, setEditingEvent] = useState(null);
  const [deletingEvent, setDeletingEvent] = useState(false);
  const [zoomLinkDraft, setZoomLinkDraft] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canCreate = useMemo(() => ["host", "organizer"].includes(user?.role), [user?.role]);

  const loadData = useCallback(async () => {
    try {
      const [eventPayload, memberPayload, travelPayload] = await Promise.all([
        apiRequest(`/events/${id}`, { token }),
        apiRequest("/community/members", { token }),
        apiRequest("/travel-plans", { token }),
      ]);
      setEvent(eventPayload);
      setMembers(memberPayload.members || []);
      setTravelPlans(travelPayload.travel_plans || []);
      setZoomLinkDraft(eventPayload.zoom_link || "");
    } catch (error) {
      toast.error("Unable to load gathering details.");
      navigate("/gatherings");
    } finally {
      setLoading(false);
    }
  }, [id, token, navigate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const mergeEvent = (nextEvent) => setEvent(nextEvent);

  const selectedTravelPlans = useMemo(
    () => travelPlans.filter((tp) => tp.event_id === id),
    [travelPlans, id]
  );

  const handleSaveMeetingLink = async () => {
    try {
      const payload = await apiRequest(`/events/${id}/meeting-link`, {
        method: "POST",
        token,
        data: { zoom_link: zoomLinkDraft },
      });
      mergeEvent(payload);
      toast.success("Meeting link saved.");
    } catch {
      toast.error("Unable to save meeting link.");
    }
  };

  const startEditEvent = () => {
    setEditingEvent({
      title: event.title,
      description: event.description,
      start_at: event.start_at,
      location: event.location,
      gathering_format: event.gathering_format,
      max_attendees: event.max_attendees,
    });
  };

  const handleSaveEditEvent = async () => {
    try {
      const payload = await apiRequest(`/events/${id}`, {
        method: "PUT",
        token,
        data: editingEvent,
      });
      mergeEvent(payload);
      setEditingEvent(null);
      toast.success("Gathering updated.");
    } catch {
      toast.error("Unable to update gathering.");
    }
  };

  const handleDeleteEvent = async () => {
    try {
      await apiRequest(`/events/${id}`, { method: "DELETE", token });
      toast.success("Gathering deleted.");
      navigate("/gatherings");
    } catch {
      toast.error("Unable to delete gathering.");
    }
  };

  if (loading) {
    return (
      <div className="app-canvas flex min-h-[50vh] items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading gathering...</p>
      </div>
    );
  }

  if (!event) return null;

  const fmt = formatBadge[event.gathering_format] || formatBadge["in-person"];
  const FormatIcon = fmt.icon;

  return (
    <div className="app-canvas space-y-8 px-4 py-6 sm:px-8 lg:px-12" data-testid="gathering-detail-page">
      {/* Back nav */}
      <button
        className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition"
        data-testid="gathering-detail-back"
        onClick={() => navigate("/gatherings")}
        type="button"
      >
        <ArrowLeft className="h-4 w-4" />
        All gatherings
      </button>

      {/* Hero */}
      <header className="archival-card relative overflow-hidden" data-testid="gathering-detail-hero">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                  <FormatIcon className="h-3 w-3" />
                  {fmt.label}
                </span>
                <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-muted-foreground">
                  {event.recurrence_frequency === "none" ? "One-time" : `${event.recurrence_frequency} recurring`}
                </span>
                {event.subyard_name && (
                  <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-muted-foreground">
                    {event.subyard_name}
                  </span>
                )}
              </div>
              {editingEvent ? (
                <div className="mt-4 space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4" data-testid="gathering-detail-edit-form">
                  <label className="block">
                    <span className="text-xs font-semibold text-muted-foreground">Title</span>
                    <Input className="field-input mt-1" data-testid="gathering-detail-edit-title" onChange={(e) => setEditingEvent((c) => ({ ...c, title: e.target.value }))} value={editingEvent.title} />
                  </label>
                  <label className="block">
                    <span className="text-xs font-semibold text-muted-foreground">Description</span>
                    <Textarea className="field-textarea mt-1" data-testid="gathering-detail-edit-description" onChange={(e) => setEditingEvent((c) => ({ ...c, description: e.target.value }))} rows={3} value={editingEvent.description} />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Date & Time</span>
                      <Input className="field-input mt-1" data-testid="gathering-detail-edit-start" onChange={(e) => setEditingEvent((c) => ({ ...c, start_at: e.target.value }))} type="datetime-local" value={editingEvent.start_at} />
                    </label>
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Location</span>
                      <Input className="field-input mt-1" data-testid="gathering-detail-edit-location" onChange={(e) => setEditingEvent((c) => ({ ...c, location: e.target.value }))} value={editingEvent.location} />
                    </label>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Format</span>
                      <select className="field-input mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" data-testid="gathering-detail-edit-format" onChange={(e) => setEditingEvent((c) => ({ ...c, gathering_format: e.target.value }))} value={editingEvent.gathering_format}>
                        <option value="in-person">In-person</option>
                        <option value="online">Online</option>
                        <option value="hybrid">Hybrid</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="text-xs font-semibold text-muted-foreground">Capacity</span>
                      <Input className="field-input mt-1" data-testid="gathering-detail-edit-capacity" min={1} onChange={(e) => setEditingEvent((c) => ({ ...c, max_attendees: e.target.value }))} type="number" value={editingEvent.max_attendees} />
                    </label>
                  </div>
                  <div className="flex gap-2 pt-1">
                    <Button className="rounded-full" data-testid="gathering-detail-edit-save" onClick={handleSaveEditEvent} size="sm"><Check className="mr-1 h-3 w-3" /> Save</Button>
                    <Button className="rounded-full" data-testid="gathering-detail-edit-cancel" onClick={() => setEditingEvent(null)} size="sm" variant="outline"><X className="mr-1 h-3 w-3" /> Cancel</Button>
                  </div>
                </div>
              ) : (
                <>
                  <h1 className="mt-4 font-display text-4xl text-foreground sm:text-5xl" data-testid="gathering-detail-title">
                    {event.title}
                  </h1>
                  <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <CalendarDays className="h-4 w-4 text-primary" />
                      {formatDateTime(event.start_at)}
                    </span>
                    {event.location && (
                      <span className="inline-flex items-center gap-1.5">
                        <MapPin className="h-4 w-4 text-primary" />
                        {event.location}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1.5">
                      <Users className="h-4 w-4 text-primary" />
                      {event.max_attendees ? `Up to ${event.max_attendees}` : "Flexible capacity"}
                    </span>
                    {event.suggested_contribution > 0 && (
                      <span className="inline-flex items-center gap-1.5">
                        {shortCurrency(event.suggested_contribution)} suggested
                      </span>
                    )}
                  </div>
                  {event.description && (
                    <p className="mt-4 max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base">
                      {event.description}
                    </p>
                  )}
                </>
              )}
              {/* Role badges */}
              {event.assigned_roles?.length > 0 && !editingEvent && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {event.assigned_roles.map((role) => (
                    <span className="rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-semibold text-foreground" key={role}>
                      {role}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Actions */}
            {canCreate && !editingEvent && (
              <div className="flex shrink-0 gap-2">
                <Button className="rounded-full h-9" data-testid="gathering-detail-edit-btn" onClick={startEditEvent} size="sm" variant="outline">
                  <Pencil className="mr-1.5 h-3.5 w-3.5" /> Edit
                </Button>
                <Button className="rounded-full h-9" data-testid="gathering-detail-delete-btn" onClick={() => setDeletingEvent(true)} size="sm" variant="outline">
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
                </Button>
              </div>
            )}
          </div>

          {/* Delete confirmation */}
          {deletingEvent && (
            <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
              <p className="text-sm font-semibold text-destructive">Delete this gathering?</p>
              <p className="text-sm text-muted-foreground">This action cannot be undone.</p>
              <div className="mt-3 flex gap-2">
                <Button className="rounded-full" data-testid="gathering-detail-delete-confirm" onClick={handleDeleteEvent} size="sm" variant="destructive">Confirm delete</Button>
                <Button className="rounded-full" data-testid="gathering-detail-delete-cancel" onClick={() => setDeletingEvent(false)} size="sm" variant="outline">Cancel</Button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Meeting link (online/hybrid only) */}
      {event.gathering_format !== "in-person" && (
        <section className="archival-card" data-testid="gathering-detail-meeting-link">
          <div className="flex items-center gap-3">
            <Link2 className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">Meeting link</h2>
          </div>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row">
            <Input className="field-input" data-testid="gathering-detail-zoom-input" onChange={(e) => setZoomLinkDraft(e.target.value)} placeholder="https://zoom.us/j/..." value={zoomLinkDraft} />
            <Button className="rounded-full" data-testid="gathering-detail-zoom-save" onClick={handleSaveMeetingLink} type="button">
              Save link
            </Button>
          </div>
          {event.zoom_link && (
            <p className="mt-3 text-sm text-muted-foreground">{event.zoom_link}</p>
          )}
        </section>
      )}

      {/* Planning sections — 2-column grid */}
      <section className="grid gap-6 lg:grid-cols-2" data-testid="gathering-detail-panels">
        <GatheringAgenda canCreate={canCreate} event={event} onUpdate={mergeEvent} token={token} />
        <GatheringRsvp event={event} onUpdate={mergeEvent} token={token} />
        <GatheringChecklist canCreate={canCreate} event={event} onUpdate={mergeEvent} token={token} />
        <GatheringInvites event={event} members={members} onUpdate={mergeEvent} token={token} />
        <GatheringRoles event={event} onUpdate={mergeEvent} token={token} />
        <GatheringVolunteers canCreate={canCreate} event={event} onUpdate={mergeEvent} token={token} />
        <GatheringPotluck canCreate={canCreate} event={event} onUpdate={mergeEvent} token={token} />
        <GatheringTravel canCreate={canCreate} event={event} onReload={loadData} token={token} travelPlans={selectedTravelPlans} />
      </section>
    </div>
  );
};
