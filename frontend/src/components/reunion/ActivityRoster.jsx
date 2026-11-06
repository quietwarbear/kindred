import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Download, RefreshCw, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiBlobRequest, apiRequest } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const ROSTER_STATUS_LABELS = {
  coming: "Coming",
  maybe: "Maybe",
  "not-coming": "Not coming",
  "no-response": "No response",
};

export const ENDED_STILL_COMING = "ended_still_coming";

export const rosterCsvPath = (eventId, activityId = "") => (
  `/events/${eventId}/activity-roster.csv${activityId ? `?activity_id=${encodeURIComponent(activityId)}` : ""}`
);

export const filterRosterPeople = (people, status) => (
  status === "all" ? people : status === "flagged" ? people.filter((p) => p.flags?.length) : people.filter((p) => p.status === status)
);

const saveBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
};

const formatWhen = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

/**
 * K7 organizer view: every registered person's answer for each activity,
 * expected turnout, a flag for people still marked coming to activities that
 * have ended, and CSV export. Names only, like the operations roster.
 */
export const ActivityRoster = ({ eventId, token, refreshKey = 0 }) => {
  const [roster, setRoster] = useState(null);
  const [error, setError] = useState("");
  const [activityId, setActivityId] = useState("");
  const [status, setStatus] = useState("all");
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      setRoster(await apiRequest(`/events/${eventId}/activity-roster`, { token }));
    } catch {
      setError("The activity roster could not be loaded.");
    }
  }, [eventId, token]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const activities = useMemo(() => roster?.activities || [], [roster]);
  const selected = activities.find((activity) => activity.id === activityId) || activities[0];

  const exportCsv = async (scope) => {
    setExporting(true);
    try {
      const blob = await apiBlobRequest(rosterCsvPath(eventId, scope), { token });
      saveBlob(blob, "activity-roster.csv");
    } catch {
      toast.error("The roster could not be exported.");
    } finally {
      setExporting(false);
    }
  };

  if (error) {
    return (
      <section className="archival-card" data-testid="activity-roster">
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button className="mt-3" onClick={load} size="sm" type="button" variant="outline">Try again</Button>
      </section>
    );
  }
  if (!roster) return null;
  if (!activities.length) return null;

  const people = filterRosterPeople(selected.people, status);

  return (
    <section className="archival-card" data-testid="activity-roster">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow-text">Who’s coming to each activity</p>
          <h2 className="mt-2 font-display text-3xl">Activity roster</h2>
          <p className="mt-2 text-sm text-muted-foreground">{roster.registered} registered for this event.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={load} size="sm" type="button" variant="outline">
            <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" /> Refresh
          </Button>
          <Button data-testid="activity-roster-export-all" disabled={exporting} onClick={() => exportCsv("")} size="sm" type="button" variant="outline">
            <Download aria-hidden="true" className="mr-2 h-4 w-4" /> Export all (CSV)
          </Button>
        </div>
      </div>

      {roster.ended_still_coming ? (
        <p className="mt-4 flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm" data-testid="activity-roster-ended-warning" role="status">
          <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          {roster.ended_still_coming} {roster.ended_still_coming === 1 ? "person is" : "people are"} still marked coming for activities that have already ended.
        </p>
      ) : null}

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <label>
          <span className="field-label">Activity</span>
          <select className="field-input w-full" data-testid="activity-roster-select" onChange={(change) => setActivityId(change.target.value)} value={selected.id}>
            {activities.map((activity) => (
              <option key={activity.id} value={activity.id}>
                {activity.title}{activity.ended ? " (ended)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">Show</span>
          <select className="field-input w-full" data-testid="activity-roster-status" onChange={(change) => setStatus(change.target.value)} value={status}>
            <option value="all">Everyone</option>
            {Object.entries(ROSTER_STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            <option value="flagged">Flagged</option>
          </select>
        </label>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-6" data-testid={`activity-roster-counts-${selected.id}`}>
        {Object.entries(ROSTER_STATUS_LABELS).map(([value, label]) => (
          <div className="rounded-xl bg-muted/40 p-3" key={value}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-lg font-semibold">{selected.counts[value] || 0}</dd>
          </div>
        ))}
        <div className="rounded-xl bg-muted/40 p-3">
          <dt className="text-muted-foreground">Expected</dt>
          <dd className="text-lg font-semibold">{selected.expected_turnout}{selected.capacity ? ` / ${selected.capacity}` : ""}</dd>
        </div>
        <div className="rounded-xl bg-muted/40 p-3">
          <dt className="text-muted-foreground">With maybes</dt>
          <dd className="text-lg font-semibold">{selected.possible_turnout}</dd>
        </div>
      </dl>

      <div className="mt-4 flex justify-end">
        <Button data-testid="activity-roster-export-one" disabled={exporting} onClick={() => exportCsv(selected.id)} size="sm" type="button" variant="ghost">
          <Download aria-hidden="true" className="mr-2 h-4 w-4" /> Export this activity
        </Button>
      </div>

      {people.length ? (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">People for {selected.title}</caption>
            <thead>
              <tr>
                <th className="pb-2" scope="col">Name</th>
                <th className="pb-2" scope="col">Response</th>
                <th className="pb-2" scope="col">Option</th>
                <th className="pb-2" scope="col">Party</th>
                <th className="pb-2" scope="col">Answered</th>
              </tr>
            </thead>
            <tbody>
              {people.map((person) => (
                <tr className="border-t border-border" data-testid={`activity-roster-row-${person.row_key}`} key={person.row_key}>
                  <td className="py-2">
                    {person.name}
                    {!person.registered ? <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">Not registered</span> : null}
                    {person.flags?.includes(ENDED_STILL_COMING) ? (
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Activity ended</span>
                    ) : null}
                  </td>
                  <td>{ROSTER_STATUS_LABELS[person.status] || person.status}</td>
                  <td>{person.choice || "—"}</td>
                  <td>{person.party_size || "—"}</td>
                  <td>{formatWhen(person.responded_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground"><Users aria-hidden="true" className="mr-1 inline h-4 w-4" />Nobody in this view.</p>
      )}
    </section>
  );
};
