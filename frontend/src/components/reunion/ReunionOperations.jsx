import { useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  ClipboardList,
  MapPin,
  Printer,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { trackReunionEvent } from "@/lib/analytics";
import { dayKeyAtTimezone, groupActivitiesByDay } from "@/lib/itinerary";

export const ReunionOperations = ({ event, operations }) => {
  const [activityFilter, setActivityFilter] = useState("all");
  const [dayFilter, setDayFilter] = useState("all");
  const rosterDetailsRef = useRef(null);
  const days = useMemo(() => groupActivitiesByDay(event), [event]);
  const activities = (event.agenda || []).filter((activity) => activity.visibility !== "archived");
  const filtered = activities.filter(
    (activity) =>
      (activityFilter === "all" || activity.id === activityFilter)
      && (
        dayFilter === "all"
        || dayKeyAtTimezone(
          activity.start_at,
          activity.timezone || event.timezone || "UTC"
        ) === dayFilter
      )
  );

  if (!operations) return null;

  const overallAttending = (operations.overall?.going || 0) + (operations.overall?.some || 0);
  const capacityWarnings = activities.filter((activity) => {
    const summary = operations.activity_summaries?.[activity.id] || {};
    return activity.capacity && (summary.party_size || 0) >= activity.capacity;
  });

  const viewRosters = () => {
    trackReunionEvent("activity_roster_viewed", {
      activity_count: filtered.length,
      actor_type: "host",
    });
  };

  const printOperations = () => {
    if (rosterDetailsRef.current) rosterDetailsRef.current.open = true;
    window.print();
  };

  return (
    <section className="archival-card print:border-0 print:shadow-none" data-testid="reunion-operations">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow-text">Reunion operations</p>
          <h2 className="mt-2 font-display text-3xl">The essentials at a glance</h2>
        </div>
        <Button className="print:hidden" onClick={printOperations} type="button" variant="outline">
          <Printer className="mr-2 h-4 w-4" /> Print run of show
        </Button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          [Users, operations.total_invitees, "Total invitees"],
          [Users, overallAttending, "Attending overall"],
          [ClipboardList, operations.unanswered_invitations, "Unanswered"],
          [CalendarDays, Object.keys(days).length, "Scheduled days"],
        ].map(([Icon, value, label]) => (
          <div className="soft-panel" key={label}>
            <Icon className="h-4 w-4 text-primary" />
            <p className="mt-3 text-2xl font-semibold">{value}</p>
            <p className="text-sm text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>

      {Object.keys(days).length ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="reunion-attendance-by-day">
          {Object.keys(days).map((day) => {
            const summary = operations.day_summaries?.[day] || {};
            return (
              <div className="rounded-2xl border border-border p-4" key={day}>
                <p className="text-sm font-semibold">{new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" })}</p>
                <p className="mt-2 text-sm text-muted-foreground">{summary.coming || 0} people coming · {summary.maybe || 0} maybe</p>
                <p className="text-sm text-muted-foreground">{summary.party_size || 0} total party size</p>
              </div>
            );
          })}
        </div>
      ) : null}

      {(capacityWarnings.length || operations.missing_venue_activity_ids?.length) ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {capacityWarnings.length ? (
            <div className="flex items-start gap-3 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <p className="text-sm">{capacityWarnings.length} activity capacity warning{capacityWarnings.length === 1 ? "" : "s"}.</p>
            </div>
          ) : null}
          {operations.missing_venue_activity_ids?.length ? (
            <div className="flex items-start gap-3 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <p className="text-sm">{operations.missing_venue_activity_ids.length} activit{operations.missing_venue_activity_ids.length === 1 ? "y needs" : "ies need"} a venue or “location to be announced.”</p>
            </div>
          ) : null}
        </div>
      ) : null}

      <details className="mt-6 rounded-2xl border border-border p-4" onToggle={(eventToggle) => eventToggle.currentTarget.open && viewRosters()} ref={rosterDetailsRef}>
        <summary className="cursor-pointer font-semibold">Attendance by activity and authorized rosters</summary>
        <div className="mt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              <span className="field-label">Filter by day</span>
              <select className="field-input w-full" onChange={(eventChange) => setDayFilter(eventChange.target.value)} value={dayFilter}>
                <option value="all">All days</option>
                {Object.keys(days).map((day) => <option key={day} value={day}>{day}</option>)}
              </select>
            </label>
            <label>
              <span className="field-label">Filter by activity</span>
              <select className="field-input w-full" onChange={(eventChange) => setActivityFilter(eventChange.target.value)} value={activityFilter}>
                <option value="all">All activities</option>
                {activities.filter((activity) => (
                  dayFilter === "all"
                  || dayKeyAtTimezone(
                    activity.start_at,
                    activity.timezone || event.timezone || "UTC"
                  ) === dayFilter
                )).map((activity) => <option key={activity.id} value={activity.id}>{activity.title}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-5 space-y-5">
            {filtered.map((activity) => {
              const summary = operations.activity_summaries?.[activity.id] || {};
              const roster = operations.activity_rosters?.[activity.id] || [];
              return (
                <article className="rounded-2xl bg-muted/40 p-4" key={activity.id}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-semibold">{activity.title}</h3>
                    <p className="text-sm text-muted-foreground">
                      {summary.coming || 0} coming · {summary.maybe || 0} maybe · {summary.no_response || 0} no response
                    </p>
                  </div>
                  {roster.length ? (
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead><tr><th className="pb-2">Attendee</th><th className="pb-2">Response</th><th className="pb-2">Party</th><th className="pb-2">Updated</th></tr></thead>
                        <tbody>
                          {roster.map((person) => (
                            <tr className="border-t border-border" key={person.row_key}>
                              <td className="py-2">{person.display_name}</td>
                              <td>{person.status}</td>
                              <td>{person.party_size}</td>
                              <td>{person.updated_at ? new Date(person.updated_at).toLocaleString() : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : <p className="mt-3 text-sm text-muted-foreground">No activity responses yet.</p>}
                </article>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Organizer rosters intentionally omit email addresses, phone numbers, minors’ details, invitation tokens, and private notes.
          </p>
        </div>
      </details>

      {operations.recent_changes?.length ? (
        <details className="mt-4 rounded-2xl border border-border p-4">
          <summary className="cursor-pointer font-semibold">Recently changed responses</summary>
          <div className="mt-3 space-y-2">
            {operations.recent_changes.map((change) => (
              <p className="text-sm text-muted-foreground" key={`${change.row_key}:${change.updated_at}`}>
                {change.display_name} · {change.status} · {change.updated_at ? new Date(change.updated_at).toLocaleString() : "Recently"}
              </p>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
};
